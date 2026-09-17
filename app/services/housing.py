from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_, or_, case, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.buildings import Room, Level, Building, Site, UsageType
from app.models.housing import Housing, Occupancy, Occupant, Unavailability, HousingStatusHistory, OccupancyStatusHistory
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
            selectinload(Housing.room).selectinload(Room.level).selectinload(Level.building).selectinload(Building.site)
        )
        .where(Housing.id == housing_id)
    )
    h = result.scalar_one_or_none()
    if not h:
        return None
    room = h.room
    level = room.level if room else None
    building = level.building if level else None
    site = building.site if building else None
    return {
        "id": h.id,
        "room_id": h.room_id,
        "room": {"id": room.id, "reference": room.reference, "name": room.name, "area": room.area} if room else None,
        "level": {"id": level.id, "name": level.name, "building": {"id": building.id, "name": building.name} if building else None} if level else None,
        "site": {"id": site.id, "name": site.name} if site else None,
        "housing_type": h.housing_type,
        "capacity": h.capacity,
        "beds": h.beds,
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
                selectinload(Housing.room).selectinload(Room.level).selectinload(Level.building).selectinload(Building.site),
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
            query = query.join(Housing.room).join(Room.level).join(Level.building).where(Building.site_id == params["site_id"])
            count_query = count_query.join(Housing.room).join(Room.level).join(Level.building).where(Building.site_id == params["site_id"])

        if params.get("building_id"):
            query = query.join(Housing.room).join(Room.level).where(Level.building_id == params["building_id"])
            count_query = count_query.join(Housing.room).join(Room.level).where(Level.building_id == params["building_id"])

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
                selectinload(Occupancy.housing).selectinload(Housing.room).selectinload(Room.level).selectinload(Level.building).selectinload(Building.site),
                selectinload(Occupancy.occupant),
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
                selectinload(Occupancy.housing).selectinload(Housing.room).selectinload(Room.level).selectinload(Level.building).selectinload(Building.site),
                selectinload(Occupancy.occupant),
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
    # PLANNING
    # ============================================================

    async def get_planning(self, start_date: date, end_date: date) -> dict:
        housings_result = await self.db.execute(
            select(Housing)
            .options(
                selectinload(Housing.room).selectinload(Room.level).selectinload(Level.building),
            )
            .where(Housing.is_active == True)
            .order_by(Housing.id)
        )
        housings = housings_result.scalars().all()

        occ_result = await self.db.execute(
            select(Occupancy)
            .options(selectinload(Occupancy.occupant))
            .where(
                Occupancy.status.in_(["pre_reserved", "confirmed", "in_progress"]),
                func.date(Occupancy.departure_date) >= start_date,
                func.date(Occupancy.arrival_date) <= end_date,
            )
        )
        occupancies = occ_result.scalars().all()

        entries = []
        for occ in occupancies:
            h = next((h for h in housings if h.id == occ.housing_id), None)
            if h:
                entries.append({
                    "occupancy_id": occ.id,
                    "housing_id": h.id,
                    "housing_name": h.room.name if h.room else "",
                    "housing_reference": h.room.reference if h.room else "",
                    "occupant_name": f"{occ.occupant.last_name} {occ.occupant.first_name}" if occ.occupant else "",
                    "status": occ.status,
                    "arrival_date": occ.arrival_date.isoformat(),
                    "departure_date": occ.departure_date.isoformat(),
                    "nb_persons": occ.nb_persons,
                })

        housing_list = []
        for h in housings:
            building_name = h.room.level.building.name if h.room and h.room.level and h.room.level.building else ""
            level_name = h.room.level.name if h.room and h.room.level else ""
            housing_list.append({
                "id": h.id,
                "name": h.room.name if h.room else "",
                "reference": h.room.reference if h.room else "",
                "building": building_name,
                "level": level_name,
            })

        return {
            "housings": housing_list,
            "entries": entries,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }


from app.schemas.housing import (
    OccupancyResponse,
    OccupantResponse,
    UnavailabilityResponse,
)
