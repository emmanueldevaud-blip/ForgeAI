from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# PROVIDERS
# ============================================================

class ProviderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = None
    contract_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    is_active: bool = True


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = None
    contract_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    contract_reference: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProviderListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search: Optional[str] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = "created_at"
    sort_order: Optional[str] = "desc"


class ProviderListResponse(BaseModel):
    items: List[ProviderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# PARTS
# ============================================================

class PartBase(BaseModel):
    reference: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    unit_cost: Optional[Decimal] = None
    unit: Optional[str] = Field(None, max_length=20)
    is_active: bool = True


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    unit_cost: Optional[Decimal] = None
    unit: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class PartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    description: Optional[str] = None
    unit_cost: Optional[Decimal] = None
    unit: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PartListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search: Optional[str] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = "created_at"
    sort_order: Optional[str] = "desc"


class PartListResponse(BaseModel):
    items: List[PartResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# CONTRACTS
# ============================================================

class ContractBase(BaseModel):
    provider_id: int
    reference: str = Field(..., min_length=1, max_length=100)
    subject: str = Field(..., min_length=1, max_length=300)
    start_date: date
    end_date: Optional[date] = None
    renewal_date: Optional[date] = None
    cost: Optional[Decimal] = None
    periodicity: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    is_active: bool = True


class ContractCreate(ContractBase):
    equipment_ids: List[int] = []


class ContractUpdate(BaseModel):
    provider_id: Optional[int] = None
    reference: Optional[str] = Field(None, min_length=1, max_length=100)
    subject: Optional[str] = Field(None, min_length=1, max_length=300)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    renewal_date: Optional[date] = None
    cost: Optional[Decimal] = None
    periodicity: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    equipment_ids: Optional[List[int]] = None


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    provider: Optional[ProviderResponse] = None
    reference: str
    subject: str
    start_date: date
    end_date: Optional[date] = None
    renewal_date: Optional[date] = None
    cost: Optional[Decimal] = None
    periodicity: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    equipment_count: int = 0


class ContractListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search: Optional[str] = None
    provider_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = "created_at"
    sort_order: Optional[str] = "desc"


class ContractListResponse(BaseModel):
    items: List[ContractResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# MAINTENANCE REQUESTS
# ============================================================

class RequestBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    equipment_id: Optional[int] = None
    priority: str = Field("normale", max_length=20)
    desired_date: Optional[date] = None


class RequestCreate(RequestBase):
    pass


class RequestUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    equipment_id: Optional[int] = None
    priority: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=30)
    desired_date: Optional[date] = None
    comment: Optional[str] = None


class RequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    title: str
    description: Optional[str] = None
    equipment_id: Optional[int] = None
    requested_by: Optional[int] = None
    priority: str
    status: str
    desired_date: Optional[date] = None
    location_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    equipment_summary: Optional[dict] = None
    requested_by_summary: Optional[dict] = None


class RequestListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    equipment_id: Optional[int] = None
    requested_by: Optional[int] = None
    sort_by: Optional[str] = "created_at"
    sort_order: Optional[str] = "desc"


class RequestListResponse(BaseModel):
    items: List[RequestResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# WORK ORDERS
# ============================================================

class WorkOrderBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    equipment_id: Optional[int] = None
    request_id: Optional[int] = None
    provider_id: Optional[int] = None
    contract_id: Optional[int] = None
    responsible_id: Optional[int] = None
    maintenance_type: str = Field("corrective", max_length=30)
    priority: str = Field("normale", max_length=20)
    planned_date: Optional[date] = None
    estimated_duration_hours: Optional[Decimal] = None


class WorkOrderCreate(WorkOrderBase):
    pass


class WorkOrderUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    equipment_id: Optional[int] = None
    provider_id: Optional[int] = None
    contract_id: Optional[int] = None
    responsible_id: Optional[int] = None
    maintenance_type: Optional[str] = Field(None, max_length=30)
    priority: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=30)
    planned_date: Optional[date] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    estimated_duration_hours: Optional[Decimal] = None
    actual_duration_hours: Optional[Decimal] = None
    diagnosis: Optional[str] = None
    cause: Optional[str] = None
    work_performed: Optional[str] = None
    solution: Optional[str] = None
    recommendations: Optional[str] = None
    notes: Optional[str] = None
    comment: Optional[str] = None


class WorkOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    title: str
    description: Optional[str] = None
    equipment_id: Optional[int] = None
    request_id: Optional[int] = None
    provider_id: Optional[int] = None
    contract_id: Optional[int] = None
    responsible_id: Optional[int] = None
    maintenance_type: str
    priority: str
    status: str
    location_summary: Optional[str] = None
    planned_date: Optional[date] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    estimated_duration_hours: Optional[Decimal] = None
    actual_duration_hours: Optional[Decimal] = None
    diagnosis: Optional[str] = None
    cause: Optional[str] = None
    work_performed: Optional[str] = None
    solution: Optional[str] = None
    recommendations: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    equipment_summary: Optional[dict] = None
    responsible_summary: Optional[dict] = None
    provider_summary: Optional[dict] = None
    request_summary: Optional[dict] = None


class WorkOrderListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    maintenance_type: Optional[str] = None
    equipment_id: Optional[int] = None
    responsible_id: Optional[int] = None
    sort_by: Optional[str] = "created_at"
    sort_order: Optional[str] = "desc"


class WorkOrderListResponse(BaseModel):
    items: List[WorkOrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# INTERVENTIONS
# ============================================================

class InterventionCreate(BaseModel):
    description: Optional[str] = None
    work_performed: Optional[str] = None
    duration_hours: Optional[Decimal] = None


class InterventionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_id: int
    intervention_date: datetime
    description: Optional[str] = None
    work_performed: Optional[str] = None
    duration_hours: Optional[Decimal] = None
    created_at: datetime


# ============================================================
# INTERVENANTS
# ============================================================

class IntervenantCreate(BaseModel):
    user_id: Optional[int] = None
    role_in_intervention: Optional[str] = Field(None, max_length=100)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    hours_spent: Optional[Decimal] = None
    comment: Optional[str] = None


class IntervenantUpdate(BaseModel):
    role_in_intervention: Optional[str] = Field(None, max_length=100)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    hours_spent: Optional[Decimal] = None
    comment: Optional[str] = None


class IntervenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_id: int
    user_id: Optional[int] = None
    role_in_intervention: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    hours_spent: Optional[Decimal] = None
    comment: Optional[str] = None
    created_at: datetime
    user_summary: Optional[dict] = None


# ============================================================
# WORK ORDER PARTS
# ============================================================

class WorkOrderPartCreate(BaseModel):
    part_id: int
    quantity: int = Field(1, ge=1)
    unit_cost: Optional[Decimal] = None
    notes: Optional[str] = Field(None, max_length=300)


class WorkOrderPartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_id: int
    part_id: int
    quantity: int
    unit_cost: Optional[Decimal] = None
    notes: Optional[str] = None
    part_summary: Optional[dict] = None


# ============================================================
# COSTS
# ============================================================

class CostCreate(BaseModel):
    cost_type: str = Field(..., max_length=30)
    amount: Decimal
    description: Optional[str] = Field(None, max_length=300)


class CostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_id: int
    cost_type: str
    amount: Decimal
    description: Optional[str] = None
    created_at: datetime


# ============================================================
# MAINTENANCE PLANS
# ============================================================

class PlanChecklistItemCreate(BaseModel):
    description: str = Field(..., max_length=500)
    sort_order: int = 0
    is_required: bool = False


class PlanChecklistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    description: str
    sort_order: int
    is_required: bool


class PlanBase(BaseModel):
    equipment_id: int
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    intervention_type: Optional[str] = Field(None, max_length=100)
    frequency: str = Field(..., max_length=30)
    frequency_value: int = Field(1, ge=1)
    next_due_date: Optional[date] = None
    estimated_duration_hours: Optional[Decimal] = None
    priority: str = Field("normale", max_length=20)
    instructions: Optional[str] = None
    is_active: bool = True


class PlanCreate(PlanBase):
    checklist_items: List[PlanChecklistItemCreate] = []


class PlanUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    intervention_type: Optional[str] = Field(None, max_length=100)
    frequency: Optional[str] = Field(None, max_length=30)
    frequency_value: Optional[int] = Field(None, ge=1)
    next_due_date: Optional[date] = None
    estimated_duration_hours: Optional[Decimal] = None
    priority: Optional[str] = Field(None, max_length=20)
    instructions: Optional[str] = None
    is_active: Optional[bool] = None
    checklist_items: Optional[List[PlanChecklistItemCreate]] = None


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    title: str
    description: Optional[str] = None
    intervention_type: Optional[str] = None
    frequency: str
    frequency_value: int
    next_due_date: Optional[date] = None
    estimated_duration_hours: Optional[Decimal] = None
    priority: str
    instructions: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    equipment_summary: Optional[dict] = None
    checklist_items: List[PlanChecklistItemResponse] = []


class PlanListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search: Optional[str] = None
    equipment_id: Optional[int] = None
    frequency: Optional[str] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = "created_at"
    sort_order: Optional[str] = "desc"


class PlanListResponse(BaseModel):
    items: List[PlanResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# STATUS CHANGE
# ============================================================

class StatusChange(BaseModel):
    status: str = Field(..., max_length=30)
    comment: Optional[str] = None


# ============================================================
# DASHBOARD
# ============================================================

class MaintenanceDashboard(BaseModel):
    open_requests: int = 0
    open_work_orders: int = 0
    overdue_work_orders: int = 0
    planned_interventions: int = 0
    preventive_due_soon: int = 0
    equipment_in_breakdown: int = 0
    total_cost_month: Decimal = Decimal("0")
    total_cost_year: Decimal = Decimal("0")
    corrective_count_month: int = 0
    preventive_count_month: int = 0
    avg_intervention_hours: Decimal = Decimal("0")


# ============================================================
# AI CHAT
# ============================================================

class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    module: str = Field(..., max_length=50)
    entity_type: Optional[str] = Field(None, max_length=50)
    entity_id: Optional[int] = None
    conversation_id: Optional[int] = None


class AIChatResponse(BaseModel):
    response: str
    conversation_id: int
    model: Optional[str] = None


class MessageResponse(BaseModel):
    message: str
