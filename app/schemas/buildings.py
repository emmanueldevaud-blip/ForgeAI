from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# USAGE TYPES
# ============================================================

class UsageTypeBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class UsageTypeCreate(UsageTypeBase):
    pass


class UsageTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class UsageTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class UsageTypeListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("sort_order", max_length=50)
    sort_order: Optional[str] = Field("asc", pattern="^(asc|desc)$")


class UsageTypeListResponse(BaseModel):
    items: List[UsageTypeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# ROOM TYPES
# ============================================================

class RoomTypeBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class RoomTypeCreate(RoomTypeBase):
    pass


class RoomTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class RoomTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class RoomTypeListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("sort_order", max_length=50)
    sort_order: Optional[str] = Field("asc", pattern="^(asc|desc)$")


class RoomTypeListResponse(BaseModel):
    items: List[RoomTypeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# SITES
# ============================================================

class SiteBase(BaseModel):
    reference: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    address_complement: Optional[str] = Field(None, max_length=500)
    postal_code: Optional[str] = Field(None, max_length=20)
    city: Optional[str] = Field(None, max_length=200)
    country: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    is_active: bool = True


class SiteCreate(SiteBase):
    pass


class SiteUpdate(BaseModel):
    reference: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    address_complement: Optional[str] = Field(None, max_length=500)
    postal_code: Optional[str] = Field(None, max_length=20)
    city: Optional[str] = Field(None, max_length=200)
    country: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    address: Optional[str] = None
    address_complement: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    building_count: int = 0


class SiteListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class SiteListResponse(BaseModel):
    items: List[SiteResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SiteWithBuildingsResponse(SiteResponse):
    buildings: List["BuildingSummaryResponse"] = []


# ============================================================
# BUILDINGS
# ============================================================

class BuildingBase(BaseModel):
    site_id: int
    reference: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    building_number: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    floors_count: Optional[int] = Field(None, ge=0)
    is_active: bool = True


class BuildingCreate(BuildingBase):
    pass


class BuildingUpdate(BaseModel):
    reference: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    building_number: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    floors_count: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class BuildingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    reference: str
    name: str
    building_number: Optional[str] = None
    description: Optional[str] = None
    floors_count: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    level_count: int = 0


class BuildingSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    is_active: bool


class BuildingListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    site_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class BuildingListResponse(BaseModel):
    items: List[BuildingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class BuildingWithLevelsResponse(BuildingResponse):
    levels: List["LevelSummaryResponse"] = []


# ============================================================
# LEVELS
# ============================================================

class LevelBase(BaseModel):
    building_id: int
    reference: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    level_order: int = 0
    description: Optional[str] = None
    is_active: bool = True


class LevelCreate(LevelBase):
    pass


class LevelUpdate(BaseModel):
    reference: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    level_order: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class LevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    building_id: int
    reference: str
    name: str
    level_order: int
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    room_count: int = 0


class LevelSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    level_order: int
    is_active: bool


class LevelListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    building_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("level_order", max_length=50)
    sort_order: Optional[str] = Field("asc", pattern="^(asc|desc)$")


class LevelListResponse(BaseModel):
    items: List[LevelResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class LevelWithRoomsResponse(LevelResponse):
    rooms: List["RoomSummaryResponse"] = []


# ============================================================
# ROOMS
# ============================================================

class RoomBase(BaseModel):
    level_id: int
    reference: str = Field(..., min_length=1, max_length=50)
    room_type_id: Optional[int] = None
    usage_type_id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=200)
    area: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = None
    is_active: bool = True


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    reference: Optional[str] = Field(None, min_length=1, max_length=50)
    room_type_id: Optional[int] = None
    usage_type_id: Optional[int] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    area: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level_id: int
    reference: str
    room_type_id: Optional[int] = None
    room_type: Optional[RoomTypeResponse] = None
    usage_type_id: Optional[int] = None
    usage_type: Optional[UsageTypeResponse] = None
    name: str
    area: Optional[Decimal] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RoomSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    is_active: bool


class RoomListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    level_id: Optional[int] = None
    room_type_id: Optional[int] = None
    usage_type_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class RoomListResponse(BaseModel):
    items: List[RoomResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# MESSAGE
# ============================================================

class MessageResponse(BaseModel):
    message: str
