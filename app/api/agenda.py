from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.models.module import Module
from app.models.rbac import Group, UserGroup
from app.models.user import User
from app.schemas.agenda import (
    AgendaAutoAssignRequest,
    AgendaAutoAssignResponse,
    AgendaExternalPresenceCreate,
    AgendaGroupListResponse,
    AgendaGroupOption,
    AgendaPlanningResponse,
    AgendaPresenceResponse,
    AgendaPresenceUpsert,
    AgendaSettingsResponse,
    AgendaSettingsUpdate,
    AgendaUserResponse,
)
from app.services.agenda import AgendaService
from app.services.rbac import RBACService

router = APIRouter(prefix="/agenda", tags=["agenda"])


class AgendaPresenceUpdate(BaseModel):
    needs_workstation: Optional[bool] = None
    needs_meal: Optional[bool] = None
    is_present: Optional[bool] = None
    period: Optional[str] = None
    room_id: Optional[int] = None


async def get_agenda_service(
    current_user: User = Depends(require_permission("agenda.access")),
    db: AsyncSession = Depends(get_db),
) -> AgendaService:
    return AgendaService(db, current_user)


async def _get_agenda_settings(db: AsyncSession) -> list[int]:
    """Retrieve planning_group_ids from module settings."""
    result = await db.execute(
        select(Module.settings).where(Module.code == "agenda")
    )
    row = result.scalar_one_or_none()
    if not row:
        return []
    return row.get("planning_group_ids", [])


async def _save_agenda_settings(db: AsyncSession, group_ids: list[int]) -> list[int]:
    """Save planning_group_ids to module settings after dedup and validation."""
    # Dedup while preserving order
    seen: set[int] = set()
    unique_ids: list[int] = []
    for gid in group_ids:
        if gid not in seen:
            seen.add(gid)
            unique_ids.append(gid)

    # Validate: keep only existing groups
    if unique_ids:
        result = await db.execute(
            select(Group.id).where(Group.id.in_(unique_ids))
        )
        valid_ids = set(result.scalars().all())
        unique_ids = [gid for gid in unique_ids if gid in valid_ids]

    # Update or create module settings
    module_result = await db.execute(
        select(Module).where(Module.code == "agenda")
    )
    module = module_result.scalar_one_or_none()
    if not module:
        module = Module(
            code="agenda",
            name="Agenda",
            status="active",
            settings={},
        )
        db.add(module)
        await db.flush()

    if module.settings is None:
        module.settings = {}
    new_settings = dict(module.settings)
    new_settings["planning_group_ids"] = unique_ids
    module.settings = new_settings
    await db.commit()

    return unique_ids


@router.get("/planning", response_model=AgendaPlanningResponse)
async def get_planning(
    view: str = Query("week", pattern="^(week|month)$"),
    anchor: Optional[date] = Query(None, description="Date de référence (aujourd'hui par défaut)"),
    service: AgendaService = Depends(get_agenda_service),
):
    try:
        return await service.get_planning(view, anchor or date.today())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/settings", response_model=AgendaSettingsResponse)
async def get_settings(
    current_user: User = Depends(require_permission("agenda.manage")),
    db: AsyncSession = Depends(get_db),
):
    group_ids = await _get_agenda_settings(db)
    return AgendaSettingsResponse(planning_group_ids=group_ids)


@router.put("/settings", response_model=AgendaSettingsResponse)
async def update_settings(
    payload: AgendaSettingsUpdate,
    current_user: User = Depends(require_permission("agenda.manage")),
    db: AsyncSession = Depends(get_db),
):
    saved_ids = await _save_agenda_settings(db, payload.planning_group_ids)
    return AgendaSettingsResponse(planning_group_ids=saved_ids)


@router.get("/groups", response_model=AgendaGroupListResponse)
async def list_groups(
    current_user: User = Depends(require_permission("agenda.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Group).where(Group.is_active.is_(True)).order_by(Group.name)
    )
    groups = result.scalars().all()
    if not groups:
        return AgendaGroupListResponse(groups=[])

    group_ids = [g.id for g in groups]
    # Count members per group
    from sqlalchemy import func as sa_func
    count_result = await db.execute(
        select(UserGroup.group_id, sa_func.count(UserGroup.user_id))
        .where(UserGroup.group_id.in_(group_ids))
        .group_by(UserGroup.group_id)
    )
    counts = dict(count_result.all())

    return AgendaGroupListResponse(
        groups=[
            AgendaGroupOption(
                id=g.id,
                name=g.name,
                description=g.description,
                source=g.source,
                user_count=counts.get(g.id, 0),
            )
            for g in groups
        ]
    )


@router.get("/users", response_model=list[AgendaUserResponse])
async def list_agenda_users(
    current_user: User = Depends(require_permission("agenda.manage")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.last_name, User.first_name))
    return [AgendaUserResponse.model_validate(u) for u in result.scalars().all()]


@router.post("/presences", response_model=AgendaPresenceResponse)
async def upsert_own_presence(
    payload: AgendaPresenceUpsert,
    current_user: User = Depends(require_permission("agenda.access")),
    db: AsyncSession = Depends(get_db),
):
    if payload.user_id is not None and payload.user_id != current_user.id:
        rbac = RBACService(db)
        if not await rbac.user_has_permission(current_user, "agenda.manage"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission 'agenda.manage' requise",
            )
    service = AgendaService(db, current_user)
    try:
        return await service.upsert_own_presence(payload, target_user_id=payload.user_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/presences/external",
    response_model=AgendaPresenceResponse,
)
async def create_external_presence(
    payload: AgendaExternalPresenceCreate,
    current_user: User = Depends(require_permission("agenda.manage")),
    db: AsyncSession = Depends(get_db),
):
    service = AgendaService(db, current_user)
    try:
        return await service.create_external_presence(payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/presences/auto-assign", response_model=AgendaAutoAssignResponse)
async def auto_assign_own_presences(
    payload: AgendaAutoAssignRequest,
    service: AgendaService = Depends(get_agenda_service),
):
    return await service.auto_assign_own_presences(payload.start_date, payload.end_date)


@router.patch("/presences/{presence_id}", response_model=AgendaPresenceResponse)
async def update_presence(
    presence_id: int,
    payload: AgendaPresenceUpdate,
    current_user: User = Depends(require_permission("agenda.access")),
    db: AsyncSession = Depends(get_db),
):
    service = AgendaService(db, current_user)
    presence = await service.get_presence(presence_id)
    if not presence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Présence introuvable")

    is_owner = presence.user_id == current_user.id
    if not is_owner:
        rbac = RBACService(db)
        if not await rbac.user_has_permission(current_user, "agenda.manage"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission 'agenda.manage' requise")

    try:
        return await service.update_presence(
            presence_id,
            needs_workstation=payload.needs_workstation,
            needs_meal=payload.needs_meal,
            is_present=payload.is_present,
            period=payload.period,
            room_id=payload.room_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("/presences/{presence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_presence(
    presence_id: int,
    current_user: User = Depends(require_permission("agenda.access")),
    db: AsyncSession = Depends(get_db),
):
    service = AgendaService(db, current_user)
    presence = await service.get_presence(presence_id)
    if not presence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Présence introuvable")

    is_owner = presence.user_id == current_user.id or (
        presence.user_id is None and presence.created_by == current_user.id
    )
    if not is_owner:
        rbac = RBACService(db)
        if not await rbac.user_has_permission(current_user, "agenda.manage"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission 'agenda.manage' requise")

    await service.delete_presence(presence_id)
    return None
