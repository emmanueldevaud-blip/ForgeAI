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


class SportGoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    goal_type: Optional[str] = Field(None, min_length=1, max_length=50)
    target_value: Optional[float] = None
    unit: Optional[str] = Field(None, max_length=30)
    target_date: Optional[date] = None
    status: Optional[str] = Field(None, max_length=30)
    metadata_json: Optional[dict[str, Any]] = None


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
    analysis: dict[str, Any] = Field(default_factory=dict)
    goal_analysis: list[dict[str, Any]] = Field(default_factory=list)


class SportHealthResponse(BaseModel):
    period_days: int
    period_start: date
    period_end: date
    days_available: int
    summary: dict[str, Any] = Field(default_factory=dict)
    series: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class SportObservationCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    activity_id: Optional[int] = Field(None, ge=1)
    kind: str = Field("observed", max_length=30)


class SportObservationResponse(BaseModel):
    id: int
    activity_id: Optional[int] = None
    kind: str
    content: str
    status: str
    sources: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class SportNotificationConfigResponse(BaseModel):
    """État des clés VAPID (la clé privée n'est jamais renvoyée)."""

    configured: bool = False
    subject: str = ""
    public_key: str = ""


class SportNotificationConfigUpdate(BaseModel):
    private_key: Optional[str] = Field(None, max_length=2000)
    subject: Optional[str] = Field(None, max_length=200)


class SportHeartRateConfig(BaseModel):
    rest_hr: Optional[float] = Field(None, ge=20, le=250)
    max_hr: Optional[float] = Field(None, ge=80, le=250)
    custom_zones: Optional[list[float]] = Field(None, min_length=5, max_length=5)


class SportAthleteProfileResponse(BaseModel):
    athlete_id: int
    display_name: Optional[str] = None
    heart_rate: Optional[SportHeartRateConfig] = None
    profile: dict[str, Any]


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


# --------------------------------------------------------------------------- #
# Publications Instagram
# --------------------------------------------------------------------------- #

PUBLICATION_STYLES = [
    "humor", "stats", "motivation", "inspiring", "story", "ultra", "short", "custom", "mix",
]

PUBLICATION_STATUSES = ["draft", "validated", "scheduled", "shared", "failed", "refused"]

PUBLICATION_CREATED_FROM = ["activity", "calendar"]

PUBLICATION_TONES = [
    "humor", "self_deprecation", "stats", "storytelling", "inspiration", "expert", "professional",
]


class PublicationProposalResponse(BaseModel):
    title: Optional[str] = None
    content: str
    hashtags: Optional[str] = None
    style: Optional[str] = None


class SportPublicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    activity_id: Optional[int] = None
    calendar_entry_id: Optional[int] = None
    status: str
    styles: list[str] = []
    custom_instructions: Optional[str] = None
    proposals: list[dict[str, Any]] = []
    selected_proposal: Optional[int] = None
    title: Optional[str] = None
    content: Optional[str] = None
    hashtags: Optional[str] = None
    photo_id: Optional[int] = None
    visual_type: str = "photo"
    card_path: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    generated_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    shared_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    activity: Optional[SportActivityResponse] = None
    calendar_entry: Optional["EditorialCalendarEntryResponse"] = None

    # V2 fields
    tone_used: Optional[str] = None
    visual_generation_prompt: Optional[str] = None
    visual_generation_provider: Optional[str] = None
    created_from: Optional[str] = None
    title_locked: bool = False
    content_locked: bool = False
    photo_locked: bool = False


class SportPublicationListResponse(BaseModel):
    items: list[SportPublicationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SportPublicationGenerateRequest(BaseModel):
    styles: list[str] = Field(default_factory=list)
    custom_instructions: Optional[str] = Field(None, max_length=2000)
    regenerate: bool = False


class SportPublicationUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    hashtags: Optional[str] = None
    photo_id: Optional[int] = None
    visual_type: Optional[str] = None
    selected_proposal: Optional[int] = None
    styles: Optional[list[str]] = None
    custom_instructions: Optional[str] = None
    # V2 fields
    tone_used: Optional[str] = Field(None, max_length=50)
    visual_generation_prompt: Optional[str] = None
    visual_generation_provider: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    instagram_media_id: Optional[str] = None
    instagram_permalink: Optional[str] = None
    # Lock fields
    title_locked: Optional[bool] = None
    content_locked: Optional[bool] = None
    photo_locked: Optional[bool] = None


class SportPublicationSettingsResponse(BaseModel):
    notifications_enabled: bool = True
    last_styles: list[str] = []
    last_custom_instructions: Optional[str] = None


class SportPublicationSettingsUpdate(BaseModel):
    notifications_enabled: Optional[bool] = None
    last_styles: Optional[list[str]] = None
    last_custom_instructions: Optional[str] = None


# --------------------------------------------------------------------------- #
# Community Manager V2 - Studio de création
# --------------------------------------------------------------------------- #


class PublicationGenerateFromCalendarRequest(BaseModel):
    """Requête pour générer une publication depuis une entrée de calendrier validée."""
    calendar_entry_id: int
    tone: Optional[str] = Field(None, max_length=50)
    styles: list[str] = Field(default_factory=list)
    custom_instructions: Optional[str] = Field(None, max_length=2000)
    visual_type: str = Field("photo", pattern="^(photo|generated|carousel|reel)$")
    # Si photo_id fourni, utiliser cette photo ; sinon laisser l'IA proposer
    photo_id: Optional[int] = None


class PublicationDraftUpdate(BaseModel):
    """Mise à jour d'un brouillon de publication en cours de création."""
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    hashtags: Optional[str] = None
    photo_id: Optional[int] = None
    visual_type: Optional[str] = Field(None, pattern="^(photo|generated|carousel|reel)$")
    tone_used: Optional[str] = Field(None, max_length=50)
    visual_generation_prompt: Optional[str] = None
    visual_generation_provider: Optional[str] = None
    selected_proposal: Optional[int] = None
    proposals: Optional[list[dict[str, Any]]] = None
    styles: Optional[list[str]] = None
    custom_instructions: Optional[str] = None
    title_locked: Optional[bool] = None
    content_locked: Optional[bool] = None
    photo_locked: Optional[bool] = None


class PublicationDraftResponse(SportPublicationResponse):
    """Réponse complète pour un brouillon (inclut toutes les propositions)."""
    pass


class PublicationGenerateFromCalendarResponse(BaseModel):
    """Réponse pour génération depuis calendrier."""
    publication_id: int
    status: str
    proposals: list[dict[str, Any]] = []


class PublicationVariantsRequest(BaseModel):
    """Demande de génération de variantes de texte."""
    publication_id: int
    tone: Optional[str] = Field(None, max_length=50)
    styles: Optional[list[str]] = None
    custom_instructions: Optional[str] = Field(None, max_length=2000)
    count: int = Field(3, ge=1, le=5)


class PublicationVariantsResponse(BaseModel):
    """Réponse avec les variantes générées."""
    publication_id: int
    variants: list[dict[str, Any]] = []


class PublicationValidateResponse(BaseModel):
    """Réponse après validation humaine."""
    publication_id: int
    status: str
    validated_at: datetime


class PublicationPreviewResponse(BaseModel):
    """Réponse avec le rendu prévisualisé."""
    publication_id: int
    preview_html: str
    format: str


class PublicationGenerateTextRequest(BaseModel):
    """Demande de génération de texte (court ou long) selon le ton."""
    publication_id: int
    length: str = Field(..., pattern="^(short|long)$")  # "short" ou "long"
    tone: Optional[str] = Field(None, max_length=50)
    use_title: bool = True  # Utiliser le titre comme contexte
    styles: Optional[list[str]] = None
    custom_instructions: Optional[str] = Field(None, max_length=2000)


class PublicationGenerateTextResponse(BaseModel):
    """Réponse avec le texte généré."""
    publication_id: int
    title: Optional[str] = None
    content: str
    hashtags: Optional[str] = None


class PublicationPreviewRequest(BaseModel):
    """Demande de prévisualisation Instagram."""
    publication_id: int
    format: str = Field("feed", pattern="^(feed|story|reel)$")


class PublicationPreviewResponse(BaseModel):
    """Réponse avec le rendu prévisualisé."""
    publication_id: int
    preview_html: str
    format: str


class PublicationValidateRequest(BaseModel):
    """Validation humaine avant publication."""
    confirm: bool = True


class PublicationPublishRequest(BaseModel):
    """Publication effective sur Instagram."""
    confirm: bool = True


class PublicationPublishResponse(BaseModel):
    """Réponse après publication Instagram."""
    publication_id: int
    status: str
    instagram_media_id: Optional[str] = None
    instagram_permalink: Optional[str] = None
    shared_at: Optional[datetime] = None
    error_message: Optional[str] = None


# --------------------------------------------------------------------------- #
# Community Manager IA
# --------------------------------------------------------------------------- #

COMMUNITY_MANAGER_TONES = [
    "professional", "inspirational", "casual", "expert", "motivational", "educational",
]

COMMUNITY_MANAGER_OBJECTIVES = [
    "engagement", "visibility", "brand_awareness", "community_building", "lead_generation",
]

COMMUNITY_MANAGER_THEMES = [
    "running", "recovery", "nutrition", "training", "gear", "mental", "races", "lifestyle",
]

COMMUNITY_MANAGER_NETWORKS = [
    "instagram", "facebook", "linkedin", "twitter", "threads",
]

CALENDAR_ENTRY_STATUSES = [
    "brouillon", "planifié", "publié", "refusé",
    "pending", "accepted", "refused", "published",
]


class CommunityManagerStrategyBase(BaseModel):
    brand_identity: Optional[str] = Field(None, max_length=200)
    tone: list[str] = Field(default_factory=list)
    target_audience: Optional[str] = Field(None, max_length=1000)
    objectives: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    frequency: int = Field(3, ge=1, le=14)
    networks: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    forbidden_topics: list[str] = Field(default_factory=list)


class CommunityManagerStrategyCreate(CommunityManagerStrategyBase):
    pass


class CommunityManagerStrategyUpdate(CommunityManagerStrategyBase):
    brand_identity: Optional[str] = Field(None, max_length=200)
    tone: Optional[list[str]] = None
    target_audience: Optional[str] = Field(None, max_length=1000)
    objectives: Optional[list[str]] = None
    themes: Optional[list[str]] = None
    frequency: Optional[int] = Field(None, ge=1, le=14)
    networks: Optional[list[str]] = None
    rules: Optional[list[str]] = None
    forbidden_topics: Optional[list[str]] = None


class CommunityManagerStrategyResponse(CommunityManagerStrategyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    created_at: datetime
    updated_at: datetime


class EditorialCalendarEntryBase(BaseModel):
    date: date
    topic: str = Field(..., min_length=1, max_length=500)
    theme: Optional[str] = Field(None, max_length=100, pattern="^(running|recovery|nutrition|training|gear|mental|races|lifestyle)$")
    objective: Optional[str] = Field(None, max_length=100, pattern="^(engagement|visibility|brand_awareness|community_building|lead_generation)$")
    notes: Optional[str] = Field(None, max_length=2000)
    hashtags: Optional[str] = Field(None, max_length=500)
    status: str = Field("brouillon", max_length=30, pattern="^(brouillon|planifié|publié|refusé|pending|accepted|refused|published)$")


class EditorialCalendarEntryCreate(EditorialCalendarEntryBase):
    pass


class EditorialCalendarEntryUpdate(BaseModel):
    date: Optional[date] = None
    topic: Optional[str] = Field(None, min_length=1, max_length=500)
    theme: Optional[str] = Field(None, max_length=100, pattern="^(running|recovery|nutrition|training|gear|mental|races|lifestyle)$")
    objective: Optional[str] = Field(None, max_length=100, pattern="^(engagement|visibility|brand_awareness|community_building|lead_generation)$")
    notes: Optional[str] = Field(None, max_length=2000)
    hashtags: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, max_length=30, pattern="^(brouillon|planifié|publié|refusé|pending|accepted|refused|published)$")


class EditorialCalendarEntryResponse(EditorialCalendarEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    created_at: datetime
    updated_at: datetime
    publication_id: Optional[int] = None
    publication_status: Optional[str] = None


class CalendarGenerateRequest(BaseModel):
    count: int = Field(5, ge=1, le=20)


class CalendarGenerateResponse(BaseModel):
    calendar: list[EditorialCalendarEntryResponse]

