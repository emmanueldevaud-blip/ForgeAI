from datetime import date, datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AgendaPeriod = Literal["full", "morning", "afternoon"]


class AgendaRoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    building_id: int
    building_name: Optional[str] = None
    workstation_capacity: int = 0


class AgendaPresenceItem(BaseModel):
    id: Optional[int] = None
    person_type: Literal["user", "external", "cleaning", "occupant"]
    person_id: Optional[int] = None
    person_name: str
    room_id: Optional[int] = None
    needs_workstation: bool = False
    needs_meal: bool = False
    is_remote: bool = False
    source: str
    is_mine: bool = False
    origin_ref: Optional[str] = None
    period: AgendaPeriod = "full"


class AgendaRoomDayCounters(BaseModel):
    room_id: int
    present_count: int = 0
    workstation_count: int = 0
    capacity: int = 0
    presences: List[AgendaPresenceItem] = []


class AgendaDayResponse(BaseModel):
    date: date
    total_present: int = 0
    total_workstations: int = 0
    rooms: List[AgendaRoomDayCounters] = []
    # Présences en télétravail (sans local) : comptées dans total_present,
    # jamais dans les compteurs de local.
    remote: List[AgendaPresenceItem] = []
    integrated: List[AgendaPresenceItem] = []


class AgendaPlanningGroup(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    depth: int = 0
    parent_id: Optional[int] = None


class AgendaPlanningPerson(BaseModel):
    person_id: int
    name: str
    group_id: Optional[int] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None


class AgendaPlanningResponse(BaseModel):
    view: Literal["week", "month"]
    start_date: date
    end_date: date
    rooms: List[AgendaRoomResponse] = []
    days: List[AgendaDayResponse] = []
    planning_groups: List[AgendaPlanningGroup] = []
    planning_people: List[AgendaPlanningPerson] = []


class AgendaSettingsResponse(BaseModel):
    planning_group_ids: List[int] = []


class AgendaSettingsUpdate(BaseModel):
    planning_group_ids: List[int] = []


class AgendaGroupOption(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    source: str = "local"
    user_count: int = 0


class AgendaGroupListResponse(BaseModel):
    groups: List[AgendaGroupOption] = []


class AgendaPresenceUpsert(BaseModel):
    presence_date: date
    # None + is_remote=True = télétravail (présence sans local).
    room_id: Optional[int] = None
    is_present: bool = True
    needs_workstation: bool = False
    needs_meal: bool = False
    is_remote: bool = False
    period: AgendaPeriod = "full"
    user_id: Optional[int] = None


class AgendaAutoAssignRequest(BaseModel):
    start_date: date
    end_date: date


class AgendaAutoAssignResponse(BaseModel):
    created: int = 0
    skipped: int = 0


class AgendaExternalPresenceCreate(BaseModel):
    presence_date: date
    room_id: int
    external_name: str = Field(..., min_length=1, max_length=200)
    needs_workstation: bool = False
    needs_meal: bool = False
    period: AgendaPeriod = "full"


class AgendaUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    role: str
    source: str
    full_name: Optional[str] = None


class AgendaPresenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    presence_date: date
    room_id: Optional[int] = None
    user_id: Optional[int] = None
    external_name: Optional[str] = None
    source: str
    source_ref: Optional[str] = None
    is_present: bool
    needs_workstation: bool
    needs_meal: bool = False
    is_remote: bool = False
    period: AgendaPeriod = "full"
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class AgendaSynthesisRoom(BaseModel):
    room_id: int
    room_name: str
    building_name: Optional[str] = None
    capacity: int
    person_count: int = 0
    meal_count: int = 0
    workstation_count: int = 0


class AgendaSynthesisDay(BaseModel):
    date: date
    rooms: List[AgendaSynthesisRoom] = []
    total_persons: int = 0
    total_meals: int = 0
    total_workstations: int = 0
    total_remote: int = 0


class AgendaSynthesisResponse(BaseModel):
    start_date: date
    end_date: date
    days: List[AgendaSynthesisDay] = []
    grand_total_persons: int = 0
    grand_total_meals: int = 0
    grand_total_workstations: int = 0
    grand_total_remote: int = 0


class AgendaImportStagedRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sheet_name: str
    line_number: int
    presence_date: date
    period: AgendaPeriod
    is_remote: bool
    raw_label: str
    user_id: Optional[int] = None
    external_name: Optional[str] = None
    room_id: Optional[int] = None
    site_label: Optional[str] = None
    needs_workstation: bool
    needs_meal: bool
    status: str
    review_reason: Optional[str] = None
    suggestions: Optional[List[dict[str, Any]]] = None


class AgendaImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    file_name: str
    status: str
    uploaded_by: Optional[int] = None
    created_at: datetime
    validated_at: Optional[datetime] = None
    rows_total: int
    rows_ready: int
    rows_needs_review: int
    rows_skipped_existing: int
    rows_excluded: int
    created_count: Optional[int] = None
    week_start: Optional[date] = None
    week_end: Optional[date] = None


class AgendaImportBatchCreate(BaseModel):
    file_name: str


class AgendaImportBatchListResponse(BaseModel):
    batches: List[AgendaImportBatchResponse]


class AgendaImportStagedRowUpdate(BaseModel):
    user_id: Optional[int] = None
    external_name: Optional[str] = None
    room_id: Optional[int] = None
    site_label: Optional[str] = None
    status: Optional[str] = None
    skip: Optional[bool] = None
