from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List
from uuid import uuid4
import asyncio
import os
import json
import smtplib
from email.message import EmailMessage

from fastapi import UploadFile, HTTPException, Form
from sqlalchemy import select, func, and_, or_, case, extract, insert, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from jinja2 import Template

from app.models.buildings import Room, Building, Site, UsageType
from app.models.housing import (
    Housing, Occupancy, Occupant, Unavailability, 
    HousingStatusHistory, OccupancyStatusHistory,
    Cleaning, CleaningInvitationLog, EmailTemplate, EmailTemplateAttachment, EmailLog,
    occupancy_occupants
)
from app.models.user import User
from app.models.volunteer import Volunteer
from app.models.module import Module, ModuleConfig


HOUSING_STATUSES = ["pre_reserved", "confirmed", "in_progress", "completed", "cancelled"]
CLEANING_STATUSES = ["clean", "to_clean", "cleaning", "to_check", "checked"]
UNAVAILABILITY_REASONS = ["maintenance", "works", "breakdown", "administrative", "other"]


async def _get_or_create_housing_for_room(db: AsyncSession, room_id: int) -> Housing:
    result = await db.execute(select(Housing).where(Housing.room_id == room_id))
    housing = result.scalar_one_or_none()
    if not housing:
        housing = Housing(room_id=room_id)
        db.add(housing)
        await db.flush()
    return housing


async def _get_housing_summary(db: AsyncSession, housing_id: int) -> Optional[dict]:
    result = await db.execute(
        select(Housing)
        .options(
            selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site)
        )
        .where(Housing.id == housing_id)
    )
    h = result.scalar_one_or_none()
    if not h:
        return None
    room = h.room
    building = room.building if room else None
    site = building.site if building else None
    return {
        "id": h.id,
        "room_id": h.room_id,
        "room": {"id": room.id, "reference": room.reference, "name": room.name, "area": room.area} if room else None,
        "building": {"id": building.id, "name": building.name} if building else None,
        "site": {"id": site.id, "name": site.name} if site else None,
        "housing_type": h.housing_type,
        "capacity": h.capacity,
        "beds": h.beds,
        "nb_rooms": h.nb_rooms,
        "bed_configuration": h.bed_configuration,
        "room_names": h.room_names,
        "bathrooms": h.bathrooms,
        "has_kitchen": h.has_kitchen,
        "has_balcony": h.has_balcony,
        "floor_number": h.floor_number,
        "notes": h.notes,
        "is_active": h.is_active,
        "created_at": h.created_at,
        "updated_at": h.updated_at,
    }


class HousingService:
    def __init__(self, db: AsyncSession, current_user: Optional[User] = None):
        self.db = db
        self.current_user = current_user

    async def _log_housing_status(self, housing_id: int, field: str, old_val: str, new_val: str):
        hist = HousingStatusHistory(
            housing_id=housing_id,
            field_name=field,
            old_value=old_val,
            new_value=new_val,
            changed_by=self.current_user.id if self.current_user else None,
        )
        self.db.add(hist)

    async def _log_occupancy_status(self, occupancy_id: int, old_status: str, new_status: str):
        hist = OccupancyStatusHistory(
            occupancy_id=occupancy_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=self.current_user.id if self.current_user else None,
        )
        self.db.add(hist)

    # ============================================================
    # HOUSING
    # ============================================================

    async def list_housings(self, params: dict) -> dict:
        query = (
            select(Housing)
            .options(
                selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site),
                selectinload(Housing.room).selectinload(Room.usage_type),
            )
        )
        count_query = select(func.count(Housing.id))

        if params.get("search"):
            search = f"%{params['search']}%"
            query = query.join(Housing.room).where(or_(Room.name.ilike(search), Room.reference.ilike(search)))
            count_query = count_query.join(Housing.room).where(or_(Room.name.ilike(search), Room.reference.ilike(search)))

        if params.get("is_active") is not None:
            query = query.where(Housing.is_active == params["is_active"])
            count_query = count_query.where(Housing.is_active == params["is_active"])

        if params.get("site_id"):
            query = query.join(Housing.room).join(Room.building).where(Building.site_id == params["site_id"])
            count_query = count_query.join(Housing.room).join(Room.building).where(Building.site_id == params["site_id"])

        if params.get("building_id"):
            query = query.join(Housing.room).join(Room.building).where(Room.building_id == params["building_id"])
            count_query = count_query.join(Housing.room).join(Room.building).where(Room.building_id == params["building_id"])

        if params.get("housing_type"):
            query = query.where(Housing.housing_type == params["housing_type"])
            count_query = count_query.where(Housing.housing_type == params["housing_type"])

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        sort_col = getattr(Housing, params.get("sort_by", "created_at"), Housing.created_at)
        if params.get("sort_order") == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = result.scalars().all()

        enriched = []
        for h in items:
            data = await _get_housing_summary(self.db, h.id)
            if data:
                data["current_occupancy"] = await self._get_current_occupancy_status(h.id)
                data["cleaning_status"] = await self._get_cleaning_status(h.id)
                enriched.append(data)

        return {
            "items": enriched,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def get_housing(self, housing_id: int) -> Optional[dict]:
        data = await _get_housing_summary(self.db, housing_id)
        if data:
            data["current_occupancy"] = await self._get_current_occupancy_status(housing_id)
            data["cleaning_status"] = await self._get_cleaning_status(housing_id)
        return data

    async def create_housing(self, data: dict) -> dict:
        housing = Housing(**data)
        self.db.add(housing)

        room_id = data.get("room_id")
        if room_id:
            result = await self.db.execute(select(Room).where(Room.id == room_id))
            room = result.scalar_one_or_none()
            if room and not room.used_for_accommodation:
                room.used_for_accommodation = True

        await self.db.flush()
        return await _get_housing_summary(self.db, housing.id)

    async def update_housing(self, housing_id: int, data: dict) -> Optional[dict]:
        result = await self.db.execute(select(Housing).where(Housing.id == housing_id))
        housing = result.scalar_one_or_none()
        if not housing:
            return None
        for k, v in data.items():
            if hasattr(housing, k) and v is not None:
                old_val = str(getattr(housing, k))
                setattr(housing, k, v)
                await self._log_housing_status(housing_id, k, old_val, str(v))
        await self.db.flush()
        await self.db.commit()
        return await _get_housing_summary(self.db, housing_id)

    async def _get_current_occupancy_status(self, housing_id: int) -> Optional[str]:
        now = datetime.utcnow()
        result = await self.db.execute(
            select(Occupancy.status).where(
                Occupancy.housing_id == housing_id,
                Occupancy.status.in_(["confirmed", "in_progress"]),
                Occupancy.arrival_date <= now,
                Occupancy.departure_date >= now,
            )
        )
        row = result.scalar_one_or_none()
        return row

    async def _get_cleaning_status(self, housing_id: int) -> Optional[str]:
        now = datetime.utcnow()
        result = await self.db.execute(
            select(Occupancy.status).where(
                Occupancy.housing_id == housing_id,
                Occupancy.status == "completed",
            ).order_by(Occupancy.actual_departure.desc()).limit(1)
        )
        last_completed = result.scalar_one_or_none()
        if last_completed:
            return "to_clean"
        return "clean"

    # ============================================================
    # OCCUPANTS
    # ============================================================

    async def list_occupants(self, params: dict) -> dict:
        query = select(Occupant)
        count_query = select(func.count(Occupant.id))

        if params.get("search"):
            search = f"%{params['search']}%"
            q = or_(Occupant.first_name.ilike(search), Occupant.last_name.ilike(search), Occupant.email.ilike(search))
            query = query.where(q)
            count_query = count_query.where(q)

        if params.get("is_active") is not None:
            query = query.where(Occupant.is_active == params["is_active"])
            count_query = count_query.where(Occupant.is_active == params["is_active"])

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        sort_col = getattr(Occupant, params.get("sort_by", "last_name"), Occupant.last_name)
        if params.get("sort_order") == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": [OccupantResponse.model_validate(i, from_attributes=True).model_dump() for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def get_occupant(self, occupant_id: int) -> Optional[dict]:
        result = await self.db.execute(select(Occupant).where(Occupant.id == occupant_id))
        o = result.scalar_one_or_none()
        if not o:
            return None
        return OccupantResponse.model_validate(o, from_attributes=True).model_dump()

    async def create_occupant(self, data: dict) -> dict:
        data = {
            **data,
            "first_name": data["first_name"].strip(),
            "last_name": data["last_name"].strip().upper(),
            "email": data["email"].strip(),
            "phone": data["phone"].strip(),
        }
        if not all(data[field] for field in ("first_name", "last_name", "email", "phone")):
            raise HTTPException(status_code=422, detail="Nom, prénom, téléphone et email sont obligatoires")

        duplicate = await self.db.execute(
            select(Occupant.id).where(
                func.upper(Occupant.last_name) == data["last_name"],
                func.upper(Occupant.first_name) == data["first_name"].upper(),
            ).limit(1)
        )
        if duplicate.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Un occupant porte déjà ce nom et ce prénom")

        occupant = Occupant(**data)
        self.db.add(occupant)
        try:
            await self.db.flush()
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail="Un occupant porte déjà ce nom et ce prénom") from exc
        await self.db.refresh(occupant)
        return OccupantResponse.model_validate(occupant, from_attributes=True).model_dump()

    async def update_occupant(self, occupant_id: int, data: dict) -> Optional[dict]:
        result = await self.db.execute(select(Occupant).where(Occupant.id == occupant_id))
        occupant = result.scalar_one_or_none()
        if not occupant:
            return None
        if "first_name" in data:
            data["first_name"] = data["first_name"].strip()
        if "last_name" in data:
            data["last_name"] = data["last_name"].strip().upper()
        if "email" in data:
            data["email"] = data["email"].strip()
        if "phone" in data:
            data["phone"] = data["phone"].strip()
        for k, v in data.items():
            if hasattr(occupant, k) and v is not None:
                setattr(occupant, k, v)
        await self.db.flush()
        return OccupantResponse.model_validate(occupant, from_attributes=True).model_dump()

    async def delete_occupant(self, occupant_id: int) -> bool:
        occupant = await self.db.get(Occupant, occupant_id)
        if not occupant:
            return False
        await self.db.execute(
            delete(occupancy_occupants).where(occupancy_occupants.c.occupant_id == occupant_id)
        )
        await self.db.delete(occupant)
        await self.db.commit()
        return True

    # ============================================================
    # OCCUPANCIES
    # ============================================================

    async def list_occupancies(self, params: dict) -> dict:
        query = (
            select(Occupancy)
            .options(
                selectinload(Occupancy.housing).selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site),
                selectinload(Occupancy.occupants),
            )
        )
        count_query = select(func.count(Occupancy.id))

        if params.get("status"):
            query = query.where(Occupancy.status == params["status"])
            count_query = count_query.where(Occupancy.status == params["status"])

        if params.get("housing_id"):
            query = query.where(Occupancy.housing_id == params["housing_id"])
            count_query = count_query.where(Occupancy.housing_id == params["housing_id"])

        if params.get("occupant_id"):
            query = query.where(Occupancy.occupant_id == params["occupant_id"])
            count_query = count_query.where(Occupancy.occupant_id == params["occupant_id"])

        if params.get("date_from"):
            query = query.where(Occupancy.arrival_date >= datetime.combine(params["date_from"], datetime.min.time()))
            count_query = count_query.where(Occupancy.arrival_date >= datetime.combine(params["date_from"], datetime.min.time()))

        if params.get("date_to"):
            query = query.where(Occupancy.departure_date <= datetime.combine(params["date_to"], datetime.max.time()))
            count_query = count_query.where(Occupancy.departure_date <= datetime.combine(params["date_to"], datetime.max.time()))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        sort_col = getattr(Occupancy, params.get("sort_by", "arrival_date"), Occupancy.arrival_date)
        if params.get("sort_order") == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = result.scalars().all()

        enriched = []
        for o in items:
            entry = OccupancyResponse.model_validate(o, from_attributes=True).model_dump()
            if o.housing:
                entry["housing"] = await _get_housing_summary(self.db, o.housing_id)
            enriched.append(entry)

        return {
            "items": enriched,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def get_occupancy(self, occupancy_id: int) -> Optional[dict]:
        result = await self.db.execute(
            select(Occupancy)
            .options(
                selectinload(Occupancy.housing).selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site),
                selectinload(Occupancy.occupants),
            )
            .where(Occupancy.id == occupancy_id)
        )
        o = result.scalar_one_or_none()
        if not o:
            return None
        entry = OccupancyResponse.model_validate(o, from_attributes=True).model_dump()
        if o.housing:
            entry["housing"] = await _get_housing_summary(self.db, o.housing_id)
        return entry

    async def create_occupancy(self, data: dict) -> dict:
        if self.current_user:
            data["created_by"] = self.current_user.id
        occupancy = Occupancy(**data)
        self.db.add(occupancy)
        await self.db.flush()

        await self._log_occupancy_status(occupancy.id, None, occupancy.status)
        await self.db.commit()

        return await self.get_occupancy(occupancy.id)

    async def update_occupancy(self, occupancy_id: int, data: dict) -> Optional[dict]:
        result = await self.db.execute(select(Occupancy).where(Occupancy.id == occupancy_id))
        occupancy = result.scalar_one_or_none()
        if not occupancy:
            return None
        for k, v in data.items():
            if hasattr(occupancy, k) and v is not None:
                setattr(occupancy, k, v)
        await self.db.flush()
        return await self.get_occupancy(occupancy_id)

    async def delete_occupancy(self, occupancy_id: int) -> bool:
        occupancy = await self.db.get(Occupancy, occupancy_id)
        if not occupancy:
            return False

        await self.db.execute(
            delete(occupancy_occupants).where(occupancy_occupants.c.occupancy_id == occupancy_id)
        )
        await self.db.execute(delete(Cleaning).where(Cleaning.occupancy_id == occupancy_id))
        await self.db.execute(
            delete(OccupancyStatusHistory).where(OccupancyStatusHistory.occupancy_id == occupancy_id)
        )
        await self.db.execute(
            EmailLog.__table__.update()
            .where(EmailLog.occupancy_id == occupancy_id)
            .values(occupancy_id=None)
        )
        await self.db.delete(occupancy)
        await self.db.commit()
        return True

    async def change_occupancy_status(self, occupancy_id: int, new_status: str) -> Optional[dict]:
        result = await self.db.execute(select(Occupancy).where(Occupancy.id == occupancy_id))
        occupancy = result.scalar_one_or_none()
        if not occupancy:
            return None

        old_status = occupancy.status

        if new_status == "confirmed" and old_status != "confirmed":
            if occupancy.arrival_date.date() < date.today():
                raise HTTPException(status_code=400, detail="Une réservation ne peut pas commencer dans le passé")
            if occupancy.departure_date < occupancy.arrival_date:
                raise HTTPException(status_code=400, detail="La date de départ doit être postérieure à la date d'arrivée")

            overlap_query = select(Occupancy.id).where(
                Occupancy.id != occupancy_id,
                Occupancy.housing_id == occupancy.housing_id,
                Occupancy.status.in_(["pre_reserved", "confirmed", "in_progress"]),
                Occupancy.arrival_date <= occupancy.departure_date,
                Occupancy.departure_date >= occupancy.arrival_date,
            )
            if occupancy.room_index is None or occupancy.room_index == 0:
                overlap_query = overlap_query.where(
                    or_(Occupancy.room_index == occupancy.room_index, Occupancy.room_index.is_(None))
                )
            else:
                overlap_query = overlap_query.where(Occupancy.room_index == occupancy.room_index)
            if (await self.db.execute(overlap_query.limit(1))).scalar_one_or_none() is not None:
                raise HTTPException(status_code=409, detail="Cette période chevauche déjà une réservation")

        occupancy.status = new_status

        if new_status == "cancelled":
            cleaning_result = await self.db.execute(
                select(Cleaning).where(
                    Cleaning.occupancy_id == occupancy.id,
                    Cleaning.status.in_(["not_planned", "in_progress", "planned"]),
                ).order_by(Cleaning.id.desc()).limit(1)
            )
            cleaning = cleaning_result.scalar_one_or_none()
            if cleaning:
                await self.cancel_cleaning(cleaning.id)

        if new_status == "confirmed" and old_status != "confirmed":
            cleaning_result = await self.db.execute(
                select(Cleaning.id).where(Cleaning.occupancy_id == occupancy.id).limit(1)
            )
            if cleaning_result.scalar_one_or_none() is None:
                scheduled_date = occupancy.departure_date.date() + timedelta(days=1)
                while scheduled_date.weekday() >= 5:
                    scheduled_date += timedelta(days=1)
                self.db.add(Cleaning(
                    housing_id=occupancy.housing_id,
                    occupancy_id=occupancy.id,
                    type="exit",
                    status="not_planned",
                    scheduled_date=scheduled_date,
                    volunteers_needed=1,
                    invitation_status="not_sent",
                    created_by=self.current_user.id if self.current_user else None,
                ))

        if new_status == "in_progress" and not occupancy.actual_arrival:
            occupancy.actual_arrival = datetime.utcnow()
        elif new_status == "completed" and not occupancy.actual_departure:
            occupancy.actual_departure = datetime.utcnow()

        await self._log_occupancy_status(occupancy_id, old_status, new_status)
        await self.db.commit()
        return await self.get_occupancy(occupancy_id)

    # ============================================================
    # UNAVAILABILITIES
    # ============================================================

    async def list_unavailabilities(self, params: dict) -> dict:
        query = select(Unavailability).options(selectinload(Unavailability.housing).selectinload(Housing.room))
        count_query = select(func.count(Unavailability.id))

        if params.get("housing_id"):
            query = query.where(Unavailability.housing_id == params["housing_id"])
            count_query = count_query.where(Unavailability.housing_id == params["housing_id"])

        if params.get("reason"):
            query = query.where(Unavailability.reason == params["reason"])
            count_query = count_query.where(Unavailability.reason == params["reason"])

        if params.get("date_from"):
            query = query.where(Unavailability.end_date >= params["date_from"])
            count_query = count_query.where(Unavailability.end_date >= params["date_from"])

        if params.get("date_to"):
            query = query.where(Unavailability.start_date <= params["date_to"])
            count_query = count_query.where(Unavailability.start_date <= params["date_to"])

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        sort_col = getattr(Unavailability, params.get("sort_by", "start_date"), Unavailability.start_date)
        if params.get("sort_order") == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": [UnavailabilityResponse.model_validate(u, from_attributes=True).model_dump() for u in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def create_unavailability(self, data: dict) -> dict:
        if self.current_user:
            data["created_by"] = self.current_user.id
        unavail = Unavailability(**data)
        self.db.add(unavail)
        await self.db.flush()
        return UnavailabilityResponse.model_validate(unavail, from_attributes=True).model_dump()

    async def delete_unavailability(self, unavail_id: int) -> bool:
        result = await self.db.execute(select(Unavailability).where(Unavailability.id == unavail_id))
        unavail = result.scalar_one_or_none()
        if not unavail:
            return False
        await self.db.delete(unavail)
        return True

    # ============================================================
    # DASHBOARD
    # ============================================================

    async def get_dashboard(self) -> dict:
        today = date.today()
        now = datetime.utcnow()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        total_result = await self.db.execute(select(func.count(Housing.id)).where(Housing.is_active == True))
        total_housings = total_result.scalar() or 0

        occupied_result = await self.db.execute(
            select(func.count(func.distinct(Occupancy.housing_id))).where(
                Occupancy.status.in_(["confirmed", "in_progress"]),
                Occupancy.arrival_date <= now,
                Occupancy.departure_date >= now,
            )
        )
        occupied = occupied_result.scalar() or 0

        arrivals_result = await self.db.execute(
            select(func.count(Occupancy.id)).where(
                Occupancy.status.in_(["confirmed", "in_progress"]),
                func.date(Occupancy.arrival_date) == today,
            )
        )
        arrivals_today = arrivals_result.scalar() or 0

        departures_result = await self.db.execute(
            select(func.count(Occupancy.id)).where(
                Occupancy.status.in_(["confirmed", "in_progress", "completed"]),
                func.date(Occupancy.departure_date) == today,
            )
        )
        departures_today = departures_result.scalar() or 0

        return {
            "total_housings": total_housings,
            "occupied": occupied,
            "free": max(0, total_housings - occupied),
            "arrivals_today": arrivals_today,
            "departures_today": departures_today,
            "to_clean": 0,
            "unavailabilities": 0,
            "occupancy_rate": round((occupied / total_housings * 100) if total_housings > 0 else 0, 1),
        }

    # ============================================================
    # QUICK OCCUPANT CREATION
    # ============================================================

    async def create_occupant_quick(self, data: dict) -> dict:
        occupant = Occupant(**data)
        self.db.add(occupant)
        await self.db.flush()
        return OccupantResponse.model_validate(occupant, from_attributes=True).model_dump()

    # ============================================================
    # CLEANING
    # ============================================================

    async def list_cleanings(self, params: dict) -> dict:
        query = select(Cleaning).options(
                selectinload(Cleaning.housing).selectinload(Housing.room).selectinload(Room.building),
                selectinload(Cleaning.occupancy).selectinload(Occupancy.occupants),
                selectinload(Cleaning.assigned_user),
                selectinload(Cleaning.volunteers),
                selectinload(Cleaning.invitation_logs).selectinload(CleaningInvitationLog.volunteer),
        )
        count_query = select(func.count(Cleaning.id))

        if params.get("housing_id"):
            query = query.where(Cleaning.housing_id == params["housing_id"])
            count_query = count_query.where(Cleaning.housing_id == params["housing_id"])

        if params.get("occupancy_id"):
            query = query.where(Cleaning.occupancy_id == params["occupancy_id"])
            count_query = count_query.where(Cleaning.occupancy_id == params["occupancy_id"])

        if params.get("type"):
            query = query.where(Cleaning.type == params["type"])
            count_query = count_query.where(Cleaning.type == params["type"])

        if params.get("status"):
            query = query.where(Cleaning.status == params["status"])
            count_query = count_query.where(Cleaning.status == params["status"])

        if params.get("date_from"):
            query = query.where(Cleaning.scheduled_date >= params["date_from"])
            count_query = count_query.where(Cleaning.scheduled_date >= params["date_from"])

        if params.get("date_to"):
            query = query.where(Cleaning.scheduled_date <= params["date_to"])
            count_query = count_query.where(Cleaning.scheduled_date <= params["date_to"])

        if params.get("assigned_to"):
            query = query.where(Cleaning.assigned_to == params["assigned_to"])
            count_query = count_query.where(Cleaning.assigned_to == params["assigned_to"])

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        sort_col = getattr(Cleaning, params.get("sort_by", "scheduled_date"), Cleaning.scheduled_date)
        if params.get("sort_order") == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": [CleaningResponse.model_validate(i, from_attributes=True).model_dump() for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def get_cleaning(self, cleaning_id: int) -> Optional[dict]:
        result = await self.db.execute(
            select(Cleaning)
            .options(
                selectinload(Cleaning.housing).selectinload(Housing.room).selectinload(Room.building),
                selectinload(Cleaning.occupancy).selectinload(Occupancy.occupants),
                selectinload(Cleaning.assigned_user),
                selectinload(Cleaning.volunteers),
                selectinload(Cleaning.invitation_logs).selectinload(CleaningInvitationLog.volunteer),
            )
            .where(Cleaning.id == cleaning_id)
        )
        c = result.scalar_one_or_none()
        if not c:
            return None
        data = CleaningResponse.model_validate(c, from_attributes=True).model_dump()
        try:
            selected_volunteer_ids = json.loads(c.selected_volunteer_ids_json or "[]")
        except (TypeError, ValueError):
            selected_volunteer_ids = []
        data["selected_volunteer_ids"] = selected_volunteer_ids
        selected_ids = set(selected_volunteer_ids)
        data["invitation_history"] = [
            {
                "id": log.id,
                "volunteer_id": log.volunteer_id,
                "volunteer_name": f"{log.volunteer.first_name} {log.volunteer.last_name}",
                "channel": log.channel,
                "status": log.status,
                "availability_response": log.availability_response,
                "response_at": log.response_at,
                "selected": log.volunteer_id in selected_ids,
                "message": log.message,
                "sent_at": log.sent_at,
            }
            for log in c.invitation_logs
        ]
        return data

    async def confirm_cleaning_volunteers(self, cleaning_id: int, volunteer_ids: list[int]) -> dict:
        result = await self.db.execute(
            select(Cleaning).options(
                selectinload(Cleaning.volunteers),
                selectinload(Cleaning.occupancy),
                selectinload(Cleaning.invitation_logs).selectinload(CleaningInvitationLog.volunteer),
                selectinload(Cleaning.housing).selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site),
            ).where(Cleaning.id == cleaning_id)
        )
        cleaning = result.scalar_one_or_none()
        if not cleaning:
            raise HTTPException(status_code=404, detail="Ménage non trouvé")
        if len(volunteer_ids) != cleaning.volunteers_needed:
            raise HTTPException(
                status_code=400,
                detail=f"Sélectionnez exactement {cleaning.volunteers_needed} volontaire(s)",
            )

        latest_responses = {}
        for log in sorted(cleaning.invitation_logs, key=lambda item: item.sent_at.timestamp() if item.sent_at else 0):
            if log.availability_response:
                latest_responses[log.volunteer_id] = log.availability_response
        available_ids = {volunteer_id for volunteer_id, response in latest_responses.items() if response == "available"}
        if not set(volunteer_ids).issubset(available_ids):
            raise HTTPException(status_code=400, detail="Seuls les volontaires disponibles peuvent être retenus")

        volunteers_result = await self.db.execute(
            select(Volunteer).where(Volunteer.id.in_(volunteer_ids), Volunteer.is_active.is_(True))
        )
        volunteers = list(volunteers_result.scalars().all())
        if len(volunteers) != len(set(volunteer_ids)):
            raise HTTPException(status_code=400, detail="Un ou plusieurs volontaires sont introuvables")

        if len(volunteer_ids) != len(set(volunteer_ids)):
            raise HTTPException(status_code=400, detail="Un volontaire ne peut être sélectionné qu'une seule fois")
        cleaning.selected_volunteer_ids_json = json.dumps(volunteer_ids)
        cleaning.status = "planned"
        room = cleaning.housing.room if cleaning.housing else None
        building = room.building if room else None
        site = building.site if building else None
        housing_name = room.name if room else "le logement"
        template_result = await self.db.execute(
            select(EmailTemplate).options(
                selectinload(EmailTemplate.attachments).selectinload(EmailTemplateAttachment.housings)
            ).where(
                EmailTemplate.template_type.in_(["cleaning_confirmation", "confirmation"]),
                EmailTemplate.is_active.is_(True),
            ).order_by(
                case((EmailTemplate.template_type == "cleaning_confirmation", 0), else_=1),
                EmailTemplate.is_default.desc(),
                EmailTemplate.id.asc(),
            ).limit(1)
        )
        template = template_result.scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=400, detail="Configurez un modèle de confirmation ménage avant de retenir les volontaires")

        not_selected_volunteers = [
            volunteer for volunteer in cleaning.volunteers
            if volunteer.id in available_ids - set(volunteer_ids)
            and volunteer.email
            and volunteer.communication_preference in ("email", "both")
        ]
        not_selected_template = None
        if not_selected_volunteers:
            not_selected_template_result = await self.db.execute(
                select(EmailTemplate).options(
                    selectinload(EmailTemplate.attachments).selectinload(EmailTemplateAttachment.housings)
                ).where(
                    EmailTemplate.template_type == "cleaning_not_selected",
                    EmailTemplate.is_active.is_(True),
                ).order_by(
                    EmailTemplate.is_default.desc(),
                    EmailTemplate.id.asc(),
                ).limit(1)
            )
            not_selected_template = not_selected_template_result.scalar_one_or_none()
            if not not_selected_template:
                raise HTTPException(status_code=400, detail="Configurez un modèle pour les volontaires non retenus")

        sent_count = 0
        sms_messages = []
        for volunteer in volunteers:
            volunteer_context = {
                "housing_name": housing_name,
                "housing_reference": room.reference if room else "",
                "building_name": building.name if building else "",
                "site_name": site.name if site else "",
                "room_index": cleaning.occupancy.room_index if cleaning.occupancy else 0,
                "scheduled_date": cleaning.scheduled_date.strftime("%d/%m/%Y"),
                "cleaning_date": cleaning.scheduled_date.strftime("%d/%m/%Y"),
                "volunteers_needed": cleaning.volunteers_needed,
                "volunteer_first_name": volunteer.first_name,
                "volunteer_last_name": volunteer.last_name,
                "volunteer_email": volunteer.email or "",
            }
            subject = Template(template.subject).render(**volunteer_context)
            html_body, body = self._render_email_template(template, volunteer_context)
            if volunteer.email and volunteer.communication_preference in ("email", "both"):
                try:
                    await self._send_email(
                        volunteer.email,
                        subject,
                        body,
                        html_body,
                        self._select_email_attachments(template, cleaning.housing_id),
                    )
                    sent_count += 1
                except Exception:
                    pass
            if volunteer.phone and volunteer.communication_preference in ("sms", "both"):
                sms_messages.append({"phone": volunteer.phone, "message": body})

        not_selected_sent_count = 0
        for volunteer in not_selected_volunteers:
            volunteer_context = {
                "housing_name": housing_name,
                "housing_reference": room.reference if room else "",
                "building_name": building.name if building else "",
                "site_name": site.name if site else "",
                "room_index": cleaning.occupancy.room_index if cleaning.occupancy else 0,
                "scheduled_date": cleaning.scheduled_date.strftime("%d/%m/%Y"),
                "cleaning_date": cleaning.scheduled_date.strftime("%d/%m/%Y"),
                "volunteers_needed": cleaning.volunteers_needed,
                "volunteer_first_name": volunteer.first_name,
                "volunteer_last_name": volunteer.last_name,
                "volunteer_email": volunteer.email or "",
            }
            subject = Template(not_selected_template.subject).render(**volunteer_context)
            html_body, body = self._render_email_template(not_selected_template, volunteer_context)
            try:
                await self._send_email(
                    volunteer.email,
                    subject,
                    body,
                    html_body,
                    self._select_email_attachments(not_selected_template, cleaning.housing_id),
                )
                not_selected_sent_count += 1
            except Exception:
                pass

        await self.db.commit()
        return {
            "message": f"{sent_count} confirmation(s) e-mail envoyée(s), {not_selected_sent_count} message(s) envoyé(s) aux volontaires non retenus et {len(sms_messages)} SMS prêt(s)",
            "selected_volunteer_ids": volunteer_ids,
            "sms_messages": sms_messages,
        }

    async def create_cleaning(self, data: dict) -> dict:
        occupancy_id = data.get("occupancy_id")
        scheduled_date = data.get("scheduled_date")
        if scheduled_date:
            await self._validate_cleaning_schedule(data["housing_id"], scheduled_date, occupancy_id)
        if self.current_user:
            data["created_by"] = self.current_user.id
        cleaning = Cleaning(**data)
        self.db.add(cleaning)
        await self.db.flush()
        await self.db.commit()
        return await self.get_cleaning(cleaning.id)

    async def update_cleaning(self, cleaning_id: int, data: dict) -> Optional[dict]:
        result = await self.db.execute(
            select(Cleaning).options(selectinload(Cleaning.occupancy)).where(Cleaning.id == cleaning_id)
        )
        cleaning = result.scalar_one_or_none()
        if not cleaning:
            return None
        scheduled_date = data.get("scheduled_date")
        if scheduled_date:
            await self._validate_cleaning_schedule(
                data.get("housing_id", cleaning.housing_id),
                scheduled_date,
                data.get("occupancy_id", cleaning.occupancy_id),
            )
        for k, v in data.items():
            if hasattr(cleaning, k) and v is not None:
                setattr(cleaning, k, v)
        await self.db.flush()
        await self.db.commit()
        return await self.get_cleaning(cleaning_id)

    async def _validate_cleaning_schedule(
        self,
        housing_id: int,
        scheduled_date: date,
        occupancy_id: int | None = None,
    ) -> None:
        if scheduled_date < date.today():
            raise HTTPException(status_code=400, detail="La date du ménage ne peut pas être antérieure à aujourd’hui")

        if occupancy_id:
            occupancy_result = await self.db.execute(select(Occupancy).where(Occupancy.id == occupancy_id))
            occupancy = occupancy_result.scalar_one_or_none()
            if occupancy and scheduled_date <= occupancy.departure_date.date():
                raise HTTPException(status_code=400, detail="La date du ménage doit être après le départ de l’occupation")

        day_start = datetime.combine(scheduled_date, datetime.min.time())
        day_end = datetime.combine(scheduled_date, datetime.max.time())
        occupied_result = await self.db.execute(
            select(Occupancy.id).where(
                Occupancy.housing_id == housing_id,
                Occupancy.status != "cancelled",
                Occupancy.arrival_date <= day_end,
                Occupancy.departure_date >= day_start,
                Occupancy.id != occupancy_id,
            ).limit(1)
        )
        if occupied_result.scalar_one_or_none() is not None:
            raise HTTPException(status_code=400, detail="Le logement est occupé à cette date")

    async def delete_cleaning(self, cleaning_id: int) -> bool:
        result = await self.db.execute(select(Cleaning).where(Cleaning.id == cleaning_id))
        cleaning = result.scalar_one_or_none()
        if not cleaning:
            return False
        await self.db.delete(cleaning)
        await self.db.commit()
        return True

    async def send_cleaning_volunteer_request(
        self,
        cleaning_id: int,
        volunteer_ids: list[int],
        channel: str,
        template_id: int | None = None,
        message: str | None = None,
        public_base_url: str = "",
    ) -> dict:
        result = await self.db.execute(
            select(Cleaning)
            .options(
                selectinload(Cleaning.volunteers),
                selectinload(Cleaning.occupancy),
                selectinload(Cleaning.housing).selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site),
            )
            .where(Cleaning.id == cleaning_id)
        )
        cleaning = result.scalar_one_or_none()
        if not cleaning:
            raise HTTPException(status_code=404, detail="Ménage non trouvé")
        if not volunteer_ids:
            raise HTTPException(status_code=400, detail="Sélectionnez au moins un volontaire")

        volunteers_result = await self.db.execute(
            select(Volunteer).where(
                Volunteer.id.in_(volunteer_ids),
                Volunteer.is_active.is_(True),
                Volunteer.usage_type.like("%cleaning%"),
            )
        )
        volunteers = list(volunteers_result.scalars().all())
        if len(volunteers) != len(set(volunteer_ids)):
            raise HTTPException(status_code=400, detail="Un ou plusieurs volontaires ne sont pas disponibles pour le ménage")

        cleaning.volunteers = volunteers
        await self.db.commit()

        room = cleaning.housing.room if cleaning.housing else None
        building = room.building if room else None
        site = building.site if building else None
        housing_name = room.name if room else "le logement"
        subject = f"Demande de ménage - {housing_name} - {cleaning.scheduled_date:%d/%m/%Y}"
        request_message = message or (
            f"Bonjour,\n\nUne intervention de ménage est demandée pour {housing_name} "
            f"le {cleaning.scheduled_date:%d/%m/%Y}. Merci d'indiquer si vous êtes disponible.\n\n"
            "Merci."
        )

        template_query = select(EmailTemplate).options(
            selectinload(EmailTemplate.attachments).selectinload(EmailTemplateAttachment.housings)
        ).where(
            EmailTemplate.template_type == "cleaning_invitation",
            EmailTemplate.is_active.is_(True),
        )
        if template_id:
            template_query = template_query.where(EmailTemplate.id == template_id)
        else:
            template_query = template_query.where(EmailTemplate.is_default.is_(True)).limit(1)
        template_result = await self.db.execute(template_query)
        template = template_result.scalar_one_or_none()
        if template_id and not template:
            raise HTTPException(status_code=400, detail="Modèle d’invitation ménage introuvable ou inactif")

        email_recipients = [
            volunteer for volunteer in volunteers
            if volunteer.email and (channel in (None, "email") and volunteer.communication_preference in ("email", "both"))
        ]
        sms_recipients = [
            volunteer for volunteer in volunteers
            if volunteer.phone and (channel in (None, "sms") and volunteer.communication_preference in ("sms", "both"))
        ]
        if email_recipients and not template:
            raise HTTPException(status_code=400, detail="Configurez un modèle d’invitation ménage avant l’envoi par e-mail")
        if not email_recipients and not sms_recipients:
            raise HTTPException(status_code=400, detail="Aucun contact ne correspond aux préférences des volontaires sélectionnés")

        template_context = {
            "housing_name": housing_name,
            "housing_reference": room.reference if room else "",
            "building_name": building.name if building else "",
            "site_name": site.name if site else "",
            "room_index": cleaning.occupancy.room_index if cleaning.occupancy else 0,
            "scheduled_date": cleaning.scheduled_date.strftime("%d/%m/%Y"),
            "cleaning_date": cleaning.scheduled_date.strftime("%d/%m/%Y"),
            "volunteers_needed": cleaning.volunteers_needed,
        }
        rendered_subject = template.subject if template else subject
        rendered_html = template.body_html if template else None
        rendered_body = (template.body_text or template.body_html) if template else request_message

        sent_count = 0
        sms_messages = []
        for volunteer in email_recipients:
                log = CleaningInvitationLog(
                    cleaning_id=cleaning.id,
                    volunteer_id=volunteer.id,
                    channel="email",
                    status="pending",
                    message=rendered_body,
                )
                self.db.add(log)
                await self.db.flush()
                available_url = f"{public_base_url}/housing/public/cleaning-invitations/{log.response_token}?response=available"
                unavailable_url = f"{public_base_url}/housing/public/cleaning-invitations/{log.response_token}?response=unavailable"
                try:
                    volunteer_context = {
                        **template_context,
                        "volunteer_first_name": volunteer.first_name,
                        "volunteer_last_name": volunteer.last_name,
                        "volunteer_email": volunteer.email,
                        "available_url": available_url,
                        "unavailable_url": unavailable_url,
                    }
                    email_subject = Template(rendered_subject).render(**volunteer_context)
                    email_html, email_body = self._render_email_template(template, volunteer_context) if template else (None, rendered_body)
                    email_body = f"{email_body}\n\nDisponible : {available_url}\nPas disponible : {unavailable_url}"
                    response_actions = (
                        '<div style="margin-top:24px;padding:16px;border:1px solid #d9e2ec;'
                        'border-radius:8px;font-family:Arial,sans-serif;">'
                        '<p style="margin:0 0 12px;font-weight:600;">Pouvez-vous assurer ce ménage ?</p>'
                        f'<a href="{available_url}" style="display:inline-block;margin-right:8px;'
                        'padding:14px 24px;background:#198754;color:#fff;text-decoration:none;'
                        'font-size:16px;font-weight:700;border-radius:5px;">Je suis disponible</a>'
                        f'<a href="{unavailable_url}" style="display:inline-block;'
                        'padding:14px 24px;background:#dc3545;color:#fff;text-decoration:none;'
                        'font-size:16px;font-weight:700;border-radius:5px;">'
                        'Je ne suis pas disponible</a></div>'
                    )
                    email_html = email_html or f"<p>{email_body}</p>"
                    closing_tag = "</body>"
                    closing_index = email_html.lower().rfind(closing_tag)
                    if closing_index < 0:
                        closing_tag = "</html>"
                        closing_index = email_html.lower().rfind(closing_tag)
                    if closing_index >= 0:
                        email_html = email_html[:closing_index] + response_actions + email_html[closing_index:]
                    else:
                        email_html += response_actions
                    log.message = email_body
                    await self._send_email(
                        volunteer.email,
                        email_subject,
                        email_body,
                        email_html,
                        self._select_email_attachments(template, cleaning.housing_id) if template else [],
                    )
                    log.status = "sent"
                    sent_count += 1
                except Exception as exc:
                    log.status = "failed"
                    log.message = f"{rendered_body}\n\nErreur: {exc}"
        phones = [volunteer.phone for volunteer in sms_recipients]
        for volunteer in sms_recipients:
            log = CleaningInvitationLog(
                cleaning_id=cleaning.id,
                volunteer_id=volunteer.id,
                channel="sms",
                status="prepared",
                message=rendered_body,
            )
            self.db.add(log)
            await self.db.flush()
            available_url = f"{public_base_url}/housing/public/cleaning-invitations/{log.response_token}?response=available"
            unavailable_url = f"{public_base_url}/housing/public/cleaning-invitations/{log.response_token}?response=unavailable"
            sms_messages.append({
                "phone": volunteer.phone,
                "message": f"{request_message}\n\nDisponible : {available_url}\nPas disponible : {unavailable_url}",
            })
            log.message = sms_messages[-1]["message"]
        invitation_sent = bool(sent_count or phones)
        cleaning.invitation_status = "sent" if invitation_sent else "not_sent"
        if invitation_sent:
            cleaning.status = "in_progress"
        await self.db.commit()
        channels = []
        if sent_count:
            channels.append(f"{sent_count} e-mail(s)")
        if phones:
            channels.append(f"{len(phones)} SMS prêt(s)")
        return {
            "message": "Demande envoyée : " + " et ".join(channels),
            "channel": "mixed" if sent_count and phones else ("email" if sent_count else "sms"),
            "status": cleaning.status,
            "phones": phones,
            "sms_message": sms_messages[0]["message"] if len(sms_messages) == 1 else request_message,
            "sms_messages": sms_messages,
        }

    async def cancel_cleaning(self, cleaning_id: int) -> dict:
        result = await self.db.execute(
            select(Cleaning).options(
                selectinload(Cleaning.volunteers),
                selectinload(Cleaning.housing).selectinload(Housing.room),
            ).where(Cleaning.id == cleaning_id)
        )
        cleaning = result.scalar_one_or_none()
        if not cleaning:
            raise HTTPException(status_code=404, detail="Ménage non trouvé")
        if cleaning.status == "not_planned":
            cleaning.status = "cancelled"
            await self.db.commit()
            return {
                "message": "Ménage annulé",
                "phones": [],
                "sms_message": "",
            }

        template_result = await self.db.execute(
            select(EmailTemplate).options(
                selectinload(EmailTemplate.attachments).selectinload(EmailTemplateAttachment.housings)
            ).where(
                EmailTemplate.template_type.in_(["cleaning_cancellation", "cancellation"]),
                EmailTemplate.is_active.is_(True),
            ).order_by(
                case((EmailTemplate.template_type == "cleaning_cancellation", 0), else_=1),
                EmailTemplate.is_default.desc(),
                EmailTemplate.id.asc(),
            ).limit(1)
        )
        template = template_result.scalar_one_or_none()
        housing_name = cleaning.housing.room.name if cleaning.housing and cleaning.housing.room else "le logement"
        try:
            selected_volunteer_ids = set(json.loads(cleaning.selected_volunteer_ids_json or "[]"))
        except (TypeError, ValueError):
            selected_volunteer_ids = set()
        confirmed_volunteers = [
            volunteer for volunteer in cleaning.volunteers
            if volunteer.id in selected_volunteer_ids
        ]
        context = {
            "housing_name": housing_name,
            "scheduled_date": cleaning.scheduled_date.strftime("%d/%m/%Y"),
            "cleaning_date": cleaning.scheduled_date.strftime("%d/%m/%Y"),
        }
        phones = []
        sent_count = 0
        for volunteer in confirmed_volunteers:
            preference = volunteer.communication_preference
            if volunteer.email and preference in ("email", "both") and template:
                volunteer_context = {
                    **context,
                    "volunteer_first_name": volunteer.first_name,
                    "volunteer_last_name": volunteer.last_name,
                    "volunteer_email": volunteer.email,
                }
                html_body, text_body = self._render_email_template(template, volunteer_context)
                log = CleaningInvitationLog(
                    cleaning_id=cleaning.id,
                    volunteer_id=volunteer.id,
                    channel="email",
                    status="pending",
                    message=text_body,
                )
                self.db.add(log)
                try:
                    await self._send_email(
                        volunteer.email,
                        Template(template.subject).render(**volunteer_context),
                        text_body,
                        html_body,
                        self._select_email_attachments(template, cleaning.housing_id),
                    )
                    log.status = "sent"
                    sent_count += 1
                except Exception as exc:
                    log.status = "failed"
                    log.message = f"{text_body}\n\nErreur: {exc}"
            if volunteer.phone and preference in ("sms", "both"):
                phones.append(volunteer.phone)
                self.db.add(CleaningInvitationLog(
                    cleaning_id=cleaning.id,
                    volunteer_id=volunteer.id,
                    channel="sms",
                    status="prepared",
                    message=f"Annulation du ménage prévu le {cleaning.scheduled_date:%d/%m/%Y}.",
                ))

        # Keep the cancelled cleaning as history, but hide it from the active planning.
        cleaning.status = "cancelled"
        await self.db.commit()
        if not template and any(v.email and v.communication_preference in ("email", "both") for v in confirmed_volunteers):
            message = "Ménage annulé, mais aucun modèle d’annulation ménage par défaut n’est configuré"
        else:
            message = f"Ménage annulé. {sent_count} e-mail(s) envoyé(s)"
        return {"message": message, "phones": phones, "sms_message": f"Le ménage du {cleaning.scheduled_date:%d/%m/%Y} à {housing_name} est annulé."}

    # ============================================================
    # EMAIL TEMPLATES
    # ============================================================

    async def list_email_templates(self, params: dict) -> dict:
        query = select(EmailTemplate).options(
            selectinload(EmailTemplate.attachments).selectinload(EmailTemplateAttachment.housings)
        )
        count_query = select(func.count(EmailTemplate.id))

        if params.get("template_type"):
            query = query.where(EmailTemplate.template_type == params["template_type"])
            count_query = count_query.where(EmailTemplate.template_type == params["template_type"])

        if params.get("is_active") is not None:
            query = query.where(EmailTemplate.is_active == params["is_active"])
            count_query = count_query.where(EmailTemplate.is_active == params["is_active"])

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        sort_col = getattr(EmailTemplate, params.get("sort_by", "name"), EmailTemplate.name)
        if params.get("sort_order") == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": [self._email_template_response(i) for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def get_email_template(self, template_id: int) -> Optional[dict]:
        result = await self.db.execute(
            select(EmailTemplate)
            .options(selectinload(EmailTemplate.attachments).selectinload(EmailTemplateAttachment.housings))
            .where(EmailTemplate.id == template_id)
        )
        t = result.scalar_one_or_none()
        if not t:
            return None
        return self._email_template_response(t)

    @staticmethod
    def _email_template_response(template: EmailTemplate) -> dict:
        data = EmailTemplateResponse.model_validate(template, from_attributes=True).model_dump()
        data["attachments"] = [
            {
                **EmailTemplateAttachmentResponse.model_validate(attachment, from_attributes=True).model_dump(),
                "housing_ids": [housing.id for housing in attachment.housings],
            }
            for attachment in template.attachments
        ]
        return data

    async def create_email_template(self, data: dict) -> dict:
        if self.current_user:
            data["created_by"] = self.current_user.id
        template = EmailTemplate(**data)
        self.db.add(template)
        await self.db.flush()
        await self.db.commit()
        return await self.get_email_template(template.id)

    async def update_email_template(self, template_id: int, data: dict) -> Optional[dict]:
        result = await self.db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
        template = result.scalar_one_or_none()
        if not template:
            return None
        for k, v in data.items():
            if hasattr(template, k) and v is not None:
                setattr(template, k, v)
        await self.db.flush()
        await self.db.commit()
        return await self.get_email_template(template_id)

    async def delete_email_template(self, template_id: int) -> bool:
        result = await self.db.execute(
            select(EmailTemplate)
            .options(selectinload(EmailTemplate.attachments))
            .where(EmailTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            return False

        for attachment in template.attachments:
            if os.path.exists(attachment.file_path):
                os.remove(attachment.file_path)
        await self.db.delete(template)
        await self.db.commit()
        return True

    async def upload_email_template_attachment(self, template_id: int, file: UploadFile, housing_ids: List[int] | None = None) -> dict:
        import os
        from uuid import uuid4
        
        template = await self.get_email_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Modèle email non trouvé")
        
        upload_dir = os.getenv("UPLOAD_DIR", "/app/uploads/email_templates")
        os.makedirs(upload_dir, exist_ok=True)
        
        ext = os.path.splitext(file.filename)[1] if file.filename else ""
        unique_name = f"{uuid4().hex}{ext}"
        file_path = os.path.join(upload_dir, unique_name)
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        attachment = EmailTemplateAttachment(
            template_id=template_id,
            filename=file.filename,
            file_path=file_path,
            mime_type=file.content_type,
            file_size=len(content),
        )
        if housing_ids:
            housing_result = await self.db.execute(select(Housing).where(Housing.id.in_(housing_ids)))
            attachment.housings = list(housing_result.scalars().all())
        self.db.add(attachment)
        await self.db.flush()
        await self.db.commit()
        
        return {
            **EmailTemplateAttachmentResponse.model_validate(attachment, from_attributes=True).model_dump(),
            "housing_ids": [housing.id for housing in attachment.housings],
        }

    async def update_email_template_attachment_housings(self, attachment_id: int, housing_ids: List[int]) -> Optional[dict]:
        result = await self.db.execute(
            select(EmailTemplateAttachment).options(selectinload(EmailTemplateAttachment.housings)).where(EmailTemplateAttachment.id == attachment_id)
        )
        attachment = result.scalar_one_or_none()
        if not attachment:
            return None
        housing_result = await self.db.execute(select(Housing).where(Housing.id.in_(housing_ids))) if housing_ids else None
        attachment.housings = list(housing_result.scalars().all()) if housing_result else []
        await self.db.commit()
        return {
            **EmailTemplateAttachmentResponse.model_validate(attachment, from_attributes=True).model_dump(),
            "housing_ids": [housing.id for housing in attachment.housings],
        }

    async def delete_email_template_attachment(self, attachment_id: int) -> bool:
        result = await self.db.execute(select(EmailTemplateAttachment).where(EmailTemplateAttachment.id == attachment_id))
        attachment = result.scalar_one_or_none()
        if not attachment:
            return False
        
        # Delete file from disk
        import os
        if os.path.exists(attachment.file_path):
            os.remove(attachment.file_path)
        
        await self.db.delete(attachment)
        await self.db.commit()
        return True

    # ============================================================
    # EMAIL SENDING
    # ============================================================

    async def _get_smtp_settings(self) -> dict:
        result = await self.db.execute(
            select(ModuleConfig)
            .join(Module)
            .where(Module.code == "administration", ModuleConfig.key.like("smtp_%"))
        )
        values = {config.key: config.value or "" for config in result.scalars().all()}
        return {
            "host": values.get("smtp_host", ""),
            "port": int(values.get("smtp_port", "587")),
            "username": values.get("smtp_username", ""),
            "password": values.get("smtp_password", ""),
            "use_tls": values.get("smtp_use_tls", "true").lower() == "true",
            "use_ssl": values.get("smtp_use_ssl", "false").lower() == "true",
            "from_email": values.get("smtp_from_email", ""),
            "from_name": values.get("smtp_from_name", "ForgeAI"),
        }

    async def _send_email(self, recipient: str, subject: str, body_text: str, body_html: Optional[str] = None, attachments: list[EmailTemplateAttachment] | None = None) -> None:
        smtp = await self._get_smtp_settings()
        if not smtp["host"] or not smtp["from_email"]:
            raise RuntimeError("La configuration SMTP est incomplète dans Administration")

        message = EmailMessage()
        message["From"] = f'{smtp["from_name"]} <{smtp["from_email"]}>'
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body_text)
        if body_html:
            message.add_alternative(body_html, subtype="html")
        for attachment in attachments or []:
            with open(attachment.file_path, "rb") as file_handle:
                content = file_handle.read()
            maintype, _, subtype = (attachment.mime_type or "application/octet-stream").partition("/")
            message.add_attachment(content, maintype=maintype, subtype=subtype or "octet-stream", filename=attachment.filename)

        def send() -> None:
            smtp_class = smtplib.SMTP_SSL if smtp["use_ssl"] else smtplib.SMTP
            with smtp_class(smtp["host"], smtp["port"], timeout=30) as client:
                if smtp["use_tls"] and not smtp["use_ssl"]:
                    client.starttls()
                if smtp["username"]:
                    client.login(smtp["username"], smtp["password"])
                client.send_message(message)

        await asyncio.to_thread(send)

    def _render_email_template(self, template: EmailTemplate, context: dict) -> tuple[str, str]:
        from jinja2 import Template
        html_template = Template(template.body_html)
        text_template = Template(template.body_text or template.body_html)
        return html_template.render(**context), text_template.render(**context)

    @staticmethod
    def _select_email_attachments(template: EmailTemplate, housing_id: int) -> list[EmailTemplateAttachment]:
        return [
            attachment for attachment in template.attachments
            if not attachment.housings or any(housing.id == housing_id for housing in attachment.housings)
        ]

    async def send_confirmation_email(self, occupancy_id: int, template_id: int, recipient_ids: List[int], send_to_all: bool) -> str:
        # Get occupancy with occupants
        result = await self.db.execute(
            select(Occupancy)
            .options(selectinload(Occupancy.occupants), selectinload(Occupancy.housing).selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site))
            .where(Occupancy.id == occupancy_id)
        )
        occupancy = result.scalar_one_or_none()
        if not occupancy:
            return "Occupation non trouvée"
        
        template_result = await self.db.execute(
            select(EmailTemplate).options(
                selectinload(EmailTemplate.attachments).selectinload(EmailTemplateAttachment.housings)
            )
            .where(EmailTemplate.id == template_id)
        )
        template = template_result.scalar_one_or_none()
        if not template:
            return "Modèle email non trouvé"
        
        # Determine recipients
        recipients = []
        if send_to_all:
            recipients = [o for o in occupancy.occupants if o.email]
        else:
            for o in occupancy.occupants:
                if o.id in recipient_ids and o.email:
                    recipients.append(o)
        
        if not recipients:
            return "Aucun destinataire valide"
        
        # Prepare context
        housing = occupancy.housing
        room = housing.room if housing else None
        building = room.building if room else None
        site = building.site if building else None
        
        sent_count = 0
        for occupant in recipients:
            context = {
                "occupant_first_name": occupant.first_name,
                "occupant_last_name": occupant.last_name,
                "occupant_email": occupant.email,
                "housing_name": room.name if room else "",
                "housing_reference": room.reference if room else "",
                "arrival_date": occupancy.arrival_date.strftime("%d/%m/%Y"),
                "departure_date": occupancy.departure_date.strftime("%d/%m/%Y"),
                "site_name": site.name if site else "",
                "building_name": building.name if building else "",
                "room_index": occupancy.room_index if occupancy.room_index is not None else 0,
                "nb_persons": occupancy.nb_persons,
                "guest_type": occupancy.guest_type or "",
                "purpose": occupancy.purpose or "",
                "observations": occupancy.observations or "",
            }
            
            html_body, text_body = self._render_email_template(template, context)
            rendered_subject = Template(template.subject).render(**context)
            
            # Log email
            email_log = EmailLog(
                template_id=template_id,
                occupancy_id=occupancy_id,
                recipient_email=occupant.email,
                recipient_name=f"{occupant.first_name} {occupant.last_name}",
                subject=rendered_subject,
                body_text=text_body,
                status="pending",
            )
            self.db.add(email_log)
            await self.db.flush()
            
            try:
                await self._send_email(
                    occupant.email,
                    rendered_subject,
                    text_body,
                    html_body,
                    self._select_email_attachments(template, occupancy.housing_id),
                )
                email_log.status = "sent"
                email_log.sent_at = datetime.utcnow()
                sent_count += 1
            except Exception as e:
                email_log.status = "failed"
                email_log.error_message = str(e)
            
            await self.db.commit()
        
        return f"{sent_count} email(s) envoyé(s) sur {len(recipients)} destinataire(s)"

    async def send_cancellation_email(self, occupancy_id: int) -> str:
        template_result = await self.db.execute(
            select(EmailTemplate)
            .where(
                EmailTemplate.template_type == "cancellation",
                EmailTemplate.is_active.is_(True),
            )
            .order_by(EmailTemplate.is_default.desc(), EmailTemplate.id.asc())
            .limit(1)
        )
        template = template_result.scalar_one_or_none()
        if not template:
            return "Aucun modèle d'annulation actif n'est configuré"

        occupancy_result = await self.db.execute(
            select(Occupancy)
            .options(selectinload(Occupancy.occupants))
            .where(Occupancy.id == occupancy_id)
        )
        occupancy = occupancy_result.scalar_one_or_none()
        if not occupancy:
            return "Occupation non trouvée"
        recipient_ids = [occupant.id for occupant in occupancy.occupants if occupant.email]
        if not recipient_ids:
            return "Aucun occupant ne possède d'adresse e-mail"
        return await self.send_custom_message(
            occupancy_id,
            template.subject,
            template.body_text or template.body_html,
            recipient_ids,
            template.id,
            [],
            template.body_html,
        )

    async def send_custom_message(self, occupancy_id: int, subject: str, body_text: str, 
                                  recipient_ids: List[int], template_id: Optional[int], 
                                  attachment_ids: List[int], body_html: Optional[str] = None) -> str:
        result = await self.db.execute(
            select(Occupancy)
            .options(
                selectinload(Occupancy.occupants),
                selectinload(Occupancy.housing).selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site),
            )
            .where(Occupancy.id == occupancy_id)
        )
        occupancy = result.scalar_one_or_none()
        if not occupancy:
            return "Occupation non trouvée"

        template = None
        if template_id:
            template_result = await self.db.execute(
                select(EmailTemplate)
                .options(selectinload(EmailTemplate.attachments).selectinload(EmailTemplateAttachment.housings))
                .where(EmailTemplate.id == template_id)
            )
            template = template_result.scalar_one_or_none()
        
        recipients = [o for o in occupancy.occupants if o.id in recipient_ids and o.email]
        if not recipients:
            return "Aucun destinataire valide"
        
        sent_count = 0
        for occupant in recipients:
            rendered_subject = subject
            rendered_body = body_text
            rendered_html = body_html
            if template:
                housing = occupancy.housing
                room = housing.room if housing else None
                building = room.building if room else None
                site = building.site if building else None
                context = {
                    "occupant_first_name": occupant.first_name,
                    "occupant_last_name": occupant.last_name,
                    "occupant_email": occupant.email,
                    "housing_name": room.name if room else "",
                    "housing_reference": room.reference if room else "",
                    "arrival_date": occupancy.arrival_date.strftime("%d/%m/%Y"),
                    "departure_date": occupancy.departure_date.strftime("%d/%m/%Y"),
                    "site_name": site.name if site else "",
                    "building_name": building.name if building else "",
                    "room_index": occupancy.room_index if occupancy.room_index is not None else 0,
                    "nb_persons": occupancy.nb_persons,
                    "guest_type": occupancy.guest_type or "",
                    "purpose": occupancy.purpose or "",
                    "observations": occupancy.observations or "",
                }
                rendered_subject = Template(subject).render(**context)
                rendered_body = Template(body_text).render(**context)
                rendered_html = Template(body_html or body_text).render(**context)
            email_log = EmailLog(
                template_id=template_id,
                occupancy_id=occupancy_id,
                recipient_email=occupant.email,
                recipient_name=f"{occupant.first_name} {occupant.last_name}",
                subject=rendered_subject,
                body_text=rendered_body,
                status="pending",
            )
            self.db.add(email_log)
            await self.db.flush()
            
            try:
                attachments = self._select_email_attachments(template, occupancy.housing_id) if template else []
                await self._send_email(occupant.email, rendered_subject, rendered_body, rendered_html, attachments)
                email_log.status = "sent"
                email_log.sent_at = datetime.utcnow()
                sent_count += 1
            except Exception as e:
                email_log.status = "failed"
                email_log.error_message = str(e)
            
            await self.db.commit()
        
        return f"{sent_count} message(s) envoyé(s)"

    async def list_email_logs(self, params: dict) -> dict:
        query = select(EmailLog)
        count_query = select(func.count(EmailLog.id))

        if params.get("template_id"):
            query = query.where(EmailLog.template_id == params["template_id"])
            count_query = count_query.where(EmailLog.template_id == params["template_id"])

        if params.get("occupancy_id"):
            query = query.where(EmailLog.occupancy_id == params["occupancy_id"])
            count_query = count_query.where(EmailLog.occupancy_id == params["occupancy_id"])

        if params.get("status"):
            query = query.where(EmailLog.status == params["status"])
            count_query = count_query.where(EmailLog.status == params["status"])

        if params.get("date_from"):
            query = query.where(EmailLog.created_at >= params["date_from"])
            count_query = count_query.where(EmailLog.created_at >= params["date_from"])

        if params.get("date_to"):
            query = query.where(EmailLog.created_at <= params["date_to"])
            count_query = count_query.where(EmailLog.created_at <= params["date_to"])

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        sort_col = getattr(EmailLog, params.get("sort_by", "created_at"), EmailLog.created_at)
        if params.get("sort_order") == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": [EmailLogResponse.model_validate(i, from_attributes=True).model_dump() for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    # ============================================================
    # ENHANCED PLANNING
    # ============================================================

    async def get_planning(self, start_date: date, end_date: date, view: str = "month", 
                          housing_ids: Optional[List[int]] = None, status_filter: Optional[str] = None,
                          include_completed: bool = False) -> dict:
        query = select(Housing).options(
            selectinload(Housing.room).selectinload(Room.building).selectinload(Building.site),
        ).where(Housing.is_active == True)

        if housing_ids:
            query = query.where(Housing.id.in_(housing_ids))

        query = query.order_by(Housing.id)
        result = await self.db.execute(query)
        housings = result.scalars().all()

        # Get occupancies
        occ_query = select(Occupancy).options(
            selectinload(Occupancy.occupants),
            selectinload(Occupancy.cleanings),
        ).where(
            Occupancy.status.in_(["pre_reserved", "confirmed", "in_progress"] + (["completed"] if include_completed else [])),
            func.date(Occupancy.departure_date) >= start_date,
            func.date(Occupancy.arrival_date) <= end_date,
        )
        if status_filter:
            occ_query = occ_query.where(Occupancy.status == status_filter)
        
        occ_result = await self.db.execute(occ_query)
        occupancies = occ_result.scalars().all()

        # Include linked cleanings even when their scheduled date falls outside the view.
        occupancy_ids = [occupancy.id for occupancy in occupancies]
        cleaning_query = select(Cleaning).where(
            or_(
                and_(
                    Cleaning.scheduled_date >= start_date,
                    Cleaning.scheduled_date <= end_date,
                ),
                Cleaning.occupancy_id.in_(occupancy_ids),
            ),
        ).options(selectinload(Cleaning.volunteers))
        cleaning_result = await self.db.execute(cleaning_query)
        cleanings = cleaning_result.scalars().all()
        cleanings_by_housing = {}
        for c in cleanings:
            if c.housing_id not in cleanings_by_housing:
                cleanings_by_housing[c.housing_id] = []
            cleanings_by_housing[c.housing_id].append(c)

        entries = []
        for occ in occupancies:
            h = next((h for h in housings if h.id == occ.housing_id), None)
            if not h:
                continue
            
            # Check cleaning status
            housing_cleanings = cleanings_by_housing.get(h.id, [])
            all_occ_cleanings = [c for c in housing_cleanings if c.occupancy_id == occ.id]
            cancelled_cleaning = any(c.status == "cancelled" for c in all_occ_cleanings)
            occ_cleanings = [c for c in all_occ_cleanings if c.status != "cancelled"]
            has_cleaning_planned = len(occ_cleanings) > 0
            cleaning_status = None
            if occ_cleanings:
                cleaning_status = occ_cleanings[0].status

            selected_volunteer_ids = []
            if occ_cleanings:
                try:
                    selected_volunteer_ids = json.loads(occ_cleanings[0].selected_volunteer_ids_json or "[]")
                except (TypeError, ValueError):
                    selected_volunteer_ids = []

            occupants_data = []
            for i, occ_occupant in enumerate(occ.occupants):
                occupants_data.append({
                    "id": occ_occupant.id,
                    "first_name": occ_occupant.first_name,
                    "last_name": occ_occupant.last_name,
                    "email": occ_occupant.email,
                    "phone": occ_occupant.phone,
                    "is_primary": i == 0,
                })

            entries.append({
                "occupancy_id": occ.id,
                "housing_id": h.id,
                "room_index": occ.room_index,
                "housing_name": h.room.name if h.room else "",
                "housing_reference": h.room.reference if h.room else "",
                "building_name": h.room.building.name if h.room and h.room.building else "",
                "site_name": h.room.building.site.name if h.room and h.room.building and h.room.building.site else "",
                "occupants": occupants_data,
                "status": occ.status,
                "arrival_date": occ.arrival_date.isoformat(),
                "departure_date": occ.departure_date.isoformat(),
                "nb_persons": occ.nb_persons,
                "cleaning_status": cleaning_status,
                "has_cleaning_planned": has_cleaning_planned,
                "cleaning_id": occ_cleanings[0].id if occ_cleanings else None,
                "cleaning_volunteers_needed": occ_cleanings[0].volunteers_needed if occ_cleanings else None,
                "cleaning_volunteer_ids": [v.id for v in occ_cleanings[0].volunteers] if occ_cleanings else [],
                "selected_volunteer_ids": selected_volunteer_ids,
                "cleaning_scheduled_date": occ_cleanings[0].scheduled_date if occ_cleanings else None,
                "cleaning_invitation_status": occ_cleanings[0].invitation_status if occ_cleanings else None,
                "cleaning_cancelled": cancelled_cleaning and not has_cleaning_planned,
            })

        for cleaning in cleanings:
            if cleaning.occupancy_id is not None or cleaning.status == "cancelled":
                continue
            housing = next((item for item in housings if item.id == cleaning.housing_id), None)
            if not housing:
                continue
            try:
                selected_volunteer_ids = json.loads(cleaning.selected_volunteer_ids_json or "[]")
            except (TypeError, ValueError):
                selected_volunteer_ids = []
            entries.append({
                "occupancy_id": -cleaning.id,
                "housing_id": housing.id,
                "room_index": 0,
                "housing_name": housing.room.name if housing.room else "",
                "housing_reference": housing.room.reference if housing.room else "",
                "building_name": housing.room.building.name if housing.room and housing.room.building else "",
                "site_name": housing.room.building.site.name if housing.room and housing.room.building and housing.room.building.site else "",
                "occupants": [],
                "status": "confirmed",
                "arrival_date": datetime.combine(cleaning.scheduled_date, datetime.min.time()).isoformat(),
                "departure_date": datetime.combine(cleaning.scheduled_date, datetime.min.time()).isoformat(),
                "nb_persons": 0,
                "cleaning_status": cleaning.status,
                "has_cleaning_planned": True,
                "cleaning_id": cleaning.id,
                "is_direct_cleaning": True,
                "cleaning_volunteers_needed": cleaning.volunteers_needed,
                "cleaning_volunteer_ids": [volunteer.id for volunteer in cleaning.volunteers],
                "selected_volunteer_ids": selected_volunteer_ids,
                "cleaning_scheduled_date": cleaning.scheduled_date,
                "cleaning_invitation_status": cleaning.invitation_status,
                "cleaning_cancelled": False,
            })

        housing_list = []
        for h in housings:
            building_name = h.room.building.name if h.room and h.room.building else ""
            site_name = h.room.building.site.name if h.room and h.room.building and h.room.building.site else ""
            housing_list.append({
                "id": h.id,
                "name": h.room.name if h.room else "",
                "reference": h.room.reference if h.room else "",
                "building": building_name,
                "site": site_name,
                "capacity": h.capacity,
                "nb_rooms": h.nb_rooms,
                "beds": h.beds,
                "bed_configuration": h.bed_configuration,
                "room_names": h.room_names,
            })

        return {
            "housings": housing_list,
            "entries": entries,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

    # ============================================================
    # OCCUPANCY WITH MULTIPLE OCCUPANTS
    # ============================================================

    async def create_occupancy(self, data: dict) -> dict:
        if self.current_user:
            data["created_by"] = self.current_user.id

        arrival_date = data.get("arrival_date")
        departure_date = data.get("departure_date")
        if arrival_date.date() < date.today():
            raise HTTPException(status_code=400, detail="Une réservation ne peut pas commencer dans le passé")
        if departure_date < arrival_date:
            raise HTTPException(status_code=400, detail="La date de départ doit être postérieure à la date d'arrivée")

        room_index = data.get("room_index")
        overlap_query = select(Occupancy.id).where(
            Occupancy.housing_id == data["housing_id"],
            Occupancy.status.in_(["pre_reserved", "confirmed", "in_progress"]),
            Occupancy.arrival_date <= departure_date,
            Occupancy.departure_date >= arrival_date,
        )
        if room_index is None or room_index == 0:
            overlap_query = overlap_query.where(
                or_(Occupancy.room_index == room_index, Occupancy.room_index.is_(None))
            )
        else:
            overlap_query = overlap_query.where(Occupancy.room_index == room_index)
        if (await self.db.execute(overlap_query.limit(1))).scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Cette période chevauche déjà une réservation")

        occupant_ids = data.pop("occupant_ids", [])
        occupancy = Occupancy(**data)
        self.db.add(occupancy)
        await self.db.flush()
        
        # Link occupants
        for i, occ_id in enumerate(occupant_ids):
            from app.models.housing import occupancy_occupants
            stmt = occupancy_occupants.insert().values(
                occupancy_id=occupancy.id,
                occupant_id=occ_id,
                is_primary=(i == 0)
            )
            await self.db.execute(stmt)
        
        await self._log_occupancy_status(occupancy.id, None, occupancy.status)
        await self.db.commit()
        
        return await self.get_occupancy(occupancy.id)

    async def update_occupancy(self, occupancy_id: int, data: dict) -> Optional[dict]:
        result = await self.db.execute(select(Occupancy).where(Occupancy.id == occupancy_id))
        occupancy = result.scalar_one_or_none()
        if not occupancy:
            return None
        
        # Handle occupant_ids separately
        if "occupant_ids" in data:
            occupant_ids = data.pop("occupant_ids")
            # Remove existing associations
            from app.models.housing import occupancy_occupants
            await self.db.execute(
                occupancy_occupants.delete().where(occupancy_occupants.c.occupancy_id == occupancy_id)
            )
            # Add new associations
            for i, occ_id in enumerate(occupant_ids):
                stmt = occupancy_occupants.insert().values(
                    occupancy_id=occupancy.id,
                    occupant_id=occ_id,
                    is_primary=(i == 0)
                )
                await self.db.execute(stmt)
        
        for k, v in data.items():
            if hasattr(occupancy, k) and v is not None:
                setattr(occupancy, k, v)
        await self.db.flush()
        await self.db.commit()
        return await self.get_occupancy(occupancy_id)


from app.schemas.housing import (
    OccupancyResponse,
    OccupantResponse,
    UnavailabilityResponse,
    CleaningResponse,
    EmailTemplateResponse,
    EmailTemplateAttachmentResponse,
    EmailLogResponse,
)
