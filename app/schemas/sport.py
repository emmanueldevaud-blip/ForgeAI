from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SportActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sport_type: str
    activity_name: Optional[str] = None
    started_at: datetime
    duration_seconds: int
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    elevation_loss_m: Optional[float] = None
    avg_speed_m_s: Optional[float] = None
    avg_pace_sec_km: Optional[float] = None
    avg_heart_rate: Optional[float] = None
    max_heart_rate: Optional[float] = None
    avg_cadence: Optional[float] = None
    avg_power_w: Optional[float] = None
    calories: Optional[float] = None
    temperature_c: Optional[float] = None
    source_type: str
    source_file_name: Optional[str] = None
    external_id: Optional[str] = None


class SportActivityCreate(BaseModel):
    sport_type: str = Field("other", max_length=50)
    activity_name: Optional[str] = Field(None, max_length=200)
    started_at: datetime
    duration_seconds: int = Field(0, ge=0)
    distance_m: Optional[float] = Field(None, ge=0)
    elevation_gain_m: Optional[float] = Field(None, ge=0)
    elevation_loss_m: Optional[float] = Field(None, ge=0)
    avg_speed_m_s: Optional[float] = Field(None, ge=0)
    avg_pace_sec_km: Optional[float] = Field(None, ge=0)
    avg_heart_rate: Optional[float] = Field(None, ge=0)
    max_heart_rate: Optional[float] = Field(None, ge=0)
    avg_cadence: Optional[float] = Field(None, ge=0)
    avg_power_w: Optional[float] = Field(None, ge=0)
    calories: Optional[float] = Field(None, ge=0)
    temperature_c: Optional[float] = None
    metadata_json: dict[str, Any] = {}


class SportActivityListResponse(BaseModel):
    items: list[SportActivityResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SportGoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    goal_type: str = Field(..., min_length=1, max_length=50)
    target_value: Optional[float] = None
    unit: Optional[str] = Field(None, max_length=30)
    target_date: Optional[date] = None
    metadata_json: dict[str, Any] = {}


class SportGoalResponse(SportGoalCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    status: str


class SportDashboardResponse(BaseModel):
    period_days: int
    period_start: date
    period_end: date
    summary: dict[str, Any]
    trends: list[dict[str, Any]] = Field(default_factory=list)
    daily: list[dict[str, Any]] = Field(default_factory=list)
    weekly: list[dict[str, Any]] = Field(default_factory=list)
    sports: list[dict[str, Any]] = Field(default_factory=list)
    calendar: list[dict[str, Any]] = Field(default_factory=list)
    heart_rate: Optional[dict[str, Any]] = None
    elevation: dict[str, Any] = Field(default_factory=dict)
    latest_activity: Optional[SportActivityResponse] = None
    recent_activities: list[SportActivityResponse] = Field(default_factory=list)
    goals: list[SportGoalResponse] = Field(default_factory=list)
    ai: dict[str, Any] = Field(default_factory=lambda: {"available": False})


class GarminConnectRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)
    mfa_code: Optional[str] = Field(None, max_length=20)
    initial_sync_days: int = Field(30, ge=1, le=365)


class GarminConnectionResponse(BaseModel):
    connected: bool
    status: Optional[str] = None
    garmin_email: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    initial_sync_days: int = 30


class GarminSyncResponse(BaseModel):
    status: str
    imported_count: int = 0
    last_sync_at: Optional[datetime] = None
    message: Optional[str] = None


class SportNormalizedActivity(BaseModel):
    sport_type: str = "other"
    activity_name: Optional[str] = None
    started_at: datetime
    duration_seconds: int = 0
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    elevation_loss_m: Optional[float] = None
    avg_speed_m_s: Optional[float] = None
    avg_pace_sec_km: Optional[float] = None
    avg_heart_rate: Optional[float] = None
    max_heart_rate: Optional[float] = None
    avg_cadence: Optional[float] = None
    avg_power_w: Optional[float] = None
    calories: Optional[float] = None
    temperature_c: Optional[float] = None
    source_type: str = "manual"
    source_file_name: Optional[str] = None
    source_file_path: Optional[str] = None
    external_id: Optional[str] = None
    metadata_json: dict[str, Any] = {}
    track_points: list[dict[str, Any]] = []
