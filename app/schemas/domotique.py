"""Schemas Pydantic du module Domotique."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Dispositif / capteurs / sorties
# --------------------------------------------------------------------------- #

class DomotiqueSensorResponse(BaseModel):
    id: int
    key: str
    name: str
    unit: str
    enabled: bool
    current_value: Optional[float] = None
    corrected_value: Optional[float] = None
    current_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DomotiqueOutputResponse(BaseModel):
    id: int
    index: int
    name: str
    role: str
    mode: str
    state: bool
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DomotiqueCurrentCycleResponse(BaseModel):
    id: int
    profile_id: int
    profile_name: Optional[str] = None
    name: Optional[str] = None
    product: Optional[str] = None
    casing_size: Optional[str] = None
    status: str
    current_phase_id: Optional[int] = None
    current_phase_name: Optional[str] = None
    current_phase_order: Optional[int] = None
    phase_started_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    initial_weight: Optional[float] = None
    current_weight: Optional[float] = None
    target_weight_loss_pct: Optional[float] = None
    weight_loss_pct: Optional[float] = None
    manual_outputs: bool = False
    phases_total: int = 0


class DomotiqueDeviceStatusResponse(BaseModel):
    code: str
    name: str
    kind: str
    status: str
    last_seen: Optional[datetime] = None
    last_error: Optional[str] = None
    base_url: Optional[str] = None
    poll_interval_s: int
    stale: bool = False
    sensors: list[DomotiqueSensorResponse] = Field(default_factory=list)
    outputs: list[DomotiqueOutputResponse] = Field(default_factory=list)
    cycle: Optional[DomotiqueCurrentCycleResponse] = None
    config: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Historique
# --------------------------------------------------------------------------- #

class DomotiqueHistoryPoint(BaseModel):
    t: datetime
    v: float


class DomotiqueOutputSeriesResponse(BaseModel):
    index: int
    name: str
    role: str
    points: list[DomotiqueHistoryPoint] = Field(default_factory=list)


class DomotiqueHistoryResponse(BaseModel):
    period: str
    start: datetime
    end: datetime
    min_sample_s: int
    series: dict[str, list[DomotiqueHistoryPoint]] = Field(default_factory=dict)
    outputs: list[DomotiqueOutputSeriesResponse] = Field(default_factory=list)
    target_temperature: Optional[float] = None
    target_humidity: Optional[float] = None
    min: dict[str, Optional[float]] = Field(default_factory=dict)
    max: dict[str, Optional[float]] = Field(default_factory=dict)
    trend: dict[str, Optional[float]] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Cycles
# --------------------------------------------------------------------------- #

class DomotiquePhaseResponse(BaseModel):
    id: int
    order: int
    name: str
    target_temperature: Optional[float] = None
    target_humidity: Optional[float] = None
    tolerance_temperature: Optional[float] = None
    tolerance_humidity: Optional[float] = None
    min_duration_hours: Optional[float] = None
    max_duration_hours: Optional[float] = None
    weight_loss_target_pct: Optional[float] = None
    exit_condition: str

    model_config = {"from_attributes": True}


class DomotiqueProfileResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    target_weight_loss_pct: Optional[float] = None
    weight_loss_min_pct: Optional[float] = None
    weight_loss_max_pct: Optional[float] = None
    is_system: bool = False
    phases: list[DomotiquePhaseResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class DomotiquePhaseUpsert(BaseModel):
    id: Optional[int] = None
    order: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    target_temperature: Optional[float] = None
    target_humidity: Optional[float] = None
    tolerance_temperature: Optional[float] = Field(default=None, ge=0)
    tolerance_humidity: Optional[float] = Field(default=None, ge=0)
    min_duration_hours: Optional[float] = Field(default=None, ge=0)
    max_duration_hours: Optional[float] = Field(default=None, ge=0)
    weight_loss_target_pct: Optional[float] = Field(default=None, ge=0, le=100)
    exit_condition: str = "time"


class DomotiqueProfileUpsert(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    target_weight_loss_pct: Optional[float] = Field(default=None, ge=0, le=100)
    weight_loss_min_pct: Optional[float] = Field(default=None, ge=0, le=100)
    weight_loss_max_pct: Optional[float] = Field(default=None, ge=0, le=100)
    phases: list[DomotiquePhaseUpsert] = Field(min_length=1)


class DomotiqueProfileListResponse(BaseModel):
    profiles: list[DomotiqueProfileResponse] = Field(default_factory=list)
    total: int = 0


class DomotiqueCycleCreate(BaseModel):
    profile_id: int
    device_code: str = "sechoir-saucisson"
    name: Optional[str] = None
    product: Optional[str] = None
    casing_size: Optional[str] = None
    initial_weight: Optional[float] = Field(default=None, ge=0)
    target_weight_loss_pct: Optional[float] = Field(default=None, ge=0, le=100)
    started_at: Optional[datetime] = None
    start_now: bool = True


class DomotiqueCycleResponse(DomotiqueCurrentCycleResponse):
    profile_code: Optional[str] = None
    status_label: str = ""
    created_at: Optional[datetime] = None


class DomotiqueCycleListResponse(BaseModel):
    cycles: list[DomotiqueCycleResponse] = Field(default_factory=list)
    total: int = 0


# --------------------------------------------------------------------------- #
# Journal
# --------------------------------------------------------------------------- #

class DomotiqueEventResponse(BaseModel):
    id: int
    device_id: int
    cycle_id: Optional[int] = None
    type: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class DomotiqueEventListResponse(BaseModel):
    events: list[DomotiqueEventResponse] = Field(default_factory=list)
    total: int = 0


# --------------------------------------------------------------------------- #
# Commandes / configuration
# --------------------------------------------------------------------------- #

class DomotiqueManualRequest(BaseModel):
    output_index: int = Field(ge=0, le=7)
    state: bool


class DomotiqueManualResponse(BaseModel):
    ok: bool
    output_index: int
    state: bool
    message: str = ""


class DomotiqueConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    poll_interval_s: Optional[int] = Field(default=None, ge=5, le=600)
    api_user: Optional[str] = Field(default=None, max_length=100)
    api_password: Optional[str] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    hum_min: Optional[float] = None
    hum_max: Optional[float] = None
    alert_cooldown_min: Optional[int] = Field(default=None, ge=1, le=1440)
    retention_days: Optional[int] = Field(default=None, ge=7, le=730)
    obsolete_after_s: Optional[int] = Field(default=None, ge=15, le=3600)
    cooler_min_off_s: Optional[int] = Field(default=None, ge=0, le=3600)
    cooler_min_on_s: Optional[int] = Field(default=None, ge=0, le=3600)
    alarm_temp_delta: Optional[float] = Field(default=None, ge=0.1, le=50)
    alarm_hum_delta: Optional[float] = Field(default=None, ge=0.1, le=100)
    comm_timeout_s: Optional[int] = Field(default=None, ge=10, le=3600)
    default_tolerance_temperature: Optional[float] = Field(default=None, ge=0.1, le=50)
    default_tolerance_humidity: Optional[float] = Field(default=None, ge=0.1, le=100)


class DomotiqueConfigTestRequest(BaseModel):
    """Valeurs de connexion a tester (non enregistrees)."""

    base_url: Optional[str] = None
    api_user: Optional[str] = None
    api_password: Optional[str] = None


class DomotiqueConfigResponse(BaseModel):
    code: str
    base_url: Optional[str] = None
    poll_interval_s: int
    api_user: Optional[str] = None
    has_api_password: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    outputs: list[DomotiqueOutputResponse] = Field(default_factory=list)
    sensors: list[DomotiqueSensorResponse] = Field(default_factory=list)


class DomotiqueTestConnectionResponse(BaseModel):
    ok: bool
    message: str
    latency_ms: Optional[int] = None
    state: Optional[dict[str, Any]] = None
