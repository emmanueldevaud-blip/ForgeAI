from calendar import monthrange
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.administrative import (
    AdministrativeAssignment, AdministrativeCapability, AdministrativeMonthlySession,
    AdministrativeProgramType, AdministrativeRoleType, VolunteerCapability,
    VolunteerUnavailability,
)
from app.models.volunteer import Volunteer
from app.schemas.administrative import (
    AssignmentCreate, AssignmentUpdate, CapabilityCreate, ProgramTypeCreate, RoleTypeCreate,
    SessionCreate, UnavailabilityCreate, VolunteerCapabilityCreate,
)


class AdministrativeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _session(self, session_id: int) -> AdministrativeMonthlySession | None:
        result = await self.db.execute(
            select(AdministrativeMonthlySession).options(selectinload(AdministrativeMonthlySession.assignments), selectinload(AdministrativeMonthlySession.program_type)).where(AdministrativeMonthlySession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_sessions(self, year: int | None = None, month: int | None = None):
        query = select(AdministrativeMonthlySession).options(selectinload(AdministrativeMonthlySession.assignments)).order_by(AdministrativeMonthlySession.year, AdministrativeMonthlySession.month, AdministrativeMonthlySession.id)
        if year is not None:
            query = query.where(AdministrativeMonthlySession.year == year)
        if month is not None:
            query = query.where(AdministrativeMonthlySession.month == month)
        return (await self.db.execute(query)).scalars().unique().all()

    async def create_session(self, data: SessionCreate):
        session = AdministrativeMonthlySession(**data.model_dump())
        self.db.add(session)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise ValueError("Cette séance mensuelle existe déjà")
        return await self._session(session.id)

    async def add_capability(self, data: CapabilityCreate):
        capability = AdministrativeCapability(**data.model_dump())
        self.db.add(capability)
        await self.db.commit()
        await self.db.refresh(capability)
        return capability

    async def add_volunteer_capability(self, volunteer_id: int, data: VolunteerCapabilityCreate):
        if not await self.db.get(Volunteer, volunteer_id) or not await self.db.get(AdministrativeCapability, data.capability_id):
            raise ValueError("Volontaire ou capacité introuvable")
        link = VolunteerCapability(volunteer_id=volunteer_id, **data.model_dump())
        self.db.add(link)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise ValueError("Cette capacité est déjà associée au volontaire")
        await self.db.refresh(link)
        return link

    async def add_unavailability(self, data: UnavailabilityCreate):
        if data.ends_on < data.starts_on:
            raise ValueError("La date de fin doit être postérieure ou égale à la date de début")
        if not await self.db.get(Volunteer, data.volunteer_id):
            raise ValueError("Volontaire introuvable")
        item = VolunteerUnavailability(**data.model_dump())
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_volunteer_capabilities(self, volunteer_id: int):
        result = await self.db.execute(
            select(VolunteerCapability).where(VolunteerCapability.volunteer_id == volunteer_id).order_by(VolunteerCapability.capability_id)
        )
        return result.scalars().all()

    async def delete_volunteer_capability(self, volunteer_id: int, capability_id: int) -> bool:
        item = await self.db.get(VolunteerCapability, (volunteer_id, capability_id))
        if not item:
            return False
        await self.db.delete(item)
        await self.db.commit()
        return True

    async def list_unavailabilities(self, volunteer_id: int | None = None):
        query = select(VolunteerUnavailability).order_by(VolunteerUnavailability.starts_on)
        if volunteer_id is not None:
            query = query.where(VolunteerUnavailability.volunteer_id == volunteer_id)
        return (await self.db.execute(query)).scalars().all()

    async def delete_unavailability(self, unavailability_id: int) -> bool:
        item = await self.db.get(VolunteerUnavailability, unavailability_id)
        if not item:
            return False
        await self.db.delete(item)
        await self.db.commit()
        return True

    async def add_program_type(self, data: ProgramTypeCreate):
        item = AdministrativeProgramType(**data.model_dump())
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def add_role_type(self, data: RoleTypeCreate):
        if not await self.db.get(AdministrativeProgramType, data.program_type_id):
            raise ValueError("Type de programme introuvable")
        item = AdministrativeRoleType(**data.model_dump())
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def _conflicts(self, session: AdministrativeMonthlySession, assignments: list[AdministrativeAssignment]) -> list[str]:
        first = date(session.year, session.month, 1)
        last = date(session.year, session.month, monthrange(session.year, session.month)[1])
        conflicts = []
        for assignment in assignments:
            volunteer = await self.db.get(Volunteer, assignment.volunteer_id)
            if not volunteer or not volunteer.is_active:
                conflicts.append(f"affectation {assignment.id}: volontaire inactif ou introuvable")
                continue
            if any(a.volunteer_id == assignment.volunteer_id and a.scheduled_date == assignment.scheduled_date for a in assignments if a.id != assignment.id):
                conflicts.append(f"affectation {assignment.id}: volontaire déjà affecté à cette date")
            role = await self.db.get(AdministrativeRoleType, assignment.role_type_id)
            if not role or role.program_type_id != session.program_type_id:
                conflicts.append(f"affectation {assignment.id}: rôle incompatible avec le programme")
                continue
            if role.required_capability_id:
                capable = await self.db.execute(select(VolunteerCapability).where(VolunteerCapability.volunteer_id == volunteer.id, VolunteerCapability.capability_id == role.required_capability_id))
                if not capable.scalar_one_or_none():
                    conflicts.append(f"affectation {assignment.id}: capacité requise absente")
            if assignment.scheduled_date < first or assignment.scheduled_date > last:
                conflicts.append(f"affectation {assignment.id}: date hors de la session mensuelle")
            unavailable = await self.db.execute(select(VolunteerUnavailability).where(VolunteerUnavailability.volunteer_id == volunteer.id, VolunteerUnavailability.starts_on <= assignment.scheduled_date, VolunteerUnavailability.ends_on >= assignment.scheduled_date))
            if unavailable.scalar_one_or_none():
                conflicts.append(f"affectation {assignment.id}: volontaire indisponible")
        return conflicts

    async def generate(self, session_id: int):
        session = await self._session(session_id)
        if not session:
            raise LookupError("Séance introuvable")
        program = session.program_type
        dates = []
        for day in range(1, monthrange(session.year, session.month)[1] + 1):
            current = date(session.year, session.month, day)
            if current.weekday() == program.weekday and (
                program.frequency == "monthly" and not dates
                or program.frequency != "monthly" and ((day - 1) // 7) % program.interval == 0
            ):
                dates.append(current)
        roles = (await self.db.execute(select(AdministrativeRoleType).where(AdministrativeRoleType.program_type_id == session.program_type_id, AdministrativeRoleType.is_active.is_(True)).order_by(AdministrativeRoleType.id))).scalars().all()
        volunteers = (await self.db.execute(select(Volunteer).where(Volunteer.is_active.is_(True)).order_by(Volunteer.id))).scalars().all()
        participation_counts = dict((await self.db.execute(
            select(AdministrativeAssignment.volunteer_id, func.count(AdministrativeAssignment.id))
            .group_by(AdministrativeAssignment.volunteer_id)
        )).all())
        session_counts = {volunteer.id: sum(1 for assignment in session.assignments if assignment.volunteer_id == volunteer.id) for volunteer in volunteers}
        conflicts = []
        for scheduled_date in dates:
            used = {a.volunteer_id for a in session.assignments if a.scheduled_date == scheduled_date}
            for role in roles:
                if any(a.role_type_id == role.id and a.scheduled_date == scheduled_date for a in session.assignments):
                    continue
                candidates = []
                for volunteer in volunteers:
                    if volunteer.id in used:
                        continue
                    candidate = AdministrativeAssignment(session_id=session.id, role_type_id=role.id, volunteer_id=volunteer.id, scheduled_date=scheduled_date, source="generated")
                    if not await self._conflicts(session, [candidate]):
                        candidates.append(volunteer)
                if not candidates:
                    if not role.is_optional:
                        conflicts.append(f"{scheduled_date} - {role.name}: aucun volontaire compatible disponible")
                    continue
                volunteer = min(
                    candidates,
                    key=lambda item: (
                        session_counts.get(item.id, 0),
                        participation_counts.get(item.id, 0),
                        item.id,
                    ),
                )
                assignment = AdministrativeAssignment(session_id=session.id, role_type_id=role.id, volunteer_id=volunteer.id, scheduled_date=scheduled_date, source="generated")
                self.db.add(assignment)
                session.assignments.append(assignment)
                used.add(volunteer.id)
                session_counts[volunteer.id] = session_counts.get(volunteer.id, 0) + 1
        await self.db.commit()
        session = await self._session(session_id)
        return session, [*conflicts, *(await self._conflicts(session, session.assignments))]

    async def update_assignment(self, assignment_id: int, data: AssignmentUpdate):
        assignment = await self.db.get(AdministrativeAssignment, assignment_id)
        if not assignment:
            raise LookupError("Affectation introuvable")
        assignment.volunteer_id = data.volunteer_id
        if data.scheduled_date is not None:
            assignment.scheduled_date = data.scheduled_date
        assignment.source = "manual"
        await self.db.flush()
        session = await self._session(assignment.session_id)
        conflicts = await self._conflicts(session, session.assignments)
        if conflicts:
            await self.db.rollback()
            raise ValueError("; ".join(conflicts))
        await self.db.commit()
        return assignment

    async def create_assignment(self, data: AssignmentCreate):
        session = await self._session(data.session_id)
        role = await self.db.get(AdministrativeRoleType, data.role_type_id)
        if not session or not role or role.program_type_id != session.program_type_id:
            raise ValueError("Séance ou rôle incompatible")
        existing = await self.db.execute(select(AdministrativeAssignment).where(AdministrativeAssignment.session_id == data.session_id, AdministrativeAssignment.role_type_id == data.role_type_id, AdministrativeAssignment.scheduled_date == data.scheduled_date))
        if existing.scalar_one_or_none():
            raise ValueError("Ce rôle est déjà affecté dans cette séance")
        assignment = AdministrativeAssignment(**data.model_dump(), source="manual")
        self.db.add(assignment)
        await self.db.flush()
        conflicts = await self._conflicts(session, [*session.assignments, assignment])
        if conflicts:
            await self.db.rollback()
            raise ValueError("; ".join(conflicts))
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def validate(self, session_id: int):
        session = await self._session(session_id)
        if not session:
            raise LookupError("Séance introuvable")
        conflicts = await self._conflicts(session, session.assignments)
        if not conflicts:
            session.status = "validated"
            for assignment in session.assignments:
                assignment.status = "validated"
            await self.db.commit()
        return session, conflicts
