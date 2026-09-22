from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class VolunteerCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    is_active: bool = True


class VolunteerUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class VolunteerResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
