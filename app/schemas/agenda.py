from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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
    source: str
    is_mine: bool = False
    origin_ref: Optional[str] = None


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
    integrated: List[AgendaPresenceItem] = []


class AgendaPlanningResponse(BaseModel):
    view: Literal["week", "month", "quarter"]
    start_date: date
    end_date: date
    rooms: List[AgendaRoomResponse] = []
    days: List[AgendaDayResponse] = []


class AgendaPresenceUpsert(BaseModel):
    presence_date: date
    room_id: int
    is_present: bool = True
    needs_workstation: bool = False


class AgendaExternalPresenceCreate(BaseModel):
    presence_date: date
    room_id: int
    external_name: str = Field(..., min_length=1, max_length=200)
    needs_workstation: bool = False


class AgendaPresenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    presence_date: date
    room_id: int
    user_id: Optional[int] = None
    external_name: Optional[str] = None
    source: str
    source_ref: Optional[str] = None
    is_present: bool
    needs_workstation: bool
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
