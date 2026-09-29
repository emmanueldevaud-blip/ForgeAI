import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, or_, select
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


def _normalize_name(value: str) -> str:
    return " ".join((value or "").split()).lower()


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

        # Dedup: the same physical person present as user presence and as
        # occupant/volunteer is kept once (matched via AD link, then name).
        user_keys_by_day: Dict[date, set] = defaultdict(set)
        for p in presences:
            user = users.get(p.user_id) if p.user_id else None
            if not user:
                continue
            keys = user_keys_by_day[p.presence_date]
            if user.ad_dn:
                keys.add(f"dn:{user.ad_dn.strip().lower()}")
            keys.add(f"name:{_normalize_name(user.full_name)}")

        def _matches_present_user(day: date, person_name: str, ad_dn: Optional[str]) -> bool:
            keys = user_keys_by_day.get(day)
            if not keys:
                return False
            if ad_dn and f"dn:{ad_dn.strip().lower()}" in keys:
                return True
            return f"name:{_normalize_name(person_name)}" in keys

        occupant_ids = {
            item.person_id
            for items in occupant_people.values()
            for item in items
            if item.person_id
        }
        volunteer_ids = {
            item.person_id
            for items in cleaning_people.values()
            for item in items
            if item.person_id
        }
        occupant_dns: Dict[int, Optional[str]] = {}
        volunteer_dns: Dict[int, Optional[str]] = {}
        if occupant_ids:
            rows = await self.db.execute(
                select(Occupant.id, Occupant.ad_dn).where(Occupant.id.in_(occupant_ids))
            )
            occupant_dns = {row.id: row.ad_dn for row in rows.all()}
        if volunteer_ids:
            rows = await self.db.execute(
                select(Volunteer.id, Volunteer.ad_dn).where(Volunteer.id.in_(volunteer_ids))
            )
            volunteer_dns = {row.id: row.ad_dn for row in rows.all()}

        occupant_people = {
            day: [
                item
                for item in items
                if not _matches_present_user(day, item.person_name, occupant_dns.get(item.person_id))
            ]
            for day, items in occupant_people.items()
        }
        cleaning_people = {
            day: [
                item
                for item in items
                if not _matches_present_user(day, item.person_name, volunteer_dns.get(item.person_id))
            ]
            for day, items in cleaning_people.items()
        }

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

    async def upsert_own_presence(
        self,
        payload: AgendaPresenceUpsert,
        *,
        target_user_id: Optional[int] = None,
    ) -> AgendaPresenceResponse:
        owner_id = self.current_user.id if target_user_id is None else target_user_id
        if owner_id != self.current_user.id and not await self.db.get(User, owner_id):
            raise LookupError("Utilisateur introuvable")

        if not payload.is_present:
            # "Absent" = hide own presence but keep the row as a manual decision
            # (the auto-assign will never recreate a day that already has a row)
            existing = await self._find_own_presence(
                payload.presence_date, payload.room_id, user_id=owner_id
            )
            if existing:
                if existing.is_present:
                    existing.is_present = False
                    await self.db.commit()
                    await self.db.refresh(existing)
                return AgendaPresenceResponse.model_validate(existing)
            return AgendaPresenceResponse(
                id=0,
                presence_date=payload.presence_date,
                room_id=payload.room_id,
                user_id=owner_id,
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
        if payload.presence_date < date.today():
            raise ValueError("Impossible de s'inscrire pour une date passée")
        await self._assert_own_day_allowed(
            payload.presence_date,
            payload.room_id,
            period=payload.period,
            needs_meal=payload.needs_meal,
            user_id=owner_id,
        )
        existing = await self._find_own_presence(
            payload.presence_date, payload.room_id, user_id=owner_id
        )

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
                user_id=owner_id,
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

    async def auto_assign_own_presences(self, start: date, end: date) -> Dict[str, int]:
        day_start = max(start, date.today())
        if day_start > end:
            return {"created": 0, "skipped": 0}

        dn = (self.current_user.ad_dn or "").strip().lower()
        if not dn:
            return {"created": 0, "skipped": 0}

        # day -> (room_id, needs_workstation); occupants take precedence
        plan: Dict[date, tuple[int, bool]] = {}

        occupant_ids = list(
            (
                await self.db.execute(
                    select(Occupant.id).where(
                        Occupant.is_active.is_(True),
                        Occupant.ad_dn.is_not(None),
                        func.lower(func.trim(Occupant.ad_dn)) == dn,
                    )
                )
            ).scalars()
        )
        if occupant_ids:
            stmt = (
                select(Occupancy)
                .where(
                    Occupancy.status.in_(OCCUPANCY_PRESENT_STATUSES),
                    Occupancy.arrival_date
                    <= datetime.combine(end, datetime.max.time()),
                    Occupancy.departure_date
                    >= datetime.combine(day_start, datetime.min.time()),
                    Occupancy.agenda_room_id.is_not(None),
                    Occupancy.occupants.any(Occupant.id.in_(occupant_ids)),
                )
            )
            for occupancy in (await self.db.execute(stmt)).scalars().all():
                first_day = max(occupancy.arrival_date.date(), day_start)
                last_day = min(occupancy.departure_date.date(), end)
                for day in _daterange(first_day, last_day):
                    plan.setdefault(day, (occupancy.agenda_room_id, bool(occupancy.needs_workstation)))

        volunteer_ids = set(
            (
                await self.db.execute(
                    select(Volunteer.id).where(
                        Volunteer.is_active.is_(True),
                        Volunteer.ad_dn.is_not(None),
                        func.lower(func.trim(Volunteer.ad_dn)) == dn,
                    )
                )
            ).scalars()
        )
        if volunteer_ids:
            cleanings = (
                await self.db.execute(
                    select(Cleaning)
                    .where(
                        Cleaning.scheduled_date.between(day_start, end),
                        Cleaning.status.in_(CLEANING_ACTIVE_STATUSES),
                    )
                    .options(selectinload(Cleaning.occupancy))
                )
            ).scalars().all()
            for cleaning in cleanings:
                if not cleaning.selected_volunteer_ids_json:
                    continue
                try:
                    selected = {int(v) for v in json.loads(cleaning.selected_volunteer_ids_json)}
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if not selected & volunteer_ids:
                    continue
                occupancy = cleaning.occupancy
                if not occupancy or not occupancy.agenda_room_id:
                    continue
                plan.setdefault(
                    cleaning.scheduled_date, (occupancy.agenda_room_id, False)
                )

        created = 0
        skipped = 0
        for day in sorted(plan):
            room_id, needs_workstation = plan[day]
            room = await self.db.get(Room, room_id)
            if not room or not room.is_active:
                skipped += 1
                continue
            existing = (
                await self.db.execute(
                    select(AgendaPresence.id).where(
                        AgendaPresence.presence_date == day,
                        AgendaPresence.user_id == self.current_user.id,
                    )
                )
            ).first()
            if existing:
                skipped += 1
                continue
            self.db.add(
                AgendaPresence(
                    presence_date=day,
                    room_id=room_id,
                    user_id=self.current_user.id,
                    external_name=None,
                    source="user",
                    is_present=True,
                    needs_workstation=needs_workstation,
                    needs_meal=True,
                    period="full",
                    created_by=self.current_user.id,
                )
            )
            created += 1
        if created:
            await self.db.commit()
        return {"created": created, "skipped": skipped}

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
        room_id: Optional[int] = None,
    ) -> AgendaPresenceResponse:
        presence = await self.get_presence(presence_id)
        if not presence:
            raise LookupError("Présence introuvable")
        next_period = period if period is not None else presence.period
        next_meal = needs_meal if needs_meal is not None else presence.needs_meal
        next_room = room_id if room_id is not None else presence.room_id
        if next_room != presence.room_id:
            await self._ensure_room_exists(next_room)
            if presence.user_id is not None:
                clash = await self._find_own_presence(
                    presence.presence_date, next_room, user_id=presence.user_id
                )
                if clash and clash.id != presence.id:
                    raise ValueError("Vous êtes déjà inscrit dans ce local ce jour-là")
        if period is not None or needs_meal is not None or next_room != presence.room_id:
            await self._assert_own_day_allowed(
                presence.presence_date,
                next_room,
                period=next_period,
                needs_meal=next_meal,
                exclude_presence_id=presence.id,
                user_id=presence.user_id,
            )
        if needs_workstation is not None:
            presence.needs_workstation = needs_workstation
        if needs_meal is not None:
            presence.needs_meal = needs_meal
        if is_present is not None:
            presence.is_present = is_present
        if period is not None:
            presence.period = period
        if next_room != presence.room_id:
            presence.room_id = next_room
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
        user_id: Optional[int] = None,
    ) -> None:
        owner_id = self.current_user.id if user_id is None else user_id
        if owner_id is None:
            return
        stmt = select(AgendaPresence).where(
            AgendaPresence.presence_date == day,
            AgendaPresence.user_id == owner_id,
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

    async def _find_own_presence(
        self,
        day: date,
        room_id: Optional[int],
        *,
        user_id: Optional[int] = None,
    ) -> Optional[AgendaPresence]:
        owner_id = self.current_user.id if user_id is None else user_id
        stmt = select(AgendaPresence).where(
            AgendaPresence.presence_date == day,
            AgendaPresence.user_id == owner_id,
        )
        if room_id is not None:
            stmt = stmt.where(AgendaPresence.room_id == room_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _ensure_room_exists(self, room_id: int) -> None:
        room = await self.db.get(Room, room_id)
        if not room or not room.is_active:
            raise LookupError("Local introuvable ou inactif")
