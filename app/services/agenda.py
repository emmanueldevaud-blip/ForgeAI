import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agenda import AgendaPresence
from app.models.buildings import Building, Room, UsageType
from app.models.housing import Cleaning, Occupancy, Occupant
from app.models.user import User
from app.models.volunteer import Volunteer
from app.schemas.agenda import (
    AgendaDayResponse,
    AgendaExternalPresenceCreate,
    AgendaPlanningResponse,
    AgendaPresenceItem,
    AgendaPresenceResponse,
    AgendaPresenceUpsert,
    AgendaRoomDayCounters,
    AgendaRoomResponse,
)

BUREAU_USAGE_CODES = ("BUREAUX", "BUREAU")
CLEANING_ACTIVE_STATUSES = ("planned", "in_progress", "to_check", "checked", "completed")
OCCUPANCY_PRESENT_STATUSES = ("confirmed", "in_progress")


def _periods_overlap(left: str, right: str) -> bool:
    left = left or "full"
    right = right or "full"
    if left == "full" or right == "full":
        return True
    return left == right



def _week_bounds(anchor: date) -> tuple[date, date]:
    # Planning ouvré: lundi → vendredi (5 jours)
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=4)


def _month_bounds(anchor: date) -> tuple[date, date]:
    start = anchor.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
    return start, end


def _daterange(start: date, end: date) -> List[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


class AgendaService:
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user

    # ------------------------------------------------------------
    # Rooms (Bureau)
    # ------------------------------------------------------------

    async def list_bureau_rooms(self) -> List[AgendaRoomResponse]:
        stmt = (
            select(Room, Building.name, UsageType.code, UsageType.name)
            .join(Building, Building.id == Room.building_id)
            .outerjoin(UsageType, UsageType.id == Room.usage_type_id)
            .where(
                Room.is_active.is_(True),
                Building.is_active.is_(True),
                or_(
                    UsageType.code.in_(BUREAU_USAGE_CODES),
                    UsageType.name.ilike("%bureau%"),
                ),
            )
            .order_by(Building.name, Room.name)
        )
        result = await self.db.execute(stmt)
        rooms: List[AgendaRoomResponse] = []
        for room, building_name, _code, _name in result.all():
            rooms.append(
                AgendaRoomResponse(
                    id=room.id,
                    reference=room.reference,
                    name=room.name,
                    building_id=room.building_id,
                    building_name=building_name,
                    workstation_capacity=room.workstation_capacity or 0,
                )
            )
        return rooms

    async def _room_capacity_map(self, room_ids: List[int]) -> Dict[int, int]:
        if not room_ids:
            return {}
        result = await self.db.execute(
            select(Room.id, Room.workstation_capacity).where(Room.id.in_(room_ids))
        )
        return {row[0]: row[1] or 0 for row in result.all()}

    # ------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------

    async def get_planning(self, view: str, anchor: date) -> AgendaPlanningResponse:
        if view == "week":
            start, end = _week_bounds(anchor)
        elif view == "month":
            start, end = _month_bounds(anchor)
        else:
            raise ValueError(f"Vue inconnue: {view}")

        rooms = await self.list_bureau_rooms()
        room_ids = [r.id for r in rooms]
        capacities = await self._room_capacity_map(room_ids)
        days_list = _daterange(start, end)

        # Manual/user presences
        presences_stmt = select(AgendaPresence).where(
            AgendaPresence.presence_date.between(start, end),
            AgendaPresence.is_present.is_(True),
        )
        if room_ids:
            presences_stmt = presences_stmt.where(AgendaPresence.room_id.in_(room_ids))
        presences_stmt = presences_stmt.options(selectinload(AgendaPresence.user))
        presences = (await self.db.execute(presences_stmt)).scalars().all()

        user_ids = {p.user_id for p in presences if p.user_id}
        users: Dict[int, User] = {}
        if user_ids:
            users_result = await self.db.execute(select(User).where(User.id.in_(user_ids)))
            users = {u.id: u for u in users_result.scalars().all()}

        # Cleaning volunteers (confirmed for scheduled_date)
        cleaning_people = await self._cleaning_people(start, end)

        # Occupants with confirmed/in_progress occupancy covering each date
        occupant_people = await self._occupant_people(start, end)

        by_day: Dict[date, List[AgendaPresence]] = defaultdict(list)
        for p in presences:
            by_day[p.presence_date].append(p)

        days: List[AgendaDayResponse] = []
        for day in days_list:
            room_counters = {
                r.id: AgendaRoomDayCounters(
                    room_id=r.id,
                    capacity=capacities.get(r.id, 0),
                )
                for r in rooms
            }
            total_present = 0
            total_workstations = 0

            for p in by_day.get(day, []):
                counter = room_counters.get(p.room_id)
                if counter is None:
                    continue
                counter.present_count += 1
                total_present += 1
                if p.needs_workstation:
                    counter.workstation_count += 1
                    total_workstations += 1
                if p.user_id:
                    user = users.get(p.user_id)
                    name = user.full_name if user else f"Utilisateur #{p.user_id}"
                    person_type = "user"
                    person_id = p.user_id
                else:
                    name = p.external_name or " externe"
                    person_type = "external"
                    person_id = None
                counter.presences.append(
                    AgendaPresenceItem(
                        id=p.id,
                        person_type=person_type,
                        person_id=person_id,
                        person_name=name,
                        room_id=p.room_id,
                        needs_workstation=p.needs_workstation,
                        needs_meal=p.needs_meal,
                        source=p.source,
                        is_mine=bool(p.user_id and p.user_id == self.current_user.id),
                        origin_ref=p.source_ref,
                        period=p.period or "full",
                    )
                )

            integrated: List[AgendaPresenceItem] = []
            for item in cleaning_people.get(day, []):
                integrated.append(item)
                total_present += 1
            for item in occupant_people.get(day, []):
                counter = room_counters.get(item.room_id) if item.room_id else None
                if counter is not None:
                    counter.present_count += 1
                    total_present += 1
                    if item.needs_workstation:
                        counter.workstation_count += 1
                        total_workstations += 1
                    counter.presences.append(item)
                else:
                    integrated.append(item)
                    total_present += 1

            days.append(
                AgendaDayResponse(
                    date=day,
                    total_present=total_present,
                    total_workstations=total_workstations,
                    rooms=[room_counters[r.id] for r in rooms],
                    integrated=integrated,
                )
            )

        return AgendaPlanningResponse(
            view=view,  # type: ignore[arg-type]
            start_date=start,
            end_date=end,
            rooms=rooms,
            days=days,
        )

    async def _cleaning_people(self, start: date, end: date) -> Dict[date, List[AgendaPresenceItem]]:
        stmt = (
            select(Cleaning)
            .where(
                Cleaning.scheduled_date.between(start, end),
                Cleaning.status.in_(CLEANING_ACTIVE_STATUSES),
            )
            .options(selectinload(Cleaning.volunteers))
        )
        cleanings = (await self.db.execute(stmt)).scalars().all()

        # Volunteers referenced only via selected_volunteer_ids_json
        volunteer_ids: set[int] = set()
        for cleaning in cleanings:
            if cleaning.selected_volunteer_ids_json:
                try:
                    volunteer_ids.update(int(v) for v in json.loads(cleaning.selected_volunteer_ids_json))
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass

        volunteers: Dict[int, Volunteer] = {}
        if volunteer_ids:
            vol_result = await self.db.execute(select(Volunteer).where(Volunteer.id.in_(volunteer_ids)))
            volunteers = {v.id: v for v in vol_result.scalars().all()}

        by_day: Dict[date, List[AgendaPresenceItem]] = defaultdict(list)
        seen: Dict[date, set[int]] = defaultdict(set)

        for cleaning in cleanings:
            selected: List[int] = []
            if cleaning.selected_volunteer_ids_json:
                try:
                    selected = [int(v) for v in json.loads(cleaning.selected_volunteer_ids_json)]
                except (TypeError, ValueError, json.JSONDecodeError):
                    selected = []
            for vid in selected:
                if vid in seen[cleaning.scheduled_date]:
                    continue
                volunteer = volunteers.get(vid)
                if not volunteer:
                    continue
                seen[cleaning.scheduled_date].add(vid)
                by_day[cleaning.scheduled_date].append(
                    AgendaPresenceItem(
                        person_type="cleaning",
                        person_id=volunteer.id,
                        person_name=f"{volunteer.first_name} {volunteer.last_name}".strip(),
                        room_id=None,
                        needs_workstation=False,
                        source="cleaning",
                        is_mine=False,
                        origin_ref=f"cleaning:{cleaning.id}",
                        period="full",
                    )
                )
        return by_day

    async def _occupant_people(self, start: date, end: date) -> Dict[date, List[AgendaPresenceItem]]:
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())

        stmt = (
            select(Occupancy)
            .where(
                Occupancy.status.in_(OCCUPANCY_PRESENT_STATUSES),
                Occupancy.arrival_date <= end_dt,
                Occupancy.departure_date >= start_dt,
            )
            .options(selectinload(Occupancy.occupants))
        )
        occupancies = (await self.db.execute(stmt)).scalars().all()

        by_day: Dict[date, List[AgendaPresenceItem]] = defaultdict(list)
        for occupancy in occupancies:
            day_start = max(occupancy.arrival_date.date(), start)
            day_end = min(occupancy.departure_date.date(), end)
            for day in _daterange(day_start, day_end):
                for occupant in occupancy.occupants:
                    by_day[day].append(
                        AgendaPresenceItem(
                            person_type="occupant",
                            person_id=occupant.id,
                            person_name=f"{occupant.first_name} {occupant.last_name}".strip(),
                            room_id=occupancy.agenda_room_id,
                            needs_workstation=bool(occupancy.needs_workstation),
                            source="occupant",
                            is_mine=False,
                            origin_ref=f"occupancy:{occupancy.id}",
                            period="full",
                        )
                    )
        return by_day

    # ------------------------------------------------------------
    # Presence mutations
    # ------------------------------------------------------------

    async def get_presence(self, presence_id: int) -> Optional[AgendaPresence]:
        result = await self.db.execute(
            select(AgendaPresence)
            .where(AgendaPresence.id == presence_id)
            .options(selectinload(AgendaPresence.user))
        )
        return result.scalar_one_or_none()

    async def upsert_own_presence(self, payload: AgendaPresenceUpsert) -> AgendaPresenceResponse:
        if not payload.is_present:
            # "Absent" = remove own presence for that day/room
            existing = await self._find_own_presence(payload.presence_date, payload.room_id)
            if existing:
                await self.db.delete(existing)
                await self.db.commit()
            return AgendaPresenceResponse(
                id=0,
                presence_date=payload.presence_date,
                room_id=payload.room_id,
                user_id=self.current_user.id,
                external_name=None,
                source="user",
                is_present=False,
                needs_workstation=payload.needs_workstation,
                needs_meal=payload.needs_meal,
                period=payload.period,
                created_by=self.current_user.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

        await self._ensure_room_exists(payload.room_id)
        await self._assert_own_day_allowed(
            payload.presence_date,
            payload.room_id,
            period=payload.period,
            needs_meal=payload.needs_meal,
        )
        existing = await self._find_own_presence(payload.presence_date, payload.room_id)

        if existing:
            existing.needs_workstation = payload.needs_workstation
            existing.needs_meal = payload.needs_meal
            existing.is_present = True
            existing.period = payload.period
            presence = existing
        else:
            presence = AgendaPresence(
                presence_date=payload.presence_date,
                room_id=payload.room_id,
                user_id=self.current_user.id,
                external_name=None,
                source="user",
                is_present=True,
                needs_workstation=payload.needs_workstation,
                needs_meal=payload.needs_meal,
                period=payload.period,
                created_by=self.current_user.id,
            )
            self.db.add(presence)

        await self.db.commit()
        await self.db.refresh(presence)
        return AgendaPresenceResponse.model_validate(presence)

    async def create_external_presence(
        self, payload: AgendaExternalPresenceCreate
    ) -> AgendaPresenceResponse:
        await self._ensure_room_exists(payload.room_id)
        presence = AgendaPresence(
            presence_date=payload.presence_date,
            room_id=payload.room_id,
            user_id=None,
            external_name=payload.external_name.strip(),
            source="manual",
            is_present=True,
            needs_workstation=payload.needs_workstation,
            needs_meal=payload.needs_meal,
            period=payload.period,
            created_by=self.current_user.id,
        )
        self.db.add(presence)
        await self.db.commit()
        await self.db.refresh(presence)
        return AgendaPresenceResponse.model_validate(presence)

    async def delete_presence(self, presence_id: int) -> None:
        presence = await self.get_presence(presence_id)
        if not presence:
            raise LookupError("Présence introuvable")
        if presence.user_id and presence.user_id != self.current_user.id:
            # Only managers can delete other people's presences (checked by router)
            pass
        await self.db.delete(presence)
        await self.db.commit()

    async def update_presence(
        self,
        presence_id: int,
        *,
        needs_workstation: Optional[bool] = None,
        needs_meal: Optional[bool] = None,
        is_present: Optional[bool] = None,
        period: Optional[str] = None,
    ) -> AgendaPresenceResponse:
        presence = await self.get_presence(presence_id)
        if not presence:
            raise LookupError("Présence introuvable")
        next_period = period if period is not None else presence.period
        next_meal = needs_meal if needs_meal is not None else presence.needs_meal
        if period is not None or needs_meal is not None:
            await self._assert_own_day_allowed(
                presence.presence_date,
                presence.room_id,
                period=next_period,
                needs_meal=next_meal,
                exclude_presence_id=presence.id,
            )
        if needs_workstation is not None:
            presence.needs_workstation = needs_workstation
        if needs_meal is not None:
            presence.needs_meal = needs_meal
        if is_present is not None:
            presence.is_present = is_present
        if period is not None:
            presence.period = period
        await self.db.commit()
        await self.db.refresh(presence)
        return AgendaPresenceResponse.model_validate(presence)

    async def _assert_own_day_allowed(
        self,
        day: date,
        room_id: int,
        *,
        period: str,
        needs_meal: bool,
        exclude_presence_id: Optional[int] = None,
    ) -> None:
        stmt = select(AgendaPresence).where(
            AgendaPresence.presence_date == day,
            AgendaPresence.user_id == self.current_user.id,
            AgendaPresence.room_id != room_id,
            AgendaPresence.is_present.is_(True),
        )
        if exclude_presence_id is not None:
            stmt = stmt.where(AgendaPresence.id != exclude_presence_id)
        others = (await self.db.execute(stmt)).scalars().all()
        for other in others:
            if _periods_overlap(period, other.period or "full"):
                raise ValueError(
                    "Vous êtes déjà inscrit dans un autre local pour la même période"
                )
            if needs_meal and other.needs_meal:
                raise ValueError("Repas déjà sélectionné dans un autre local")

    async def _find_own_presence(self, day: date, room_id: Optional[int]) -> Optional[AgendaPresence]:
        stmt = select(AgendaPresence).where(
            AgendaPresence.presence_date == day,
            AgendaPresence.user_id == self.current_user.id,
        )
        if room_id is not None:
            stmt = stmt.where(AgendaPresence.room_id == room_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _ensure_room_exists(self, room_id: int) -> None:
        room = await self.db.get(Room, room_id)
        if not room or not room.is_active:
            raise LookupError("Local introuvable ou inactif")
