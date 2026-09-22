from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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
    CleaningCreate,
    CleaningListParams,
    CleaningListResponse,
    CleaningResponse,
    CleaningUpdate,
    EmailTemplateCreate,
    EmailTemplateListParams,
    EmailTemplateListResponse,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    EmailTemplateAttachmentResponse,
    EmailLogListParams,
    EmailLogListResponse,
    EmailLogResponse,
    OccupantQuickCreate,
    PlanningEntry,
    PlanningResponse,
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


async def get_housing_manage_service(
    current_user: User = Depends(require_permission("housing.manage")),
    db: AsyncSession = Depends(get_db),
) -> HousingService:
    return HousingService(db, current_user=current_user)


async def get_occupant_manage_service(
    current_user: User = Depends(require_permission("housing.manage_occupants")),
    db: AsyncSession = Depends(get_db),
) -> HousingService:
    return HousingService(db, current_user=current_user)


async def get_occupancy_manage_service(
    current_user: User = Depends(require_permission("housing.manage_occupancies")),
    db: AsyncSession = Depends(get_db),
) -> HousingService:
    return HousingService(db, current_user=current_user)


async def get_unavailability_manage_service(
    current_user: User = Depends(require_permission("housing.manage_unavailabilities")),
    db: AsyncSession = Depends(get_db),
) -> HousingService:
    return HousingService(db, current_user=current_user)


async def get_cleaning_manage_service(
    current_user: User = Depends(require_permission("housing.manage_cleaning")),
    db: AsyncSession = Depends(get_db),
) -> HousingService:
    return HousingService(db, current_user=current_user)


async def get_email_template_manage_service(
    current_user: User = Depends(require_permission("housing.manage_email_templates")),
    db: AsyncSession = Depends(get_db),
) -> HousingService:
    return HousingService(db, current_user=current_user)


async def get_email_send_service(
    current_user: User = Depends(require_permission("housing.send_emails")),
    db: AsyncSession = Depends(get_db),
) -> HousingService:
    return HousingService(db, current_user=current_user)


async def get_planning_manage_service(
    current_user: User = Depends(require_permission("housing.manage_planning")),
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
    service: HousingService = Depends(get_housing_service),
):
    return await service.create_housing(data.model_dump())


@router.patch("/housings/{housing_id}", response_model=HousingResponse)
async def update_housing(
    housing_id: int,
    data: HousingUpdate,
    service: HousingService = Depends(get_housing_service),
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
    service: HousingService = Depends(get_occupant_manage_service),
):
    return await service.create_occupant(data.model_dump())


@router.patch("/occupants/{occupant_id}", response_model=OccupantResponse)
async def update_occupant(
    occupant_id: int,
    data: OccupantUpdate,
    service: HousingService = Depends(get_occupant_manage_service),
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
    service: HousingService = Depends(get_occupancy_manage_service),
):
    return await service.create_occupancy(data.model_dump())


@router.patch("/occupancies/{occupancy_id}", response_model=OccupancyResponse)
async def update_occupancy(
    occupancy_id: int,
    data: OccupancyUpdate,
    service: HousingService = Depends(get_occupancy_manage_service),
):
    item = await service.update_occupancy(occupancy_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Occupation non trouvée")
    return item


@router.delete("/occupancies/{occupancy_id}", response_model=MessageResponse)
async def delete_occupancy(
    occupancy_id: int,
    service: HousingService = Depends(get_occupancy_manage_service),
):
    deleted = await service.delete_occupancy(occupancy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Occupation non trouvée")
    return MessageResponse(message="Réservation supprimée")


@router.post("/occupancies/{occupancy_id}/status", response_model=OccupancyResponse)
async def change_occupancy_status(
    occupancy_id: int,
    data: dict,
    service: HousingService = Depends(get_occupancy_manage_service),
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
    service: HousingService = Depends(get_unavailability_manage_service),
):
    return await service.create_unavailability(data.model_dump())


@router.delete("/unavailabilities/{unavailability_id}", response_model=MessageResponse)
async def delete_unavailability(
    unavailability_id: int,
    service: HousingService = Depends(get_unavailability_manage_service),
):
    ok = await service.delete_unavailability(unavailability_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Indisponibilité non trouvée")
    return {"message": "Indisponibilité supprimée"}


# ============================================================
# QUICK OCCUPANT CREATION
# ============================================================

@router.post("/occupants/quick-create", response_model=OccupantResponse, status_code=201)
async def quick_create_occupant(
    data: OccupantQuickCreate,
    service: HousingService = Depends(get_occupant_manage_service),
):
    return await service.create_occupant(data.model_dump())


# ============================================================
# CLEANING
# ============================================================

@router.get("/cleanings", response_model=CleaningListResponse)
async def list_cleanings(
    page: int = 1,
    page_size: int = 20,
    housing_id: Optional[int] = None,
    occupancy_id: Optional[int] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    assigned_to: Optional[int] = None,
    sort_by: str = "scheduled_date",
    sort_order: str = "asc",
    service: HousingService = Depends(get_housing_service),
):
    params = {k: v for k, v in {
        "page": page, "page_size": page_size, "housing_id": housing_id,
        "occupancy_id": occupancy_id, "type": type, "status": status,
        "date_from": date_from, "date_to": date_to, "assigned_to": assigned_to,
        "sort_by": sort_by, "sort_order": sort_order,
    }.items() if v is not None}
    return await service.list_cleanings(params)


@router.get("/cleanings/{cleaning_id}", response_model=CleaningResponse)
async def get_cleaning(
    cleaning_id: int,
    service: HousingService = Depends(get_housing_service),
):
    item = await service.get_cleaning(cleaning_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ménage non trouvé")
    return item


@router.post("/cleanings", response_model=CleaningResponse, status_code=201)
async def create_cleaning(
    data: CleaningCreate,
    service: HousingService = Depends(get_cleaning_manage_service),
):
    return await service.create_cleaning(data.model_dump())


@router.patch("/cleanings/{cleaning_id}", response_model=CleaningResponse)
async def update_cleaning(
    cleaning_id: int,
    data: CleaningUpdate,
    service: HousingService = Depends(get_cleaning_manage_service),
):
    item = await service.update_cleaning(cleaning_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Ménage non trouvé")
    return item


@router.delete("/cleanings/{cleaning_id}", response_model=MessageResponse)
async def delete_cleaning(
    cleaning_id: int,
    service: HousingService = Depends(get_cleaning_manage_service),
):
    ok = await service.delete_cleaning(cleaning_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Ménage non trouvé")
    return {"message": "Ménage supprimé"}


# ============================================================
# EMAIL TEMPLATES
# ============================================================

@router.get("/email-templates", response_model=EmailTemplateListResponse)
async def list_email_templates(
    page: int = 1,
    page_size: int = 20,
    template_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    service: HousingService = Depends(get_housing_service),
):
    params = {k: v for k, v in {
        "page": page, "page_size": page_size, "template_type": template_type,
        "is_active": is_active, "sort_by": sort_by, "sort_order": sort_order,
    }.items() if v is not None}
    return await service.list_email_templates(params)


@router.get("/email-templates/{template_id}", response_model=EmailTemplateResponse)
async def get_email_template(
    template_id: int,
    service: HousingService = Depends(get_housing_service),
):
    item = await service.get_email_template(template_id)
    if not item:
        raise HTTPException(status_code=404, detail="Modèle email non trouvé")
    return item


@router.post("/email-templates", response_model=EmailTemplateResponse, status_code=201)
async def create_email_template(
    data: EmailTemplateCreate,
    service: HousingService = Depends(get_email_template_manage_service),
):
    return await service.create_email_template(data.model_dump())


@router.patch("/email-templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: int,
    data: EmailTemplateUpdate,
    service: HousingService = Depends(get_email_template_manage_service),
):
    item = await service.update_email_template(template_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Modèle email non trouvé")
    return item


@router.post("/email-templates/{template_id}/attachments", response_model=EmailTemplateAttachmentResponse, status_code=201)
async def upload_email_template_attachment(
    template_id: int,
    file: UploadFile = File(...),
    housing_ids: str = Form("[]"),
    service: HousingService = Depends(get_email_template_manage_service),
):
    import json
    return await service.upload_email_template_attachment(template_id, file, json.loads(housing_ids) if housing_ids else [])


@router.put("/email-templates/{template_id}/attachments/{attachment_id}", response_model=EmailTemplateAttachmentResponse)
async def update_email_template_attachment_housings(
    template_id: int,
    attachment_id: int,
    housing_ids: List[int],
    service: HousingService = Depends(get_email_template_manage_service),
):
    attachment = await service.update_email_template_attachment_housings(attachment_id, housing_ids)
    if not attachment:
        raise HTTPException(status_code=404, detail="Pièce jointe non trouvée")
    return attachment


@router.delete("/email-templates/{template_id}/attachments/{attachment_id}", response_model=MessageResponse)
async def delete_email_template_attachment(
    template_id: int,
    attachment_id: int,
    service: HousingService = Depends(get_email_template_manage_service),
):
    ok = await service.delete_email_template_attachment(attachment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Pièce jointe non trouvée")
    return {"message": "Pièce jointe supprimée"}


# ============================================================
# EMAIL SENDING
# ============================================================

@router.post("/occupancies/{occupancy_id}/send-confirmation", response_model=MessageResponse)
async def send_confirmation_email(
    occupancy_id: int,
    template_id: int = Form(...),
    recipient_ids: str = Form(...),  # JSON array of occupant IDs
    send_to_all: bool = Form(True),
    service: HousingService = Depends(get_email_send_service),
):
    import json
    recipients = json.loads(recipient_ids) if recipient_ids else []
    result = await service.send_confirmation_email(occupancy_id, template_id, recipients, send_to_all)
    return {"message": result}


@router.post("/occupancies/{occupancy_id}/send-message", response_model=MessageResponse)
async def send_custom_message(
    occupancy_id: int,
    subject: str = Form(...),
    body_text: str = Form(...),
    recipient_ids: str = Form(...),
    template_id: Optional[int] = Form(None),
    attachment_ids: str = Form("[]"),
    service: HousingService = Depends(get_email_send_service),
):
    import json
    recipients = json.loads(recipient_ids) if recipient_ids else []
    attachments = json.loads(attachment_ids) if attachment_ids else []
    result = await service.send_custom_message(occupancy_id, subject, body_text, recipients, template_id, attachments)
    return {"message": result}


@router.get("/email-logs", response_model=EmailLogListResponse)
async def list_email_logs(
    page: int = 1,
    page_size: int = 20,
    template_id: Optional[int] = None,
    occupancy_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    service: HousingService = Depends(get_housing_service),
):
    params = {k: v for k, v in {
        "page": page, "page_size": page_size, "template_id": template_id,
        "occupancy_id": occupancy_id, "status": status,
        "date_from": date_from, "date_to": date_to,
        "sort_by": sort_by, "sort_order": sort_order,
    }.items() if v is not None}
    return await service.list_email_logs(params)


# ============================================================
# ENHANCED PLANNING
# ============================================================

@router.get("/planning", response_model=PlanningResponse)
async def get_planning(
    start_date: date,
    end_date: date,
    view: str = "month",  # day, week, month
    housing_ids: Optional[str] = None,  # JSON array
    status_filter: Optional[str] = None,
    service: HousingService = Depends(get_planning_manage_service),
):
    import json
    housing_id_list = json.loads(housing_ids) if housing_ids else None
    return await service.get_planning(start_date, end_date, view, housing_id_list, status_filter)


# ============================================================
# OCCUPANCY WITH MULTIPLE OCCUPANTS
# ============================================================

@router.post("/occupancies", response_model=OccupancyResponse, status_code=201)
async def create_occupancy(
    data: OccupancyCreate,
    service: HousingService = Depends(get_occupancy_manage_service),
):
    return await service.create_occupancy(data.model_dump())


@router.patch("/occupancies/{occupancy_id}", response_model=OccupancyResponse)
async def update_occupancy(
    occupancy_id: int,
    data: OccupancyUpdate,
    service: HousingService = Depends(get_occupancy_manage_service),
):
    item = await service.update_occupancy(occupancy_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Occupation non trouvée")
    return item
