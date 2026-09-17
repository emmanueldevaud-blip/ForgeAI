from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# HOUSING
# ============================================================

class HousingBase(BaseModel):
    room_id: int
    housing_type: Optional[str] = Field(None, max_length=50)
    capacity: int = Field(1, ge=1)
    beds: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    has_kitchen: bool = False
    has_balcony: bool = False
    floor_number: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None
    is_active: bool = True


class HousingCreate(HousingBase):
    pass


class HousingUpdate(BaseModel):
    housing_type: Optional[str] = Field(None, max_length=50)
    capacity: Optional[int] = Field(None, ge=1)
    beds: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    has_kitchen: Optional[bool] = None
    has_balcony: Optional[bool] = None
    floor_number: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class RoomSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reference: str
    name: str
    area: Optional[Decimal] = None


class BuildingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class LevelSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    building: Optional[BuildingSummary] = None


class SiteSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class UsageTypeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class HousingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    room: Optional[RoomSummary] = None
    housing_type: Optional[str] = None
    capacity: int
    beds: Optional[int] = None
    bathrooms: Optional[int] = None
    has_kitchen: bool
    has_balcony: bool
    floor_number: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    current_occupancy: Optional[str] = None
    cleaning_status: Optional[str] = None
    level: Optional[LevelSummary] = None
    site: Optional[SiteSummary] = None


class HousingListParams(BaseModel):
    page: int = 1
    page_size: int = 20
    search: Optional[str] = None
    is_active: Optional[bool] = None
    site_id: Optional[int] = None
    building_id: Optional[int] = None
    housing_type: Optional[str] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"


class HousingListResponse(BaseModel):
    items: List[HousingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# OCCUPANT
# ============================================================

class OccupantBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    id_type: Optional[str] = Field(None, max_length=50)
    id_number: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    is_active: bool = True


class OccupantCreate(OccupantBase):
    pass


class OccupantUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    id_type: Optional[str] = Field(None, max_length=50)
    id_number: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class OccupantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OccupantListParams(BaseModel):
    page: int = 1
    page_size: int = 20
    search: Optional[str] = None
    is_active: Optional[bool] = None
    sort_by: str = "last_name"
    sort_order: str = "asc"


class OccupantListResponse(BaseModel):
    items: List[OccupantResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# OCCUPANCY
# ============================================================

class OccupancyBase(BaseModel):
    housing_id: int
    occupant_id: int
    arrival_date: datetime
    departure_date: datetime
    purpose: Optional[str] = Field(None, max_length=200)
    observations: Optional[str] = None
    nb_persons: int = Field(1, ge=1)


class OccupancyCreate(OccupancyBase):
    pass


class OccupancyUpdate(BaseModel):
    occupant_id: Optional[int] = None
    arrival_date: Optional[datetime] = None
    departure_date: Optional[datetime] = None
    actual_arrival: Optional[datetime] = None
    actual_departure: Optional[datetime] = None
    purpose: Optional[str] = Field(None, max_length=200)
    observations: Optional[str] = None
    nb_persons: Optional[int] = Field(None, ge=1)


class OccupancyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    housing_id: int
    housing: Optional[HousingResponse] = None
    occupant_id: int
    occupant: Optional[OccupantResponse] = None
    status: str
    arrival_date: datetime
    departure_date: datetime
    actual_arrival: Optional[datetime] = None
    actual_departure: Optional[datetime] = None
    purpose: Optional[str] = None
    observations: Optional[str] = None
    nb_persons: int
    created_at: datetime
    updated_at: datetime


class OccupancyListParams(BaseModel):
    page: int = 1
    page_size: int = 20
    search: Optional[str] = None
    status: Optional[str] = None
    housing_id: Optional[int] = None
    occupant_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    sort_by: str = "arrival_date"
    sort_order: str = "desc"


class OccupancyListResponse(BaseModel):
    items: List[OccupancyResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# UNAVAILABILITY
# ============================================================

class UnavailabilityBase(BaseModel):
    housing_id: int
    start_date: date
    end_date: date
    reason: str = Field(..., max_length=50)
    comment: Optional[str] = None


class UnavailabilityCreate(UnavailabilityBase):
    pass


class UnavailabilityUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reason: Optional[str] = Field(None, max_length=50)
    comment: Optional[str] = None


class UnavailabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    housing_id: int
    housing: Optional[HousingResponse] = None
    start_date: date
    end_date: date
    reason: str
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UnavailabilityListParams(BaseModel):
    page: int = 1
    page_size: int = 20
    housing_id: Optional[int] = None
    reason: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    sort_by: str = "start_date"
    sort_order: str = "desc"


class UnavailabilityListResponse(BaseModel):
    items: List[UnavailabilityResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# HOUSING DASHBOARD
# ============================================================

class HousingDashboard(BaseModel):
    total_housings: int = 0
    occupied: int = 0
    free: int = 0
    arrivals_today: int = 0
    departures_today: int = 0
    to_clean: int = 0
    unavailabilities: int = 0
    occupancy_rate: float = 0.0
    recent_occupancies: List[OccupancyResponse] = []
    by_cleaning_status: list = []
    upcoming_arrivals: List[OccupancyResponse] = []


# ============================================================
# PLANNING
# ============================================================

class PlanningEntry(BaseModel):
    occupancy_id: int
    housing_id: int
    housing_name: str
    housing_reference: str
    occupant_name: str
    status: str
    arrival_date: datetime
    departure_date: datetime
    nb_persons: int


class PlanningResponse(BaseModel):
    housings: list = []
    entries: List[PlanningEntry] = []
    start_date: date
    end_date: date


# ============================================================
# MESSAGES
# ============================================================

class MessageResponse(BaseModel):
    message: str
