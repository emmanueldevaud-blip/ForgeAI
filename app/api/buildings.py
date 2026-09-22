import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.buildings import (
    BuildingCreate,
    BuildingListParams,
    BuildingListResponse,
    BuildingResponse,
    BuildingUpdate,
    BuildingWithRoomsResponse,
    MessageResponse,
    RoomCreate,
    RoomListParams,
    RoomListResponse,
    RoomResponse,
    RoomUpdate,
    RoomTypeCreate,
    RoomTypeListParams,
    RoomTypeListResponse,
    RoomTypeResponse,
    RoomTypeUpdate,
    SiteCreate,
    SiteListParams,
    SiteListResponse,
    SiteResponse,
    SiteUpdate,
    SiteWithBuildingsResponse,
    UsageTypeCreate,
    UsageTypeListParams,
    UsageTypeListResponse,
    UsageTypeResponse,
    UsageTypeUpdate,
)
from app.services.audit import get_audit_service
from app.services.buildings import BuildingService


router = APIRouter(
    prefix="/buildings",
    tags=["buildings"],
)


async def get_building_service(
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
) -> BuildingService:
    audit = await get_audit_service(db)
    return BuildingService(db, audit=audit, current_user=current_user)


# ============================================================
# USAGE TYPES
# ============================================================

@router.get("/usage-types", response_model=UsageTypeListResponse)
async def list_usage_types(
    params: UsageTypeListParams = Depends(),
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    items, total = await service.search_usage_types(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        is_active=params.is_active,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    return UsageTypeListResponse(
        items=[UsageTypeResponse.model_validate(i) for i in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=math.ceil(total / params.page_size) if total > 0 else 1,
    )


@router.get("/usage-types/{usage_type_id}", response_model=UsageTypeResponse)
async def get_usage_type(
    usage_type_id: int,
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    item = await service.get_usage_type(usage_type_id)
    if not item:
        raise HTTPException(status_code=404, detail="Type d'utilisation non trouvé")

    return UsageTypeResponse.model_validate(item)


@router.post("/usage-types", response_model=UsageTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_usage_type(
    data: UsageTypeCreate,
    current_user: User = Depends(require_permission("building.manage_refs")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    item = await service.create_usage_type(data.model_dump())
    return UsageTypeResponse.model_validate(item)


@router.patch("/usage-types/{usage_type_id}", response_model=UsageTypeResponse)
async def update_usage_type(
    usage_type_id: int,
    data: UsageTypeUpdate,
    current_user: User = Depends(require_permission("building.manage_refs")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    item = await service.update_usage_type(usage_type_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Type d'utilisation non trouvé")

    return UsageTypeResponse.model_validate(item)


@router.delete("/usage-types/{usage_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_usage_type(
    usage_type_id: int,
    current_user: User = Depends(require_permission("building.manage_refs")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    error = await service.delete_usage_type(usage_type_id)
    if error == "Type d'utilisation non trouvé":
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)


# ============================================================
# ROOM TYPES
# ============================================================

@router.get("/room-types", response_model=RoomTypeListResponse)
async def list_room_types(
    params: RoomTypeListParams = Depends(),
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    items, total = await service.search_room_types(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        is_active=params.is_active,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    return RoomTypeListResponse(
        items=[RoomTypeResponse.model_validate(i) for i in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=math.ceil(total / params.page_size) if total > 0 else 1,
    )


@router.get("/room-types/{room_type_id}", response_model=RoomTypeResponse)
async def get_room_type(
    room_type_id: int,
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    item = await service.get_room_type(room_type_id)
    if not item:
        raise HTTPException(status_code=404, detail="Type de pièce non trouvé")

    return RoomTypeResponse.model_validate(item)


@router.post("/room-types", response_model=RoomTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_room_type(
    data: RoomTypeCreate,
    current_user: User = Depends(require_permission("building.manage_refs")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    item = await service.create_room_type(data.model_dump())
    return RoomTypeResponse.model_validate(item)


@router.patch("/room-types/{room_type_id}", response_model=RoomTypeResponse)
async def update_room_type(
    room_type_id: int,
    data: RoomTypeUpdate,
    current_user: User = Depends(require_permission("building.manage_refs")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    item = await service.update_room_type(room_type_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Type de pièce non trouvé")

    return RoomTypeResponse.model_validate(item)


@router.delete("/room-types/{room_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room_type(
    room_type_id: int,
    current_user: User = Depends(require_permission("building.manage_refs")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    error = await service.delete_room_type(room_type_id)
    if error == "Type de pièce non trouvé":
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)


# ============================================================
# SITES
# ============================================================

@router.get("/sites", response_model=SiteListResponse)
async def list_sites(
    params: SiteListParams = Depends(),
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    items, total = await service.search_sites(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        is_active=params.is_active,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    site_responses = []
    for site in items:
        resp = SiteResponse.model_validate(site)
        resp.building_count = len(site.buildings) if site.buildings else 0
        site_responses.append(resp)

    return SiteListResponse(
        items=site_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=math.ceil(total / params.page_size) if total > 0 else 1,
    )


@router.get("/sites/{site_id}", response_model=SiteWithBuildingsResponse)
async def get_site(
    site_id: int,
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    site = await service.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site non trouvé")

    resp = SiteWithBuildingsResponse.model_validate(site)
    resp.building_count = len(site.buildings) if site.buildings else 0
    return resp


@router.post("/sites", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(
    data: SiteCreate,
    current_user: User = Depends(require_permission("building.create")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    site = await service.create_site(data.model_dump())
    if not site:
        raise HTTPException(status_code=409, detail="Une référence existe déjà")
    return SiteResponse.model_validate(site)


@router.patch("/sites/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: int,
    data: SiteUpdate,
    current_user: User = Depends(require_permission("building.update")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    site = await service.update_site(site_id, data.model_dump(exclude_unset=True))
    if not site:
        raise HTTPException(status_code=404, detail="Site non trouvé")

    return SiteResponse.model_validate(site)


# ============================================================
# ROOMS (must be before /{building_id})
# ============================================================

@router.get("/rooms", response_model=RoomListResponse)
async def list_rooms(
    params: RoomListParams = Depends(),
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    items, total = await service.search_rooms(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        building_id=params.building_id,
        room_type_id=params.room_type_id,
        usage_type_id=params.usage_type_id,
        is_active=params.is_active,
        used_for_accommodation=params.used_for_accommodation,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    return RoomListResponse(
        items=[RoomResponse.model_validate(i) for i in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=math.ceil(total / params.page_size) if total > 0 else 1,
    )


@router.get("/rooms/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: int,
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    room = await service.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Local non trouvé")

    return RoomResponse.model_validate(room)


@router.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    data: RoomCreate,
    current_user: User = Depends(require_permission("building.create")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    room = await service.create_room(data.model_dump())
    if not room:
        raise HTTPException(status_code=409, detail="Une référence existe déjà")
    return RoomResponse.model_validate(room)


@router.patch("/rooms/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: int,
    data: RoomUpdate,
    current_user: User = Depends(require_permission("building.update")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    room = await service.update_room(room_id, data.model_dump(exclude_unset=True))
    if not room:
        raise HTTPException(status_code=404, detail="Local non trouvé")

    return RoomResponse.model_validate(room)


# ============================================================
# BUILDINGS (/{building_id} must be last)
# ============================================================

@router.get("", response_model=BuildingListResponse)
async def list_buildings(
    params: BuildingListParams = Depends(),
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    items, total = await service.search_buildings(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        site_id=params.site_id,
        is_active=params.is_active,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    building_responses = []
    for b in items:
        resp = BuildingResponse.model_validate(b)
        resp.room_count = len(b.rooms) if b.rooms else 0
        building_responses.append(resp)

    return BuildingListResponse(
        items=building_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=math.ceil(total / params.page_size) if total > 0 else 1,
    )


@router.get("/{building_id}", response_model=BuildingWithRoomsResponse)
async def get_building(
    building_id: int,
    current_user: User = Depends(require_permission("building.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    building = await service.get_building(building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Bâtiment non trouvé")

    resp = BuildingWithRoomsResponse.model_validate(building)
    resp.room_count = len(building.rooms) if building.rooms else 0
    return resp


@router.post("", response_model=BuildingResponse, status_code=status.HTTP_201_CREATED)
async def create_building(
    data: BuildingCreate,
    current_user: User = Depends(require_permission("building.create")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    building = await service.create_building(data.model_dump())
    if not building:
        raise HTTPException(status_code=409, detail="Une référence existe déjà")
    return BuildingResponse.model_validate(building)


@router.patch("/{building_id}", response_model=BuildingResponse)
async def update_building(
    building_id: int,
    data: BuildingUpdate,
    current_user: User = Depends(require_permission("building.update")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    building = await service.update_building(building_id, data.model_dump(exclude_unset=True))
    if not building:
        raise HTTPException(status_code=404, detail="Bâtiment non trouvé")

    return BuildingResponse.model_validate(building)


@router.delete("/sites/{site_id}", response_model=MessageResponse)
async def delete_site(
    site_id: int,
    current_user: User = Depends(require_permission("building.delete")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    error = await service.delete_site(site_id)
    if error == "Site non trouvé":
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)

    return MessageResponse(message="Site supprimé")


@router.delete("/rooms/{room_id}", response_model=MessageResponse)
async def delete_room(
    room_id: int,
    current_user: User = Depends(require_permission("building.delete")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    error = await service.delete_room(room_id)
    if error == "Local non trouvé":
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)

    return MessageResponse(message="Local supprimé")


@router.delete("/{building_id}", response_model=MessageResponse)
async def delete_building(
    building_id: int,
    current_user: User = Depends(require_permission("building.delete")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = BuildingService(db, audit=audit, current_user=current_user)

    error = await service.delete_building(building_id)
    if error == "Bâtiment non trouvé":
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)

    return MessageResponse(message="Bâtiment supprimé")
