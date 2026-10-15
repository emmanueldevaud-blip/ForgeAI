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
from app.models.module import Module
from app.models.rbac import Group, GroupGroup, UserGroup
from app.models.user import User
from app.models.volunteer import Volunteer
from app.schemas.agenda import (
    AgendaDayResponse,
    AgendaExternalPresenceCreate,
    AgendaPlanningGroup,
    AgendaPlanningPerson,
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

# Ordre d'affichage souhaité pour les groupes du planning.
# Les groupes racines sont triés selon cette liste ; les groupes absents
# de la liste sont placés après, dans leur ordre de sauvegarde.
PLANNING_GROUP_ORDER = [
    "structure",
    "ede",
    "jwcad",
    "intendance",
    "maintenance",
    "autres",
]


def _periods_overlap(left: str, right: str) -> bool:
    left = left or "full"
    right = right or "full"
    if left == "full" or right == "full":
        return True
    return left == right


def _merge_periods(existing: str, new: str) -> str:
    """Fusionne deux périodes : matin + après-midi = journée complète."""
    existing = existing or "full"
    new = new or "full"
    if existing == "full" or new == "full":
        return "full"
    if existing != new:
        return "full"
    return existing



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

    async def _get_planning_group_ids(self) -> List[int]:
        """Retrieve planning_group_ids from module settings."""
        result = await self.db.execute(
            select(Module).where(Module.code == "agenda")
        )
        module = result.scalar_one_or_none()
        if not module:
            return []
        return (module.settings or {}).get("planning_group_ids", [])

    async def _get_planning_groups(self) -> List[AgendaPlanningGroup]:
        """Fetch selected groups ordered by tree (parent before child)."""
        group_ids = await self._get_planning_group_ids()
        if not group_ids:
            return []

        # Fetch all selected groups
        result = await self.db.execute(
            select(Group).where(Group.id.in_(group_ids))
        )
        groups = {g.id: g for g in result.scalars().all()}

        # Fetch parent-child relationships among selected groups
        gg_result = await self.db.execute(
            select(GroupGroup).where(
                GroupGroup.parent_group_id.in_(group_ids),
                GroupGroup.child_group_id.in_(group_ids),
            )
        )
        relationships = gg_result.scalars().all()

        # Build children map: parent_id -> [child_id, ...]
        children: Dict[int, List[int]] = defaultdict(list)
        has_parent: set[int] = set()
        for rel in relationships:
            children[rel.parent_group_id].append(rel.child_group_id)
            has_parent.add(rel.child_group_id)

        # Find roots: groups without a parent among selected groups
        roots = [gid for gid in group_ids if gid not in has_parent]

        # Sort roots by preferred display order (Structure, EDE, JWCAD, ...)
        def _preferred_key(gid: int) -> tuple[int, str]:
            g = groups[gid]
            label = (g.description or g.name or "").lower()
            for idx, preferred in enumerate(PLANNING_GROUP_ORDER):
                if preferred in label:
                    return (idx, label)
            return (len(PLANNING_GROUP_ORDER), label)

        roots.sort(key=_preferred_key)

        # DFS to order groups (parent before children)
        ordered: List[tuple[int, int, Optional[int]]] = []  # (group_id, depth, parent_id)
        visited: set[int] = set()

        def dfs(gid: int, depth: int, parent_id: Optional[int]) -> None:
            if gid in visited or gid not in groups:
                return
            visited.add(gid)
            ordered.append((gid, depth, parent_id))
            for child_id in children.get(gid, []):
                dfs(child_id, depth + 1, gid)

        for root_id in roots:
            dfs(root_id, 0, None)

        # Add any remaining groups not reached by DFS (no relationships)
        for gid in group_ids:
            if gid not in visited and gid in groups:
                dfs(gid, 0, None)

        return [
            AgendaPlanningGroup(
                id=gid,
                name=groups[gid].name,
                description=groups[gid].description,
                depth=depth,
                parent_id=parent_id,
            )
            for gid, depth, parent_id in ordered
        ]

    async def _get_planning_people(self) -> List[AgendaPlanningPerson]:
        """Fetch members of selected groups with group assignment."""
        planning_groups = await self._get_planning_groups()
        if not planning_groups:
            return []

        group_ids = [g.id for g in planning_groups]
        group_id_set = set(group_ids)

        # Map: group_id -> position in ordered list (for first-group assignment)
        group_order: Dict[int, int] = {gid: idx for idx, gid in enumerate(group_ids)}

        # Fetch user-group memberships for selected groups
        ug_result = await self.db.execute(
            select(UserGroup).where(UserGroup.group_id.in_(group_ids))
        )
        memberships = ug_result.scalars().all()

        # Group users by user_id -> set of group_ids
        user_groups: Dict[int, set[int]] = defaultdict(set)
        for m in memberships:
            user_groups[m.user_id].add(m.group_id)

        if not user_groups:
            return []

        # Fetch users (actifs uniquement)
        user_ids = list(user_groups.keys())
        u_result = await self.db.execute(
            select(User).where(User.id.in_(user_ids), User.is_active.is_(True))
        )
        users = {u.id: u for u in u_result.scalars().all()}

        # Build people list: one row per person, assigned to first group in order
        people: List[AgendaPlanningPerson] = []
        for user_id, user in users.items():
            user_group_ids = user_groups.get(user_id, set())
            # Find the first group in the ordered list
            assigned_group_id = min(user_group_ids, key=lambda gid: group_order.get(gid, float('inf')))
            # Format name: "NOM Prénom" (last name uppercase, first name)
            last_name = user.last_name or ""
            first_name = user.first_name or ""
            display_name = f"{last_name.upper()} {first_name}".strip()
            if not display_name:
                display_name = user.full_name or user.username
            people.append(
                AgendaPlanningPerson(
                    person_id=user_id,
                    name=display_name,
                    group_id=assigned_group_id,
                    last_name=user.last_name,
                    first_name=user.first_name,
                )
            )

        # Sort by last name then first name
        people.sort(key=lambda p: ((p.last_name or "").lower(), (p.first_name or "").lower()))
        return people

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
            presences_stmt = presences_stmt.where(
                or_(
                    AgendaPresence.room_id.in_(room_ids),
                    AgendaPresence.room_id.is_(None),
                )
            )
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
            remote_items: List[AgendaPresenceItem] = []

            for p in by_day.get(day, []):
                if p.user_id:
                    user = users.get(p.user_id)
                    name = user.full_name if user else f"Utilisateur #{p.user_id}"
                    person_type = "user"
                    person_id = p.user_id
                else:
                    name = p.external_name or " externe"
                    person_type = "external"
                    person_id = None
                item = AgendaPresenceItem(
                    id=p.id,
                    person_type=person_type,
                    person_id=person_id,
                    person_name=name,
                    room_id=p.room_id,
                    needs_workstation=p.needs_workstation,
                    needs_meal=p.needs_meal,
                    is_remote=p.is_remote,
                    source=p.source,
                    is_mine=bool(p.user_id and p.user_id == self.current_user.id),
                    origin_ref=p.source_ref,
                    period=p.period or "full",
                )
                if p.room_id is None:
                    # Télétravail : compté dans le total du jour,
                    # jamais dans les compteurs de local.
                    remote_items.append(item)
                    total_present += 1
                    continue
                counter = room_counters.get(p.room_id)
                if counter is None:
                    continue
                counter.present_count += 1
                total_present += 1
                if p.needs_workstation:
                    counter.workstation_count += 1
                    total_workstations += 1
                counter.presences.append(item)

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
                    remote=remote_items,
                    integrated=integrated,
                )
            )

        planning_groups = await self._get_planning_groups()
        planning_people = await self._get_planning_people()

        return AgendaPlanningResponse(
            view=view,  # type: ignore[arg-type]
            start_date=start,
            end_date=end,
            rooms=rooms,
            days=days,
            planning_groups=planning_groups,
            planning_people=planning_people,
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

        # Un télétravail ne consomme ni poste de travail ni repas et n'a
        # aucun local (invariant : room_id NULL <=> is_remote = 1).
        is_remote = bool(payload.is_remote)
        room_id = None if is_remote else payload.room_id
        if not is_remote and room_id is None:
            raise ValueError("Local requis pour une présence sur site")
        needs_workstation = False if is_remote else payload.needs_workstation
        needs_meal = False if is_remote else payload.needs_meal

        if not payload.is_present:
            # "Absent" = hide own presence but keep the row as a manual decision
            # (the auto-assign will never recreate a day that already has a row)
            existing = await self._find_own_presence(
                payload.presence_date, room_id, user_id=owner_id
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
                room_id=room_id,
                user_id=owner_id,
                external_name=None,
                source="user",
                is_present=False,
                needs_workstation=needs_workstation,
                needs_meal=needs_meal,
                is_remote=is_remote,
                period=payload.period,
                created_by=self.current_user.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

        if not is_remote:
            await self._ensure_room_exists(room_id)
            # Le matin peut se passer dans un local et l'après-midi dans un
            # autre : seules les présences des autres locaux qui chevauchent
            # la période demandée sont retirées.
            await self._remove_other_locals(
                payload.presence_date, owner_id, keep_room_id=room_id, period=payload.period
            )
        existing = await self._find_own_presence(
            payload.presence_date, room_id, user_id=owner_id
        )

        if existing:
            existing.needs_workstation = needs_workstation
            existing.needs_meal = needs_meal
            existing.is_remote = is_remote
            existing.is_present = True
            # Pas de fusion matin/après-midi : la période demandée remplace la
            # précédente (y compris la période conservée après une annulation),
            # sinon décocher une demi-journée ou en cocher une seule est impossible.
            existing.period = payload.period
            presence = existing
        else:
            presence = AgendaPresence(
                presence_date=payload.presence_date,
                room_id=room_id,
                user_id=owner_id,
                external_name=None,
                source="user",
                is_present=True,
                # Le poste est auto-coché selon la préférence de l'utilisateur
                # (jamais en télétravail : ni poste ni repas).
                needs_workstation=bool(needs_workstation)
                or (not is_remote and await self._pref_needs_workstation(owner_id)),
                needs_meal=needs_meal or (not is_remote and payload.period == "full"),
                is_remote=is_remote,
                period=payload.period,
                created_by=self.current_user.id,
            )
            self.db.add(presence)

        # Exclusivité par demi-journée : la présence de l'autre nature qui
        # chevauche cette période est rétrécie ou retirée automatiquement.
        await self._resolve_half_day_overlap(
            payload.presence_date,
            owner_id,
            keep_remote=is_remote,
            period=payload.period,
        )
        if not is_remote and needs_meal:
            # Un seul repas par jour : le repas suit la présence qui vient
            # d'être cochée, les autres locaux du jour le perdent.
            await self._migrate_meal(
                payload.presence_date, owner_id, exclude_presence_id=presence.id
            )

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
        # Les inscriptions libres sont toujours sur site (pas de télétravail).
        presence = AgendaPresence(
            presence_date=payload.presence_date,
            room_id=payload.room_id,
            user_id=None,
            external_name=payload.external_name.strip(),
            source="manual",
            is_present=True,
            needs_workstation=payload.needs_workstation,
            needs_meal=payload.needs_meal,
            is_remote=False,
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
        is_remote: Optional[bool] = None,
        is_present: Optional[bool] = None,
        period: Optional[str] = None,
        room_id: Optional[int] = None,
    ) -> AgendaPresenceResponse:
        presence = await self.get_presence(presence_id)
        if not presence:
            raise LookupError("Présence introuvable")
        # Un télétravail ne consomme ni poste de travail ni repas et n'a
        # aucun local (invariant : room_id NULL <=> is_remote = 1).
        next_remote = presence.is_remote if is_remote is None else bool(is_remote)
        if next_remote:
            needs_workstation = False
            needs_meal = False
            room_id = None
        elif room_id is None and presence.room_id is None:
            raise ValueError("Local requis pour une présence sur site")
        next_period = period if period is not None else presence.period
        next_room = room_id if room_id is not None else presence.room_id
        if next_room is not None and next_room != presence.room_id:
            await self._ensure_room_exists(next_room)
            if presence.user_id is not None:
                clash = await self._find_own_presence(
                    presence.presence_date, next_room, user_id=presence.user_id
                )
                if clash and clash.id != presence.id:
                    # Fusionner avec la présence existante dans le nouveau local
                    merged_period = _merge_periods(clash.period, next_period)
                    clash.period = merged_period
                    # Auto-cocher poste/repas selon la période fusionnée
                    if clash.period == "full":
                        clash.needs_workstation = True
                        clash.needs_meal = True
                    else:
                        clash.needs_workstation = True
                    if clash.needs_meal and clash.user_id is not None:
                        # Un seul repas par jour : le repas migre sur la
                        # présence qui reste.
                        await self._migrate_meal(
                            clash.presence_date, clash.user_id, exclude_presence_id=clash.id
                        )
                    # Supprimer la présence qu'on déplace
                    await self.db.delete(presence)
                    await self.db.commit()
                    await self.db.refresh(clash)
                    return AgendaPresenceResponse.model_validate(clash)
        next_present = presence.is_present if is_present is None else is_present
        if next_room is not None and next_present and presence.user_id is not None:
            # Un seul local par demi-journée : l'autre local qui chevauche
            # cette période est retiré automatiquement (jamais d'erreur).
            await self._remove_other_locals(
                presence.presence_date,
                presence.user_id,
                keep_room_id=next_room,
                period=next_period,
                exclude_presence_id=presence.id,
            )
        if needs_workstation is not None:
            presence.needs_workstation = needs_workstation
        if needs_meal is not None:
            presence.needs_meal = needs_meal
        presence.is_remote = next_remote
        if is_present is not None:
            presence.is_present = is_present
        if period is not None:
            presence.period = period
        if next_room != presence.room_id:
            presence.room_id = next_room
        if next_present and presence.user_id is not None:
            # Exclusivité télétravail / présence locale : comme lors d'une
            # inscription, la période mise à jour retire ou rétrécit la
            # présence de l'autre nature (télétravail complet = plus de
            # présence sur site, ni repas ni poste).
            await self._resolve_half_day_overlap(
                presence.presence_date,
                presence.user_id,
                keep_remote=next_remote,
                period=next_period,
                exclude_presence_id=presence.id,
            )
        if next_present and not next_remote and presence.needs_meal and presence.user_id is not None:
            # Un seul repas par jour : le repas migre sur la présence cochée.
            await self._migrate_meal(
                presence.presence_date, presence.user_id, exclude_presence_id=presence.id
            )
        await self.db.commit()
        await self.db.refresh(presence)
        return AgendaPresenceResponse.model_validate(presence)

    async def _resolve_half_day_overlap(
        self,
        day: date,
        owner_id: int,
        *,
        keep_remote: bool,
        period: str,
        exclude_presence_id: Optional[int] = None,
    ) -> None:
        """Exclusivité par demi-journée entre télétravail et présence locale.

        Les présences de l'autre nature qui chevauchent ``period`` sont
        retirées automatiquement (jamais d'erreur) : une présence couvrant
        toute la journée est réduite à l'autre moitié, sinon elle est
        supprimée. Les drapeaux repas/poste d'une présence réduite sont
        conservés tant qu'une présence locale subsiste.
        """
        stmt = select(AgendaPresence).where(
            AgendaPresence.presence_date == day,
            AgendaPresence.user_id == owner_id,
            AgendaPresence.is_present.is_(True),
        )
        if keep_remote:
            stmt = stmt.where(AgendaPresence.room_id.is_not(None))
        else:
            stmt = stmt.where(AgendaPresence.room_id.is_(None))
        if exclude_presence_id is not None:
            stmt = stmt.where(AgendaPresence.id != exclude_presence_id)
        rows = (await self.db.execute(stmt)).scalars().all()
        for row in rows:
            if not _periods_overlap(period, row.period or "full"):
                continue
            if row.period == "full" and period != "full":
                row.period = "morning" if period == "afternoon" else "afternoon"
            else:
                await self.db.delete(row)

    async def _pref_needs_workstation(self, owner_id: Optional[int]) -> bool:
        """Préférence utilisateur « besoin d'un poste » (désactivée par défaut)."""
        if owner_id is None:
            return False
        if self.current_user is not None and self.current_user.id == owner_id:
            return bool(self.current_user.default_needs_workstation)
        owner = await self.db.get(User, owner_id)
        return bool(owner.default_needs_workstation) if owner is not None else False

    async def _migrate_meal(
        self,
        day: date,
        owner_id: Optional[int],
        *,
        exclude_presence_id: Optional[int] = None,
    ) -> None:
        """Un seul repas par jour.

        Le repas est porté par la présence qui vient d'être cochée : les
        autres présences locales du même jour le perdent (migration, jamais
        d'erreur). Les lignes de télétravail ne portent jamais de repas.
        """
        if owner_id is None:
            return
        stmt = select(AgendaPresence).where(
            AgendaPresence.presence_date == day,
            AgendaPresence.user_id == owner_id,
            AgendaPresence.room_id.is_not(None),
            AgendaPresence.is_present.is_(True),
            AgendaPresence.needs_meal.is_(True),
        )
        if exclude_presence_id is not None:
            stmt = stmt.where(AgendaPresence.id != exclude_presence_id)
        rows = (await self.db.execute(stmt)).scalars().all()
        for row in rows:
            row.needs_meal = False

    async def _remove_other_locals(
        self,
        day: date,
        owner_id: Optional[int],
        *,
        keep_room_id: int,
        period: str,
        exclude_presence_id: Optional[int] = None,
    ) -> None:
        """Recouvrement par demi-journée entre locaux.

        Le matin peut se passer dans un local et l'après-midi dans un autre :
        seules les présences des autres locaux qui chevauchent ``period`` sont
        retirées (une présence couvrant la journée est réduite à l'autre
        moitié, sinon elle est supprimée). Un clic sur le même matin dans un
        autre local migre donc l'inscription, l'après-midi reste en place.
        Les lignes de télétravail (``room_id`` NULL) ne sont pas concernées.
        """
        if owner_id is None:
            return
        stmt = select(AgendaPresence).where(
            AgendaPresence.presence_date == day,
            AgendaPresence.user_id == owner_id,
            AgendaPresence.room_id.is_not(None),
            AgendaPresence.room_id != keep_room_id,
            AgendaPresence.is_present.is_(True),
        )
        if exclude_presence_id is not None:
            stmt = stmt.where(AgendaPresence.id != exclude_presence_id)
        rows = (await self.db.execute(stmt)).scalars().all()
        for row in rows:
            if not _periods_overlap(period, row.period or "full"):
                continue
            if row.period == "full" and period != "full":
                row.period = "morning" if period == "afternoon" else "afternoon"
            else:
                await self.db.delete(row)

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
            # room_id None = ligne de télétravail (sans local).
            AgendaPresence.room_id.is_(None)
            if room_id is None
            else AgendaPresence.room_id == room_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _ensure_room_exists(self, room_id: int) -> None:
        room = await self.db.get(Room, room_id)
        if not room or not room.is_active:
            raise LookupError("Local introuvable ou inactif")
