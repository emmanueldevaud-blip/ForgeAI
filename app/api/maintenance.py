from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.maintenance import (
    AIChatRequest,
    AIChatResponse,
    ContractCreate,
    ContractListParams,
    ContractListResponse,
    ContractResponse,
    ContractUpdate,
    CostCreate,
    CostResponse,
    IntervenantCreate,
    IntervenantResponse,
    IntervenantUpdate,
    InterventionCreate,
    InterventionResponse,
    MaintenanceDashboard,
    MessageResponse,
    PartCreate,
    PartListParams,
    PartListResponse,
    PartResponse,
    PartUpdate,
    PlanCreate,
    PlanListParams,
    PlanListResponse,
    PlanResponse,
    PlanUpdate,
    ProviderCreate,
    ProviderListParams,
    ProviderListResponse,
    ProviderResponse,
    ProviderUpdate,
    RequestCreate,
    RequestListParams,
    RequestListResponse,
    RequestResponse,
    RequestUpdate,
    StatusChange,
    WorkOrderCreate,
    WorkOrderListParams,
    WorkOrderListResponse,
    WorkOrderPartCreate,
    WorkOrderPartResponse,
    WorkOrderResponse,
    WorkOrderUpdate,
)
from app.services.audit import get_audit_service
from app.services.maintenance import MaintenanceService


router = APIRouter(
    prefix="/maintenance",
    tags=["maintenance"]
)


async def get_maintenance_service(
    current_user: User = Depends(require_permission("maintenance.view")),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceService:
    audit = await get_audit_service(db)
    return MaintenanceService(db, audit=audit, current_user=current_user)


# ============================================================
# DASHBOARD
# ============================================================

@router.get("/dashboard", response_model=MaintenanceDashboard)
async def get_dashboard(
    service: MaintenanceService = Depends(get_maintenance_service),
):
    data = await service.get_dashboard()
    return MaintenanceDashboard(**data)


# ============================================================
# PROVIDERS
# ============================================================

@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(
    params: ProviderListParams = Depends(),
    current_user: User = Depends(require_permission("maintenance.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    items, total = await service.search_providers(
        page=params.page, page_size=params.page_size,
        search=params.search, is_active=params.is_active,
        sort_by=params.sort_by, sort_order=params.sort_order,
    )
    return ProviderListResponse(
        items=[ProviderResponse.model_validate(i, from_attributes=True) for i in items],
        total=total, page=params.page, page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.get("/providers/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: int,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.get_provider(provider_id)
    if not item:
        raise HTTPException(status_code=404, detail="Prestataire non trouvé")
    return ProviderResponse.model_validate(item, from_attributes=True)


@router.post("/providers", response_model=ProviderResponse, status_code=201)
async def create_provider(
    data: ProviderCreate,
    current_user: User = Depends(require_permission("maintenance.manage_providers")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    item = await service.create_provider(data.model_dump())
    return ProviderResponse.model_validate(item, from_attributes=True)


@router.patch("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: int,
    data: ProviderUpdate,
    current_user: User = Depends(require_permission("maintenance.manage_providers")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    item = await service.update_provider(provider_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Prestataire non trouvé")
    return ProviderResponse.model_validate(item, from_attributes=True)


# ============================================================
# PARTS
# ============================================================

@router.get("/parts", response_model=PartListResponse)
async def list_parts(
    params: PartListParams = Depends(),
    current_user: User = Depends(require_permission("maintenance.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    items, total = await service.search_parts(
        page=params.page, page_size=params.page_size,
        search=params.search, is_active=params.is_active,
        sort_by=params.sort_by, sort_order=params.sort_order,
    )
    return PartListResponse(
        items=[PartResponse.model_validate(i, from_attributes=True) for i in items],
        total=total, page=params.page, page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.get("/parts/{part_id}", response_model=PartResponse)
async def get_part(
    part_id: int,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.get_part(part_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    return PartResponse.model_validate(item, from_attributes=True)


@router.post("/parts", response_model=PartResponse, status_code=201)
async def create_part(
    data: PartCreate,
    current_user: User = Depends(require_permission("maintenance.manage_referentials")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    item = await service.create_part(data.model_dump())
    return PartResponse.model_validate(item, from_attributes=True)


@router.patch("/parts/{part_id}", response_model=PartResponse)
async def update_part(
    part_id: int,
    data: PartUpdate,
    current_user: User = Depends(require_permission("maintenance.manage_referentials")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    item = await service.update_part(part_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    return PartResponse.model_validate(item, from_attributes=True)


# ============================================================
# CONTRACTS
# ============================================================

@router.get("/contracts", response_model=ContractListResponse)
async def list_contracts(
    params: ContractListParams = Depends(),
    current_user: User = Depends(require_permission("maintenance.view")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    items, total = await service.search_contracts(
        page=params.page, page_size=params.page_size,
        search=params.search, provider_id=params.provider_id,
        is_active=params.is_active,
        sort_by=params.sort_by, sort_order=params.sort_order,
    )
    responses = []
    for item in items:
        r = ContractResponse.model_validate(item, from_attributes=True)
        r.equipment_count = len(item.equipment_links)
        if item.provider:
            r.provider = ProviderResponse.model_validate(item.provider, from_attributes=True)
        responses.append(r)
    return ContractListResponse(
        items=responses, total=total, page=params.page, page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.get("/contracts/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: int,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.get_contract(contract_id)
    if not item:
        raise HTTPException(status_code=404, detail="Contrat non trouvé")
    r = ContractResponse.model_validate(item, from_attributes=True)
    r.equipment_count = len(item.equipment_links)
    if item.provider:
        r.provider = ProviderResponse.model_validate(item.provider, from_attributes=True)
    return r


@router.post("/contracts", response_model=ContractResponse, status_code=201)
async def create_contract(
    data: ContractCreate,
    current_user: User = Depends(require_permission("maintenance.manage_contracts")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    item = await service.create_contract(data.model_dump())
    return ContractResponse.model_validate(item, from_attributes=True)


@router.patch("/contracts/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: int,
    data: ContractUpdate,
    current_user: User = Depends(require_permission("maintenance.manage_contracts")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    item = await service.update_contract(contract_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Contrat non trouvé")
    return ContractResponse.model_validate(item, from_attributes=True)


# ============================================================
# REQUESTS
# ============================================================

@router.get("/requests", response_model=RequestListResponse)
async def list_requests(
    params: RequestListParams = Depends(),
    service: MaintenanceService = Depends(get_maintenance_service),
):
    items, total = await service.search_requests(
        page=params.page, page_size=params.page_size,
        search=params.search, status=params.status,
        priority=params.priority, equipment_id=params.equipment_id,
        requested_by=params.requested_by,
        sort_by=params.sort_by, sort_order=params.sort_order,
    )
    responses = []
    for item in items:
        r = RequestResponse.model_validate(item, from_attributes=True)
        if item.equipment_id:
            eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
            if eq_summary:
                r.equipment_summary = eq_summary
        if item.requested_by:
            user_summary = await _get_user_summary(service.db, item.requested_by)
            if user_summary:
                r.requested_by_summary = user_summary
        responses.append(r)
    return RequestListResponse(
        items=responses, total=total, page=params.page, page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.get("/requests/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: int,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.get_request(request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    r = RequestResponse.model_validate(item, from_attributes=True)
    if item.equipment_id:
        eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
        if eq_summary:
            r.equipment_summary = eq_summary
    if item.requested_by:
        user_summary = await _get_user_summary(service.db, item.requested_by)
        if user_summary:
            r.requested_by_summary = user_summary
    return r


@router.post("/requests", response_model=RequestResponse, status_code=201)
async def create_request(
    data: RequestCreate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.create_request(data.model_dump())
    r = RequestResponse.model_validate(item, from_attributes=True)
    if item.equipment_id:
        eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
        if eq_summary:
            r.equipment_summary = eq_summary
    return r


@router.patch("/requests/{request_id}", response_model=RequestResponse)
async def update_request(
    request_id: int,
    data: RequestUpdate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    try:
        item = await service.update_request(request_id, data.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    r = RequestResponse.model_validate(item, from_attributes=True)
    if item.equipment_id:
        eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
        if eq_summary:
            r.equipment_summary = eq_summary
    if item.requested_by:
        user_summary = await _get_user_summary(service.db, item.requested_by)
        if user_summary:
            r.requested_by_summary = user_summary
    return r


# ============================================================
# WORK ORDERS
# ============================================================

@router.get("/work-orders", response_model=WorkOrderListResponse)
async def list_work_orders(
    params: WorkOrderListParams = Depends(),
    service: MaintenanceService = Depends(get_maintenance_service),
):
    items, total = await service.search_work_orders(
        page=params.page, page_size=params.page_size,
        search=params.search, status=params.status,
        priority=params.priority, maintenance_type=params.maintenance_type,
        equipment_id=params.equipment_id, responsible_id=params.responsible_id,
        sort_by=params.sort_by, sort_order=params.sort_order,
    )
    responses = []
    for item in items:
        r = WorkOrderResponse.model_validate(item, from_attributes=True)
        if item.equipment_id:
            eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
            if eq_summary:
                r.equipment_summary = eq_summary
        if item.responsible_id:
            user_summary = await _get_user_summary(service.db, item.responsible_id)
            if user_summary:
                r.responsible_summary = user_summary
        responses.append(r)
    return WorkOrderListResponse(
        items=responses, total=total, page=params.page, page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.get("/work-orders/{wo_id}", response_model=WorkOrderResponse)
async def get_work_order(
    wo_id: int,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.get_work_order(wo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ordre de travail non trouvé")
    r = WorkOrderResponse.model_validate(item, from_attributes=True)
    if item.equipment_id:
        eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
        if eq_summary:
            r.equipment_summary = eq_summary
    if item.responsible_id:
        user_summary = await _get_user_summary(service.db, item.responsible_id)
        if user_summary:
            r.responsible_summary = user_summary
    return r


@router.post("/work-orders", response_model=WorkOrderResponse, status_code=201)
async def create_work_order(
    data: WorkOrderCreate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.create_work_order(data.model_dump())
    r = WorkOrderResponse.model_validate(item, from_attributes=True)
    if item.equipment_id:
        eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
        if eq_summary:
            r.equipment_summary = eq_summary
    return r


@router.patch("/work-orders/{wo_id}", response_model=WorkOrderResponse)
async def update_work_order(
    wo_id: int,
    data: WorkOrderUpdate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    try:
        item = await service.update_work_order(wo_id, data.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail="Ordre de travail non trouvé")
    r = WorkOrderResponse.model_validate(item, from_attributes=True)
    if item.equipment_id:
        eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
        if eq_summary:
            r.equipment_summary = eq_summary
    if item.responsible_id:
        user_summary = await _get_user_summary(service.db, item.responsible_id)
        if user_summary:
            r.responsible_summary = user_summary
    return r


@router.post("/requests/{request_id}/create-work-order", response_model=WorkOrderResponse, status_code=201)
async def create_work_order_from_request(
    request_id: int,
    data: WorkOrderCreate | None = None,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    extra = data.model_dump(exclude_unset=True) if data else None
    item = await service.create_work_order_from_request(request_id, extra)
    if not item:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    r = WorkOrderResponse.model_validate(item, from_attributes=True)
    if item.equipment_id:
        eq_summary = await _get_equipment_summary(service.db, item.equipment_id)
        if eq_summary:
            r.equipment_summary = eq_summary
    return r


# ============================================================
# INTERVENANTS
# ============================================================

@router.post("/work-orders/{wo_id}/intervenants", response_model=IntervenantResponse, status_code=201)
async def add_intervenant(
    wo_id: int,
    data: IntervenantCreate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.add_intervenant(wo_id, data.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Ordre de travail non trouvé")
    r = IntervenantResponse.model_validate(item, from_attributes=True)
    if item.user_id:
        user_summary = await _get_user_summary(service.db, item.user_id)
        if user_summary:
            r.user_summary = user_summary
    return r


@router.patch("/intervenants/{intervenant_id}", response_model=IntervenantResponse)
async def update_intervenant(
    intervenant_id: int,
    data: IntervenantUpdate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.update_intervenant(intervenant_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Intervenant non trouvé")
    return IntervenantResponse.model_validate(item, from_attributes=True)


@router.delete("/intervenants/{intervenant_id}", response_model=MessageResponse)
async def remove_intervenant(
    intervenant_id: int,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    removed = await service.remove_intervenant(intervenant_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Intervenant non trouvé")
    return MessageResponse(message="Intervenant retiré")


# ============================================================
# INTERVENTIONS
# ============================================================

@router.post("/work-orders/{wo_id}/interventions", response_model=InterventionResponse, status_code=201)
async def add_intervention(
    wo_id: int,
    data: InterventionCreate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.add_intervention(wo_id, data.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Ordre de travail non trouvé")
    return InterventionResponse.model_validate(item, from_attributes=True)


# ============================================================
# WORK ORDER PARTS
# ============================================================

@router.post("/work-orders/{wo_id}/parts", response_model=WorkOrderPartResponse, status_code=201)
async def add_wo_part(
    wo_id: int,
    data: WorkOrderPartCreate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.add_wo_part(wo_id, data.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Ordre de travail non trouvé")
    r = WorkOrderPartResponse.model_validate(item, from_attributes=True)
    if item.part:
        r.part_summary = {
            "id": item.part.id,
            "reference": item.part.reference,
            "name": item.part.name,
        }
    return r


@router.delete("/work-order-parts/{part_link_id}", response_model=MessageResponse)
async def remove_wo_part(
    part_link_id: int,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    removed = await service.remove_wo_part(part_link_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    return MessageResponse(message="Pièce retirée")


# ============================================================
# COSTS
# ============================================================

@router.post("/work-orders/{wo_id}/costs", response_model=CostResponse, status_code=201)
async def add_cost(
    wo_id: int,
    data: CostCreate,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.add_cost(wo_id, data.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Ordre de travail non trouvé")
    return CostResponse.model_validate(item, from_attributes=True)


# ============================================================
# PLANS (Préventif)
# ============================================================

@router.get("/plans", response_model=PlanListResponse)
async def list_plans(
    params: PlanListParams = Depends(),
    service: MaintenanceService = Depends(get_maintenance_service),
):
    items, total = await service.search_plans(
        page=params.page, page_size=params.page_size,
        search=params.search, equipment_id=params.equipment_id,
        frequency=params.frequency, is_active=params.is_active,
        sort_by=params.sort_by, sort_order=params.sort_order,
    )
    responses = []
    for item in items:
        r = PlanResponse.model_validate(item, from_attributes=True)
        if item.equipment:
            r.equipment_summary = {
                "id": item.equipment.id,
                "reference": item.equipment.reference,
                "name": item.equipment.name,
            }
        responses.append(r)
    return PlanListResponse(
        items=responses, total=total, page=params.page, page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: int,
    service: MaintenanceService = Depends(get_maintenance_service),
):
    item = await service.get_plan(plan_id)
    if not item:
        raise HTTPException(status_code=404, detail="Plan non trouvé")
    r = PlanResponse.model_validate(item, from_attributes=True)
    if item.equipment:
        r.equipment_summary = {
            "id": item.equipment.id,
            "reference": item.equipment.reference,
            "name": item.equipment.name,
        }
    return r


@router.post("/plans", response_model=PlanResponse, status_code=201)
async def create_plan(
    data: PlanCreate,
    current_user: User = Depends(require_permission("maintenance.plan")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    item = await service.create_plan(data.model_dump())
    return PlanResponse.model_validate(item, from_attributes=True)


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: int,
    data: PlanUpdate,
    current_user: User = Depends(require_permission("maintenance.plan")),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    service = MaintenanceService(db, audit=audit, current_user=current_user)
    item = await service.update_plan(plan_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Plan non trouvé")
    return PlanResponse.model_validate(item, from_attributes=True)


# ============================================================
# AI CHAT
# ============================================================

@router.post("/ai/chat", response_model=AIChatResponse)
async def ai_chat(
    data: AIChatRequest,
    current_user: User = Depends(require_permission("ai.use")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.maintenance import AIConversation, AIMessage

    if data.conversation_id:
        result = await db.execute(
            select(AIConversation).where(
                AIConversation.id == data.conversation_id,
                AIConversation.user_id == current_user.id,
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation non trouvée")
    else:
        conversation = AIConversation(
            user_id=current_user.id,
            module=data.module,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            title=data.message[:100] if data.message else "Nouvelle conversation",
        )
        db.add(conversation)
        await db.flush()

    user_msg = AIMessage(
        conversation_id=conversation.id,
        role="user",
        content=data.message,
    )
    db.add(user_msg)

    ai_response = f"Assistant IA - Module: {data.module}. Votre question: {data.message}"
    ai_msg = AIMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=ai_response,
        model="local",
    )
    db.add(ai_msg)
    await db.commit()

    return AIChatResponse(
        response=ai_response,
        conversation_id=conversation.id,
        model="local",
    )


@router.get("/ai/conversations")
async def list_ai_conversations(
    module: Optional[str] = None,
    current_user: User = Depends(require_permission("ai.use")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.maintenance import AIConversation

    query = select(AIConversation).where(AIConversation.user_id == current_user.id)
    if module:
        query = query.where(AIConversation.module == module)
    query = query.order_by(AIConversation.created_at.desc()).limit(50)

    result = await db.execute(query)
    conversations = result.scalars().all()

    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "module": c.module,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in conversations
        ]
    }


@router.get("/ai/conversations/{conversation_id}")
async def get_ai_conversation(
    conversation_id: int,
    current_user: User = Depends(require_permission("ai.use")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.maintenance import AIConversation, AIMessage

    result = await db.execute(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation non trouvée")

    result = await db.execute(
        select(AIMessage).where(
            AIMessage.conversation_id == conversation_id
        ).order_by(AIMessage.created_at)
    )
    messages = result.scalars().all()

    return {
        "id": conversation.id,
        "title": conversation.title,
        "module": conversation.module,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "model": m.model,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


# ============================================================
# HELPERS
# ============================================================

async def _get_equipment_summary(db, equipment_id: int):
    from app.services.maintenance import _get_equipment_summary as _get_eq
    return await _get_eq(db, equipment_id)


async def _get_user_summary(db, user_id: int):
    from app.services.maintenance import _get_user_summary as _get_us
    return await _get_us(db, user_id)
