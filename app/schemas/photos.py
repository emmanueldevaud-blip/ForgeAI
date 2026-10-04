"""Schémas Pydantic du module Photos."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MessageResponse(BaseModel):
    message: str


# ================================ Photos ================================

class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: Optional[str] = None
    original_filename: str
    mime_type: str
    byte_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    taken_at: datetime
    imported_at: datetime
    is_favorite: bool
    status: str
    analysis_status: str
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    is_deleted: bool = False


class PhotoUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    is_favorite: Optional[bool] = None


class PhotoListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(100, ge=1, le=500)
    search: Optional[str] = Field(None, max_length=255)
    favorite: Optional[bool] = None
    album_id: Optional[int] = None
    person_id: Optional[int] = None
    tag: Optional[str] = Field(None, max_length=120)
    place_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    include_deleted: bool = False
    # Curseur opaque (tri taken_at décroissant) pour l'infinite scroll.
    cursor: Optional[str] = Field(None, max_length=200)
    sort_by: str = Field("taken_at", max_length=50)
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


class PhotoListResponse(BaseModel):
    items: List[PhotoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    next_cursor: Optional[str] = None


class PhotoTagLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    category: Optional[str] = None
    source: str = "manual"


class PhotoEditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int
    kind: str
    name: Optional[str] = None
    params_json: Optional[dict] = None
    width: int
    height: int
    byte_size: int
    status: str
    is_active: bool
    created_at: datetime


class PhotoPlaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    country: Optional[str] = None
    lat_cell: float
    lon_cell: float
    photo_count: int = 0


class PhotoDetailResponse(PhotoResponse):
    exif_json: Optional[dict] = None
    place: Optional[PhotoPlaceResponse] = None
    tags: List[PhotoTagLinkResponse] = []
    album_ids: List[int] = []
    edits: List[PhotoEditResponse] = []
    face_count: int = 0
    analysis_status_detail: Optional[str] = None


class PhotoUploadResponse(BaseModel):
    items: List[PhotoResponse]
    errors: List[dict] = []


# ================================ Albums ================================

class PhotoAlbumCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=2000)


class PhotoAlbumUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=2000)
    cover_photo_id: Optional[int] = None


class PhotoAlbumResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    description: Optional[str] = None
    cover_photo_id: Optional[int] = None
    photo_count: int = 0
    created_at: datetime
    updated_at: datetime


class PhotoAlbumListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)
    search: Optional[str] = Field(None, max_length=255)


class PhotoAlbumListResponse(BaseModel):
    items: List[PhotoAlbumResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PhotoAlbumPhotosRequest(BaseModel):
    photo_ids: List[int] = Field(..., min_length=1, max_length=500)


# ================================ Personnes ================================

class PhotoPersonCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)


class PhotoPersonUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    # Visage de couverture du groupe (None = effacer ; absent = inchangé,
    # géré via exclude_unset côté endpoint).
    cover_face_id: Optional[int] = None


class PhotoPersonMerge(BaseModel):
    """Fusion : la personne ``person_id`` (source) est absorbée par la cible."""

    person_id: int


class PhotoPersonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    cover_face_id: Optional[int] = None
    # Compteurs calculés dynamiquement (pas de colonne dénormalisée).
    face_count: int = 0
    photo_count: int = 0
    created_at: datetime


class PhotoPersonListResponse(BaseModel):
    items: List[PhotoPersonResponse]
    total: int


class PhotoFaceUpdate(BaseModel):
    person_id: Optional[int] = None


class PhotoFaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int
    person_id: Optional[int] = None
    x: float
    y: float
    w: float
    h: float
    confidence: float


class PhotoFaceListResponse(BaseModel):
    """Visages d'une personne (grille des groupes / désaffectation)."""

    items: List[PhotoFaceResponse]
    total: int


# ================================ Tags / lieux ================================

class PhotoTagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = Field(None, max_length=50)


class PhotoTagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    category: Optional[str] = None
    photo_count: int = 0


class PhotoTagListResponse(BaseModel):
    items: List[PhotoTagResponse]
    total: int


class PhotoPlaceListResponse(BaseModel):
    items: List[PhotoPlaceResponse]
    total: int


# ================================ Recherche ================================

class PhotoSearchParams(BaseModel):
    q: str = Field("", max_length=500)
    page: int = Field(1, ge=1)
    page_size: int = Field(100, ge=1, le=500)
    favorite: Optional[bool] = None
    album_id: Optional[int] = None
    person_id: Optional[int] = None
    place_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    cursor: Optional[str] = Field(None, max_length=200)


# ================================ Photos similaires ================================

class PhotoSimilarItem(BaseModel):
    photo: PhotoResponse
    score: float


class PhotoSimilarResponse(BaseModel):
    items: List[PhotoSimilarItem] = []
    # False = la photo source n'a pas (encore) d'embedding : ré-indexer.
    indexed: bool = False
    provider: Optional[str] = None


# ================================ Retouche ================================

class PhotoEditCreate(BaseModel):
    # rotate | crop | adjust | auto_enhance | ai_remove | ai_upscale | ai_restore
    kind: str = Field(..., pattern="^(rotate|crop|adjust|auto_enhance|ai_remove|ai_upscale|ai_restore)$")
    name: Optional[str] = Field(None, max_length=150)
    params: Optional[dict] = None


# ================================ Jobs ================================

class PhotoJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    photo_id: Optional[int] = None
    type: str
    status: str
    attempts: int
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class PhotoAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int
    kind: str
    status: str
    result_json: Optional[dict] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    version: int = 1
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class PhotoDuplicateGroup(BaseModel):
    content_hash: str
    count: int
    photo_ids: List[int]


class PhotoDuplicateListResponse(BaseModel):
    groups: List[PhotoDuplicateGroup]
    total: int


# ================================ Stockage (V3) ================================

class PhotoScanRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    backend: str
    state: str
    detail: Optional[str] = None
    files_seen: int
    created: int
    updated_paths: int
    missing_marked: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class PhotoStorageStatusResponse(BaseModel):
    backend: str
    path: str
    state: str
    detail: str
    backends: List[str]
    scan_enabled: bool
    scan_interval_seconds: int
    last_scan: Optional[PhotoScanRunResponse] = None


class PhotoThumbnailRebuildResponse(BaseModel):
    queued: int
    message: str


class PhotoScanQueuedResponse(BaseModel):
    queued: bool
    job_id: Optional[str] = None
    message: str
