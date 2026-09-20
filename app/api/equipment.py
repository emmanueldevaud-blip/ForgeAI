import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentListParams,
    EquipmentListResponse,
    EquipmentResponse,
    EquipmentTypeCreate,
    EquipmentTypeListParams,
    EquipmentTypeListResponse,
    EquipmentTypeResponse,
    EquipmentTypeUpdate,
    EquipmentUpdate,
    MessageResponse,
)
from app.services.audit import get_audit_service
from app.services.equipment import EquipmentService


router = APIRouter(
    prefix="/equipment",
    tags=["equipment"],
)


def _build_equipment_response(equipment) -> EquipmentResponse:
    resp = EquipmentResponse.model_validate(equipment)
    if equipment.room:
        from app.schemas.equipment import RoomSummaryResponse, LevelSummaryResponse, BuildingSummaryResponse, SiteSummaryResponse
        resp.room = RoomSummaryResponse.model_validate(equipment.room)
        if equipment.room.level:
            resp.level = LevelSummaryResponse.model_validate(equipment.room.level)
            if equipment.room.level.building:
                resp.building = BuildingSummaryResponse.model_validate(equipment.room.level.building)
                if equipment.room.level.building.site:
                    resp.site = SiteSummaryResponse.model_validate(equipment.room.level.building.site)
    return resp


def _get_equipment_service(
    current_user: User = Depends(require_permission("equipment.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = get_audit_service(db)
    return EquipmentService(db, audit=audit, current_user=current_user)


# ============================================================
# EQUIPMENT TYPES
# ============================================================

@router.get("/types")
async def list_equipment_types(
    page: int = 1,
    page_size: int = 20,
    search: str = None,
    is_active: bool = None,
    sort_by: str = "sort_order",
    sort_order: str = "asc",
    current_user: User = Depends(require_permission("equipment.view")),
    db: AsyncSession = Depends(get_db),
):
    service = EquipmentService(db, current_user=current_user)
    items, total = await service.search_equipment_types(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return EquipmentTypeListResponse(
        items=[EquipmentTypeResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/types/{equipment_type_id}", response_model=EquipmentTypeResponse)
async def get_equipment_type(
    equipment_type_id: int,
    current_user: User = Depends(require_permission("equipment.view")),
    db: AsyncSession = Depends(get_db),
):
    service = EquipmentService(db, current_user=current_user)
    equipment_type = await service.get_equipment_type(equipment_type_id)
    if not equipment_type:
        raise HTTPException(status_code=404, detail="Type d'équipement non trouvé")
    return EquipmentTypeResponse.model_validate(equipment_type)


@router.post("/types", response_model=EquipmentTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_equipment_type(
    data: EquipmentTypeCreate,
    current_user: User = Depends(require_permission("equipment.manage_referentials")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = EquipmentService(db, audit=audit, current_user=current_user)
    equipment_type = await service.create_equipment_type(data.model_dump(exclude_unset=True))
    if not equipment_type:
        raise HTTPException(status_code=400, detail="Erreur lors de la création du type d'équipement")
    return EquipmentTypeResponse.model_validate(equipment_type)


@router.patch("/types/{equipment_type_id}", response_model=EquipmentTypeResponse)
async def update_equipment_type(
    equipment_type_id: int,
    data: EquipmentTypeUpdate,
    current_user: User = Depends(require_permission("equipment.manage_referentials")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = EquipmentService(db, audit=audit, current_user=current_user)
    equipment_type = await service.update_equipment_type(equipment_type_id, data.model_dump(exclude_unset=True))
    if not equipment_type:
        raise HTTPException(status_code=404, detail="Type d'équipement non trouvé")
    return EquipmentTypeResponse.model_validate(equipment_type)


@router.delete("/types/{equipment_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment_type(
    equipment_type_id: int,
    current_user: User = Depends(require_permission("equipment.manage_referentials")),
    db: AsyncSession = Depends(get_db),
):
    service = EquipmentService(db, current_user=current_user)
    error = await service.delete_equipment_type(equipment_type_id)
    if error:
        raise HTTPException(status_code=400, detail=error)


# ============================================================
# EQUIPMENTS
# ============================================================

@router.get("", response_model=EquipmentListResponse)
async def list_equipments(
    page: int = 1,
    page_size: int = 20,
    search: str = None,
    equipment_type_id: int = None,
    status: str = None,
    room_id: int = None,
    is_active: bool = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    current_user: User = Depends(require_permission("equipment.view")),
    db: AsyncSession = Depends(get_db),
):
    service = EquipmentService(db, current_user=current_user)
    items, total = await service.search_equipments(
        page=page,
        page_size=page_size,
        search=search,
        equipment_type_id=equipment_type_id,
        status=status,
        room_id=room_id,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return EquipmentListResponse(
        items=[_build_equipment_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(
    equipment_id: int,
    current_user: User = Depends(require_permission("equipment.view")),
    db: AsyncSession = Depends(get_db),
):
    service = EquipmentService(db, current_user=current_user)
    equipment = await service.get_equipment(equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Équipement non trouvé")
    return _build_equipment_response(equipment)


@router.post("", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    data: EquipmentCreate,
    current_user: User = Depends(require_permission("equipment.create")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = EquipmentService(db, audit=audit, current_user=current_user)

    from app.models.buildings import Room
    room = await db.get(Room, data.room_id)
    if not room:
        raise HTTPException(status_code=422, detail="La pièce spécifiée n'existe pas")

    if data.equipment_type_id:
        eq_type = await service.get_equipment_type(data.equipment_type_id)
        if not eq_type:
            raise HTTPException(status_code=422, detail="Le type d'équipement spécifié n'existe pas")

    equipment = await service.create_equipment(data.model_dump(exclude_unset=True))
    if not equipment:
        raise HTTPException(status_code=400, detail="Erreur lors de la création de l'équipement")
    return _build_equipment_response(equipment)


@router.patch("/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    equipment_id: int,
    data: EquipmentUpdate,
    current_user: User = Depends(require_permission("equipment.update")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = EquipmentService(db, audit=audit, current_user=current_user)

    if data.room_id is not None:
        from app.models.buildings import Room
        room = await db.get(Room, data.room_id)
        if not room:
            raise HTTPException(status_code=422, detail="La pièce spécifiée n'existe pas")

    if data.equipment_type_id is not None:
        eq_type = await service.get_equipment_type(data.equipment_type_id)
        if not eq_type:
            raise HTTPException(status_code=422, detail="Le type d'équipement spécifié n'existe pas")

    equipment = await service.update_equipment(equipment_id, data.model_dump(exclude_unset=True))
    if not equipment:
        raise HTTPException(status_code=404, detail="Équipement non trouvé")
    return _build_equipment_response(equipment)


@router.patch("/{equipment_id}/deactivate", response_model=EquipmentResponse)
async def deactivate_equipment(
    equipment_id: int,
    current_user: User = Depends(require_permission("equipment.update")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = EquipmentService(db, audit=audit, current_user=current_user)
    equipment = await service.deactivate_equipment(equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Équipement non trouvé")
    return _build_equipment_response(equipment)


@router.delete("/{equipment_id}", response_model=MessageResponse)
async def delete_equipment(
    equipment_id: int,
    current_user: User = Depends(require_permission("equipment.delete")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = EquipmentService(db, audit=audit, current_user=current_user)
    success = await service.delete_equipment(equipment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Équipement non trouvé")
    return MessageResponse(message="Équipement supprimé")
