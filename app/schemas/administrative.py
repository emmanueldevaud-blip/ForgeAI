from datetime import date, datetime

from pydantic import BaseModel, Field


class CapabilityCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    is_active: bool = True


class CapabilityResponse(CapabilityCreate):
    id: int
    model_config = {"from_attributes": True}


class VolunteerCapabilityCreate(BaseModel):
    capability_id: int
    level: int = Field(default=1, ge=1)


class VolunteerCapabilityResponse(VolunteerCapabilityCreate):
    volunteer_id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class UnavailabilityCreate(BaseModel):
    volunteer_id: int
    starts_on: date
    ends_on: date
    reason: str | None = Field(default=None, max_length=255)


class UnavailabilityResponse(UnavailabilityCreate):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class ProgramTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    is_active: bool = True
    frequency: str = Field(default="weekly", min_length=1, max_length=20)
    weekday: int = Field(default=0, ge=0, le=6)
    interval: int = Field(default=1, ge=1)


class ProgramTypeResponse(ProgramTypeCreate):
    id: int
    model_config = {"from_attributes": True}


class RoleTypeCreate(BaseModel):
    program_type_id: int
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    required_capability_id: int | None = None
    is_active: bool = True
    is_optional: bool = False


class RoleTypeResponse(RoleTypeCreate):
    id: int
    model_config = {"from_attributes": True}


class SessionCreate(BaseModel):
    program_type_id: int
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)


class AssignmentResponse(BaseModel):
    id: int
    session_id: int
    role_type_id: int
    volunteer_id: int
    scheduled_date: date
    source: str
    status: str
    assigned_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AssignmentCreate(BaseModel):
    session_id: int
    role_type_id: int
    volunteer_id: int
    scheduled_date: date


class SessionResponse(SessionCreate):
    id: int
    status: str
    assignments: list[AssignmentResponse] = []
    model_config = {"from_attributes": True}


class AssignmentUpdate(BaseModel):
    volunteer_id: int
    scheduled_date: date | None = None


class GenerationResponse(BaseModel):
    session: SessionResponse
    conflicts: list[str]


class ValidationResponse(BaseModel):
    valid: bool
    conflicts: list[str]
    session: SessionResponse
