from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List
from uuid import uuid4
import os
import json

from fastapi import UploadFile, HTTPException, Form
from sqlalchemy import select, func, and_, or_, case, extract, insert, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from jinja2 import Template

from app.models.buildings import Room, Building, Site, UsageType
from app.models.housing import (
    Housing, Occupancy, Occupant, Unavailability, 
    HousingStatusHistory, OccupancyStatusHistory,
    Cleaning, EmailTemplate, EmailTemplateAttachment, EmailLog,
    occupancy_occupants
)
from app.models.user import User


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
        occupant = Occupant(**data)
        self.db.add(occupant)
        await self.db.flush()
        return OccupantResponse.model_validate(occupant, from_attributes=True).model_dump()

    async def update_occupant(self, occupant_id: int, data: dict) -> Optional[dict]:
        result = await self.db.execute(select(Occupant).where(Occupant.id == occupant_id))
        occupant = result.scalar_one_or_none()
        if not occupant:
            return None
        for k, v in data.items():
            if hasattr(occupant, k) and v is not None:
                setattr(occupant, k, v)
        await self.db.flush()
        return OccupantResponse.model_validate(occupant, from_attributes=True).model_dump()

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
        occupancy.status = new_status

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
            )
            .where(Cleaning.id == cleaning_id)
        )
        c = result.scalar_one_or_none()
        if not c:
            return None
        return CleaningResponse.model_validate(c, from_attributes=True).model_dump()

    async def create_cleaning(self, data: dict) -> dict:
        if self.current_user:
            data["created_by"] = self.current_user.id
        cleaning = Cleaning(**data)
        self.db.add(cleaning)
        await self.db.flush()
        await self.db.commit()
        return await self.get_cleaning(cleaning.id)

    async def update_cleaning(self, cleaning_id: int, data: dict) -> Optional[dict]:
        result = await self.db.execute(select(Cleaning).where(Cleaning.id == cleaning_id))
        cleaning = result.scalar_one_or_none()
        if not cleaning:
            return None
        for k, v in data.items():
            if hasattr(cleaning, k) and v is not None:
                setattr(cleaning, k, v)
        await self.db.flush()
        await self.db.commit()
        return await self.get_cleaning(cleaning_id)

    async def delete_cleaning(self, cleaning_id: int) -> bool:
        result = await self.db.execute(select(Cleaning).where(Cleaning.id == cleaning_id))
        cleaning = result.scalar_one_or_none()
        if not cleaning:
            return False
        await self.db.delete(cleaning)
        await self.db.commit()
        return True

    # ============================================================
    # EMAIL TEMPLATES
    # ============================================================

    async def list_email_templates(self, params: dict) -> dict:
        query = select(EmailTemplate).options(selectinload(EmailTemplate.attachments))
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
            "items": [EmailTemplateResponse.model_validate(i, from_attributes=True).model_dump() for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def get_email_template(self, template_id: int) -> Optional[dict]:
        result = await self.db.execute(
            select(EmailTemplate)
            .options(selectinload(EmailTemplate.attachments))
            .where(EmailTemplate.id == template_id)
        )
        t = result.scalar_one_or_none()
        if not t:
            return None
        return EmailTemplateResponse.model_validate(t, from_attributes=True).model_dump()

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

    async def upload_email_template_attachment(self, template_id: int, file: UploadFile) -> dict:
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
        self.db.add(attachment)
        await self.db.flush()
        await self.db.commit()
        
        return EmailTemplateAttachmentResponse.model_validate(attachment, from_attributes=True).model_dump()

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

    def _render_email_template(self, template: EmailTemplate, context: dict) -> tuple[str, str]:
        from jinja2 import Template
        html_template = Template(template.body_html)
        text_template = Template(template.body_text or template.body_html)
        return html_template.render(**context), text_template.render(**context)

    async def send_confirmation_email(self, occupancy_id: int, template_id: int, recipient_ids: List[int], send_to_all: bool) -> str:
        # Get occupancy with occupants
        result = await self.db.execute(
            select(Occupancy)
            .options(selectinload(Occupancy.occupants), selectinload(Occupancy.housing).selectinload(Housing.room).selectinload(Room.building))
            .where(Occupancy.id == occupancy_id)
        )
        occupancy = result.scalar_one_or_none()
        if not occupancy:
            return "Occupation non trouvée"
        
        template_result = await self.db.execute(
            select(EmailTemplate).options(selectinload(EmailTemplate.attachments))
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
            }
            
            html_body, text_body = self._render_email_template(template, context)
            
            # Log email
            email_log = EmailLog(
                template_id=template_id,
                occupancy_id=occupancy_id,
                recipient_email=occupant.email,
                recipient_name=f"{occupant.first_name} {occupant.last_name}",
                subject=template.subject,
                body_text=text_body,
                status="pending",
            )
            self.db.add(email_log)
            await self.db.flush()
            
            # Send email (placeholder - would integrate with actual email service)
            try:
                # TODO: Integrate with actual email sending service (SMTP, SendGrid, etc.)
                # For now, just log as sent
                email_log.status = "sent"
                email_log.sent_at = datetime.utcnow()
                sent_count += 1
            except Exception as e:
                email_log.status = "failed"
                email_log.error_message = str(e)
            
            await self.db.commit()
        
        return f"{sent_count} email(s) envoyé(s) sur {len(recipients)} destinataire(s)"

    async def send_custom_message(self, occupancy_id: int, subject: str, body_text: str, 
                                  recipient_ids: List[int], template_id: Optional[int], 
                                  attachment_ids: List[int]) -> str:
        result = await self.db.execute(
            select(Occupancy)
            .options(selectinload(Occupancy.occupants))
            .where(Occupancy.id == occupancy_id)
        )
        occupancy = result.scalar_one_or_none()
        if not occupancy:
            return "Occupation non trouvée"
        
        recipients = [o for o in occupancy.occupants if o.id in recipient_ids and o.email]
        if not recipients:
            return "Aucun destinataire valide"
        
        sent_count = 0
        for occupant in recipients:
            email_log = EmailLog(
                template_id=template_id,
                occupancy_id=occupancy_id,
                recipient_email=occupant.email,
                recipient_name=f"{occupant.first_name} {occupant.last_name}",
                subject=subject,
                body_text=body_text,
                status="pending",
            )
            self.db.add(email_log)
            await self.db.flush()
            
            try:
                # TODO: Integrate with actual email sending service
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
                          housing_ids: Optional[List[int]] = None, status_filter: Optional[str] = None) -> dict:
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
            Occupancy.status.in_(["pre_reserved", "confirmed", "in_progress"]),
            func.date(Occupancy.departure_date) >= start_date,
            func.date(Occupancy.arrival_date) <= end_date,
        )
        if status_filter:
            occ_query = occ_query.where(Occupancy.status == status_filter)
        
        occ_result = await self.db.execute(occ_query)
        occupancies = occ_result.scalars().all()

        # Get cleanings for the period
        cleaning_query = select(Cleaning).where(
            Cleaning.scheduled_date >= start_date,
            Cleaning.scheduled_date <= end_date,
        )
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
            occ_cleanings = [c for c in housing_cleanings if c.occupancy_id == occ.id]
            has_cleaning_planned = len(occ_cleanings) > 0
            cleaning_status = None
            if occ_cleanings:
                cleaning_status = occ_cleanings[0].status

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
                "occupants": occupants_data,
                "status": occ.status,
                "arrival_date": occ.arrival_date.isoformat(),
                "departure_date": occ.departure_date.isoformat(),
                "nb_persons": occ.nb_persons,
                "cleaning_status": cleaning_status,
                "has_cleaning_planned": has_cleaning_planned,
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
