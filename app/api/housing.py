from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.housing import (
    HousingCreate,
    HousingListParams,
    HousingListResponse,
    HousingResponse,
    HousingUpdate,
    HousingDashboard,
    MessageResponse,
    OccupancyCreate,
    OccupancyListParams,
    OccupancyListResponse,
    OccupancyResponse,
    OccupancyUpdate,
    OccupantCreate,
    OccupantListParams,
    OccupantListResponse,
    OccupantResponse,
    OccupantUpdate,
    UnavailabilityCreate,
    UnavailabilityListParams,
    UnavailabilityListResponse,
    UnavailabilityResponse,
    UnavailabilityUpdate,
)
from app.services.housing import HousingService


router = APIRouter(
    prefix="/housing",
    tags=["housing"]
)


async def get_housing_service(
    current_user: User = Depends(require_permission("housing.view")),
    db: AsyncSession = Depends(get_db),
) -> HousingService:
    return HousingService(db, current_user=current_user)


# ============================================================
# DASHBOARD
# ============================================================

@router.get("/dashboard", response_model=HousingDashboard)
async def get_dashboard(
    service: HousingService = Depends(get_housing_service),
):
    return await service.get_dashboard()


# ============================================================
# HOUSINGS
# ============================================================

@router.get("/housings", response_model=HousingListResponse)
async def list_housings(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    site_id: Optional[int] = None,
    building_id: Optional[int] = None,
    housing_type: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    service: HousingService = Depends(get_housing_service),
):
    params = {k: v for k, v in {
        "page": page, "page_size": page_size, "search": search,
        "is_active": is_active, "site_id": site_id, "building_id": building_id,
        "housing_type": housing_type, "sort_by": sort_by, "sort_order": sort_order,
    }.items() if v is not None}
    return await service.list_housings(params)


@router.get("/housings/{housing_id}", response_model=HousingResponse)
async def get_housing(
    housing_id: int,
    service: HousingService = Depends(get_housing_service),
):
    item = await service.get_housing(housing_id)
    if not item:
        raise HTTPException(status_code=404, detail="Hébergement non trouvé")
    return item


@router.post("/housings", response_model=HousingResponse, status_code=201)
async def create_housing(
    data: HousingCreate,
    service: HousingService = Depends(require_permission("housing.manage")),
):
    return await service.create_housing(data.model_dump())


@router.patch("/housings/{housing_id}", response_model=HousingResponse)
async def update_housing(
    housing_id: int,
    data: HousingUpdate,
    service: HousingService = Depends(require_permission("housing.manage")),
):
    item = await service.update_housing(housing_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Hébergement non trouvé")
    return item


# ============================================================
# OCCUPANTS
# ============================================================

@router.get("/occupants", response_model=OccupantListResponse)
async def list_occupants(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = "last_name",
    sort_order: str = "asc",
    service: HousingService = Depends(get_housing_service),
):
    params = {k: v for k, v in {
        "page": page, "page_size": page_size, "search": search,
        "is_active": is_active, "sort_by": sort_by, "sort_order": sort_order,
    }.items() if v is not None}
    return await service.list_occupants(params)


@router.get("/occupants/{occupant_id}", response_model=OccupantResponse)
async def get_occupant(
    occupant_id: int,
    service: HousingService = Depends(get_housing_service),
):
    item = await service.get_occupant(occupant_id)
    if not item:
        raise HTTPException(status_code=404, detail="Occupant non trouvé")
    return item


@router.post("/occupants", response_model=OccupantResponse, status_code=201)
async def create_occupant(
    data: OccupantCreate,
    service: HousingService = Depends(require_permission("housing.manage_occupants")),
):
    return await service.create_occupant(data.model_dump())


@router.patch("/occupants/{occupant_id}", response_model=OccupantResponse)
async def update_occupant(
    occupant_id: int,
    data: OccupantUpdate,
    service: HousingService = Depends(require_permission("housing.manage_occupants")),
):
    item = await service.update_occupant(occupant_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Occupant non trouvé")
    return item


# ============================================================
# OCCUPANCIES
# ============================================================

@router.get("/occupancies", response_model=OccupancyListResponse)
async def list_occupancies(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    housing_id: Optional[int] = None,
    occupant_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = "arrival_date",
    sort_order: str = "desc",
    service: HousingService = Depends(get_housing_service),
):
    params = {k: v for k, v in {
        "page": page, "page_size": page_size, "status": status,
        "housing_id": housing_id, "occupant_id": occupant_id,
        "date_from": date_from, "date_to": date_to,
        "sort_by": sort_by, "sort_order": sort_order,
    }.items() if v is not None}
    return await service.list_occupancies(params)


@router.get("/occupancies/{occupancy_id}", response_model=OccupancyResponse)
async def get_occupancy(
    occupancy_id: int,
    service: HousingService = Depends(get_housing_service),
):
    item = await service.get_occupancy(occupancy_id)
    if not item:
        raise HTTPException(status_code=404, detail="Occupation non trouvée")
    return item


@router.post("/occupancies", response_model=OccupancyResponse, status_code=201)
async def create_occupancy(
    data: OccupancyCreate,
    service: HousingService = Depends(require_permission("housing.manage_occupancies")),
):
    return await service.create_occupancy(data.model_dump())


@router.patch("/occupancies/{occupancy_id}", response_model=OccupancyResponse)
async def update_occupancy(
    occupancy_id: int,
    data: OccupancyUpdate,
    service: HousingService = Depends(require_permission("housing.manage_occupancies")),
):
    item = await service.update_occupancy(occupancy_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Occupation non trouvée")
    return item


@router.post("/occupancies/{occupancy_id}/status", response_model=OccupancyResponse)
async def change_occupancy_status(
    occupancy_id: int,
    data: dict,
    service: HousingService = Depends(require_permission("housing.manage_occupancies")),
):
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Statut requis")
    item = await service.change_occupancy_status(occupancy_id, new_status)
    if not item:
        raise HTTPException(status_code=404, detail="Occupation non trouvée")
    return item


# ============================================================
# UNAVAILABILITIES
# ============================================================

@router.get("/unavailabilities", response_model=UnavailabilityListResponse)
async def list_unavailabilities(
    page: int = 1,
    page_size: int = 20,
    housing_id: Optional[int] = None,
    reason: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = "start_date",
    sort_order: str = "desc",
    service: HousingService = Depends(get_housing_service),
):
    params = {k: v for k, v in {
        "page": page, "page_size": page_size, "housing_id": housing_id,
        "reason": reason, "date_from": date_from, "date_to": date_to,
        "sort_by": sort_by, "sort_order": sort_order,
    }.items() if v is not None}
    return await service.list_unavailabilities(params)


@router.post("/unavailabilities", response_model=UnavailabilityResponse, status_code=201)
async def create_unavailability(
    data: UnavailabilityCreate,
    service: HousingService = Depends(require_permission("housing.manage_unavailabilities")),
):
    return await service.create_unavailability(data.model_dump())


@router.delete("/unavailabilities/{unavailability_id}", response_model=MessageResponse)
async def delete_unavailability(
    unavailability_id: int,
    service: HousingService = Depends(require_permission("housing.manage_unavailabilities")),
):
    ok = await service.delete_unavailability(unavailability_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Indisponibilité non trouvée")
    return {"message": "Indisponibilité supprimée"}


# ============================================================
# PLANNING
# ============================================================

@router.get("/planning")
async def get_planning(
    start_date: date,
    end_date: date,
    service: HousingService = Depends(get_housing_service),
):
    return await service.get_planning(start_date, end_date)
