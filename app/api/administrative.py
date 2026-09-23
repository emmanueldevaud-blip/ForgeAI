from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.models.administrative import AdministrativeCapability, AdministrativeProgramType, AdministrativeRoleType, VolunteerUnavailability
from app.schemas.administrative import (
    AssignmentCreate, AssignmentResponse, AssignmentUpdate, CapabilityCreate, CapabilityResponse,
    GenerationResponse, ProgramTypeCreate, ProgramTypeResponse, RoleTypeCreate,
    RoleTypeResponse, SessionCreate, SessionResponse, UnavailabilityCreate,
    UnavailabilityResponse, ValidationResponse, VolunteerCapabilityCreate,
    VolunteerCapabilityResponse,
)
from app.services.administrative import AdministrativeService

router = APIRouter(prefix="/administration", tags=["administration-programs"])


def service_for(permission: str):
    async def dependency(
        _: object = Depends(require_permission(permission)),
        db: AsyncSession = Depends(get_db),
    ) -> AdministrativeService:
        return AdministrativeService(db)
    return dependency


def _bad_request(exc: ValueError):
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/programs/capabilities", response_model=list[CapabilityResponse])
async def list_capabilities(service: AdministrativeService = Depends(service_for("administration.programs.view"))):
    return (await service.db.execute(select(AdministrativeCapability).order_by(AdministrativeCapability.name))).scalars().all()


@router.post("/programs/capabilities", response_model=CapabilityResponse, status_code=201)
async def create_capability(data: CapabilityCreate, service: AdministrativeService = Depends(service_for("administration.programs.configure"))):
    try:
        return await service.add_capability(data)
    except ValueError as exc:
        _bad_request(exc)


@router.post("/programs/volunteers/{volunteer_id}/capabilities", response_model=VolunteerCapabilityResponse, status_code=201)
async def assign_capability(volunteer_id: int, data: VolunteerCapabilityCreate, service: AdministrativeService = Depends(service_for("administration.programs.manage"))):
    try:
        return await service.add_volunteer_capability(volunteer_id, data)
    except ValueError as exc:
        _bad_request(exc)


@router.get("/programs/volunteers/{volunteer_id}/capabilities", response_model=list[VolunteerCapabilityResponse])
async def list_volunteer_capabilities(volunteer_id: int, service: AdministrativeService = Depends(service_for("administration.programs.view"))):
    return await service.list_volunteer_capabilities(volunteer_id)


@router.delete("/programs/volunteers/{volunteer_id}/capabilities/{capability_id}", status_code=204)
async def delete_volunteer_capability(volunteer_id: int, capability_id: int, service: AdministrativeService = Depends(service_for("administration.programs.manage"))):
    if not await service.delete_volunteer_capability(volunteer_id, capability_id):
        raise HTTPException(status_code=404, detail="Capacité introuvable")


@router.get("/programs/unavailabilities", response_model=list[UnavailabilityResponse])
async def list_unavailabilities(volunteer_id: int | None = None, service: AdministrativeService = Depends(service_for("administration.programs.view"))):
    return await service.list_unavailabilities(volunteer_id)


@router.post("/programs/unavailabilities", response_model=UnavailabilityResponse, status_code=201)
async def create_unavailability(data: UnavailabilityCreate, service: AdministrativeService = Depends(service_for("administration.programs.manage"))):
    try:
        return await service.add_unavailability(data)
    except ValueError as exc:
        _bad_request(exc)


@router.get("/programs/volunteers/{volunteer_id}/unavailabilities", response_model=list[UnavailabilityResponse])
async def list_volunteer_unavailabilities(volunteer_id: int, service: AdministrativeService = Depends(service_for("administration.programs.view"))):
    return await service.list_unavailabilities(volunteer_id)


@router.delete("/programs/unavailabilities/{unavailability_id}", status_code=204)
async def delete_unavailability(unavailability_id: int, service: AdministrativeService = Depends(service_for("administration.programs.manage"))):
    if not await service.delete_unavailability(unavailability_id):
        raise HTTPException(status_code=404, detail="Indisponibilité introuvable")


@router.get("/programs/types", response_model=list[ProgramTypeResponse])
async def list_program_types(service: AdministrativeService = Depends(service_for("administration.programs.view"))):
    return (await service.db.execute(select(AdministrativeProgramType).order_by(AdministrativeProgramType.name))).scalars().all()


@router.post("/programs/types", response_model=ProgramTypeResponse, status_code=201)
async def create_program_type(data: ProgramTypeCreate, service: AdministrativeService = Depends(service_for("administration.programs.configure"))):
    try:
        return await service.add_program_type(data)
    except ValueError as exc:
        _bad_request(exc)


@router.get("/programs/roles", response_model=list[RoleTypeResponse])
async def list_role_types(service: AdministrativeService = Depends(service_for("administration.programs.view"))):
    return (await service.db.execute(select(AdministrativeRoleType).order_by(AdministrativeRoleType.program_type_id, AdministrativeRoleType.id))).scalars().all()


@router.post("/programs/roles", response_model=RoleTypeResponse, status_code=201)
async def create_role_type(data: RoleTypeCreate, service: AdministrativeService = Depends(service_for("administration.programs.configure"))):
    try:
        return await service.add_role_type(data)
    except ValueError as exc:
        _bad_request(exc)


@router.get("/programs/sessions", response_model=list[SessionResponse])
async def list_sessions(year: int | None = None, month: int | None = None, service: AdministrativeService = Depends(service_for("administration.programs.view"))):
    return await service.list_sessions(year, month)


@router.post("/programs/sessions", response_model=SessionResponse, status_code=201)
async def create_session(data: SessionCreate, service: AdministrativeService = Depends(service_for("administration.programs.manage"))):
    try:
        return await service.create_session(data)
    except ValueError as exc:
        _bad_request(exc)


@router.post("/programs/sessions/{session_id}/generate", response_model=GenerationResponse)
async def generate_session(session_id: int, service: AdministrativeService = Depends(service_for("administration.programs.manage"))):
    try:
        session, conflicts = await service.generate(session_id)
        return {"session": session, "conflicts": conflicts}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/programs/sessions/{session_id}/history", response_model=list[AssignmentResponse])
async def session_history(session_id: int, service: AdministrativeService = Depends(service_for("administration.programs.view"))):
    session = await service._session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    return session.assignments


@router.put("/programs/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(assignment_id: int, data: AssignmentUpdate, service: AdministrativeService = Depends(service_for("administration.programs.manage"))):
    try:
        return await service.update_assignment(assignment_id, data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        _bad_request(exc)


@router.post("/programs/assignments", response_model=AssignmentResponse, status_code=201)
async def create_assignment(data: AssignmentCreate, service: AdministrativeService = Depends(service_for("administration.programs.manage"))):
    try:
        return await service.create_assignment(data)
    except ValueError as exc:
        _bad_request(exc)


@router.post("/programs/sessions/{session_id}/validate", response_model=ValidationResponse)
async def validate_session(session_id: int, service: AdministrativeService = Depends(service_for("administration.programs.validate"))):
    try:
        session, conflicts = await service.validate(session_id)
        return {"valid": not conflicts, "conflicts": conflicts, "session": session}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
