from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# EQUIPMENT TYPES
# ============================================================

class EquipmentTypeBase(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class EquipmentTypeCreate(EquipmentTypeBase):
    pass


class EquipmentTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class EquipmentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class EquipmentTypeListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("sort_order", max_length=50)
    sort_order: Optional[str] = Field("asc", pattern="^(asc|desc)$")


class EquipmentTypeListResponse(BaseModel):
    items: List[EquipmentTypeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# ROOM SUMMARY (for nested responses)
# ============================================================

class RoomSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str


class LevelSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str


class BuildingSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str


class SiteSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str


# ============================================================
# EQUIPMENT
# ============================================================

class EquipmentBase(BaseModel):
    reference: Optional[str] = Field(None, min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    equipment_type_id: Optional[int] = None
    manufacturer: Optional[str] = Field(None, max_length=200)
    model: Optional[str] = Field(None, max_length=200)
    serial_number: Optional[str] = Field(None, max_length=200)
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = Field(None, ge=0)
    installation_date: Optional[date] = None
    commissioning_date: Optional[date] = None
    warranty_end_date: Optional[date] = None
    status: str = "en_service"
    room_id: int
    notes: Optional[str] = None
    is_active: bool = True


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    reference: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    equipment_type_id: Optional[int] = None
    manufacturer: Optional[str] = Field(None, max_length=200)
    model: Optional[str] = Field(None, max_length=200)
    serial_number: Optional[str] = Field(None, max_length=200)
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = Field(None, ge=0)
    installation_date: Optional[date] = None
    commissioning_date: Optional[date] = None
    warranty_end_date: Optional[date] = None
    status: Optional[str] = None
    room_id: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class EquipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    description: Optional[str] = None
    equipment_type_id: Optional[int] = None
    equipment_type: Optional[EquipmentTypeResponse] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = None
    installation_date: Optional[date] = None
    commissioning_date: Optional[date] = None
    warranty_end_date: Optional[date] = None
    status: str
    room_id: int
    room: Optional[RoomSummaryResponse] = None
    level: Optional[LevelSummaryResponse] = None
    building: Optional[BuildingSummaryResponse] = None
    site: Optional[SiteSummaryResponse] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EquipmentSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    status: str
    is_active: bool


class EquipmentLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    room: Optional[RoomSummaryResponse] = None
    level: Optional[LevelSummaryResponse] = None
    building: Optional[BuildingSummaryResponse] = None
    site: Optional[SiteSummaryResponse] = None


class EquipmentListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    equipment_type_id: Optional[int] = None
    status: Optional[str] = None
    room_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class EquipmentListResponse(BaseModel):
    items: List[EquipmentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# MESSAGE
# ============================================================

class MessageResponse(BaseModel):
    message: str
