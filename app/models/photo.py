"""Modeles du module Photos (gestionnaire de photos personnelles).

Hiérarchie logique du stockage :

    original  ->  métadonnées (EXIF)  ->  miniatures  ->  analyse IA  ->  retouches/versions

L'original est conservé tel quel et n'est jamais modifié : chaque retouche
produit une nouvelle ``PhotoEdit`` (version dérivée).
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid4())


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    # Chemin relatif au stockage d'originaux (jamais d'absolu en base).
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # Backend d'originaux de CETTE photo : "local" | "nas" (V3). La lecture
    # doit suivre la colonne, pas la configuration courante, sinon changer
    # le backend casserait l'accès aux photos existantes.
    storage_backend: Mapped[str] = mapped_column(
        String(20), default="local", server_default="local", nullable=False
    )
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # BigInteger : une vidéo peut dépasser 2 Go (max INT = 2 147 483 647).
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Clé de tri / regroupement : EXIF DateTimeOriginal, sinon date du fichier,
    # sinon date d'import. Jamais NULL pour un tri stable.
    taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gps_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_places.id", ondelete="SET NULL"), nullable=True, index=True
    )
    camera_make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    camera_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exif_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Suppression logique : la galerie masque, rien n'est écrasé sans confirmation.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # pending | ready | failed (import / miniatures)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending | running | done | failed | skipped (analyse IA)
    analysis_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # selectin (et non lazy) : un accès différé à ``place`` lèverait
    # MissingGreenlet en session async (500 sur le détail d'une photo GPS).
    place: Mapped["PhotoPlace | None"] = relationship(
        "PhotoPlace", back_populates="photos", lazy="selectin"
    )
    thumbnails: Mapped[list["PhotoThumbnail"]] = relationship(
        "PhotoThumbnail", back_populates="photo", cascade="all, delete-orphan"
    )
    album_items: Mapped[list["PhotoAlbumItem"]] = relationship(
        "PhotoAlbumItem", back_populates="photo", cascade="all, delete-orphan"
    )
    faces: Mapped[list["PhotoFace"]] = relationship(
        "PhotoFace", back_populates="photo", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["PhotoAnalysis"]] = relationship(
        "PhotoAnalysis", back_populates="photo", cascade="all, delete-orphan"
    )
    edits: Mapped[list["PhotoEdit"]] = relationship(
        "PhotoEdit",
        back_populates="photo",
        cascade="all, delete-orphan",
        foreign_keys="PhotoEdit.photo_id",
    )
    jobs: Mapped[list["PhotoJob"]] = relationship(
        "PhotoJob", back_populates="photo", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_photos_owner_taken", "owner_id", "taken_at"),
        Index("ix_photos_owner_deleted_taken", "owner_id", "is_deleted", "taken_at"),
        Index("ix_photos_owner_hash", "owner_id", "content_hash"),
        Index("ix_photos_owner_favorite", "owner_id", "is_favorite"),
    )


class PhotoThumbnail(Base):
    __tablename__ = "photo_thumbnails"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # tiny | small | medium | large | preview
    size: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    photo: Mapped["Photo"] = relationship("Photo", back_populates="thumbnails")

    __table_args__ = (UniqueConstraint("photo_id", "size", name="uq_photo_thumbnail_size"),)


class PhotoPlace(Base):
    """Cache de résolution des lieux (cellule GPS arrondie)."""

    __tablename__ = "photo_places"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lat_cell: Mapped[float] = mapped_column(Float, nullable=False)
    lon_cell: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="coords")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    photos: Mapped[list["Photo"]] = relationship("Photo", back_populates="place")

    __table_args__ = (
        UniqueConstraint("lat_cell", "lon_cell", name="uq_photo_place_cell"),
    )


class PhotoAlbum(Base):
    __tablename__ = "photo_albums"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_photo_id: Mapped[int | None] = mapped_column(
        ForeignKey("photos.id", ondelete="SET NULL"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[list["PhotoAlbumItem"]] = relationship(
        "PhotoAlbumItem", back_populates="album", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_photo_album_owner_name"),
    )


class PhotoAlbumItem(Base):
    __tablename__ = "photo_album_items"

    album_id: Mapped[int] = mapped_column(
        ForeignKey("photo_albums.id", ondelete="CASCADE"), primary_key=True
    )
    # index séparé : la PK (album_id, photo_id) ne peut pas servir les
    # recherches par photo_id (détail d'une photo → ses albums).
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    album: Mapped["PhotoAlbum"] = relationship("PhotoAlbum", back_populates="items")
    photo: Mapped["Photo"] = relationship("Photo", back_populates="album_items")


class PhotoPerson(Base):
    """Groupe de visages identifié par l'utilisateur (« Personne 1 », « Manu »...).

    Les groupes créés automatiquement portent un nom auto généré
    (« Personne N ») : l'anonymat est matérialisé par ce préfixe, le nom
    reste NOT NULL pour conserver l'unicité (owner_id, name).
    Les compteurs de visages/photos sont calculés dynamiquement (jamais
    dénormalisés) pour rester justes après suppression de photo.
    """

    __tablename__ = "photo_people"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Visage de couverture (cadrage affiché dans la grille des personnes).
    cover_face_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_faces.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Pas de cascade ORM : la suppression d'une personne DÉSASSOCIE ses
    # visages (person_id = NULL, défaut applicatif + ON DELETE SET NULL en
    # base) — les détections sont conservées, seul le lien change.
    # foreign_keys explicites : le cycle cover_face_id / person_id rend
    # l'appariement ambigu pour SQLAlchemy.
    faces: Mapped[list["PhotoFace"]] = relationship(
        "PhotoFace",
        back_populates="person",
        foreign_keys="PhotoFace.person_id",
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_photo_person_owner_name"),
    )


class PhotoFace(Base):
    """Visage détecté sur une photo (boîte normalisée + embedding).

    ``detector`` / ``model`` / ``version`` permettent la ré-indexation :
    quand le détecteur fourni change, la détection est relancée (état
    stocké dans ``photo_analyses`` kind = « faces »).
    L'embedding (vecteur JSON) reste dans la base applicative — données
    sensibles scopées au propriétaire, jamais transmises à l'extérieur.
    """

    __tablename__ = "photo_faces"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_people.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Boîte englobante normalisée (0.0 - 1.0) par rapport à l'image.
    x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    w: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    h: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detector: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Embedding facial (vecteur sérialisé JSON, normalisé L2).
    embedding_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    photo: Mapped["Photo"] = relationship("Photo", back_populates="faces")
    person: Mapped["PhotoPerson | None"] = relationship(
        "PhotoPerson",
        back_populates="faces",
        foreign_keys="[PhotoFace.person_id]",
    )


class PhotoTag(Base):
    __tablename__ = "photo_tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    # classification | object | scene | person | place | manual | metadata
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_photo_tag_owner_slug"),
    )


class PhotoTagLink(Base):
    __tablename__ = "photo_tag_links"

    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("photo_tags.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class PhotoAnalysis(Base):
    __tablename__ = "photo_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # classification | ocr | vision | faces (état de détection des visages)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="classification")
    # pending | running | done | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Version du provider : une ré-analyse est nécessaire quand elle change.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    photo: Mapped["Photo"] = relationship("Photo", back_populates="analyses")


class PhotoEmbedding(Base):
    """Vecteur d'image pour la recherche de photos similaires.

    Une ligne par photo, ré-écrite quand ``provider`` / ``model`` /
    ``version`` changent (ré-indexation). Le vecteur est sérialisé en JSON :
    MySQL 8.4 n'a pas de type vector et aucune base vectorielle n'est
    introduite pour le module Photos.
    """

    __tablename__ = "photo_embeddings"

    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector_json: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    photo: Mapped["Photo"] = relationship("Photo")


class PhotoEdit(Base):
    """Version dérivée d'une photo. ``parent_edit_id`` NULL = basée sur l'original."""

    __tablename__ = "photo_edits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_edit_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_edits.id", ondelete="SET NULL"), nullable=True
    )
    # rotate | crop | adjust | auto_enhance | ai_remove | ai_upscale | ai_restore
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # pending | ready | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    photo: Mapped["Photo"] = relationship(
        "Photo", back_populates="edits", foreign_keys=[photo_id]
    )


class PhotoJob(Base):
    """File de tâches d'arrière-plan du module Photos (ingest, analyse, ...)."""

    __tablename__ = "photo_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    photo_id: Mapped[int | None] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # ingest | analyze | embedding | face_detect | face_embedding | edit | purge
    # | scan_import (V3 : import idempotent d'un répertoire de stockage)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    # pending | running | done | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    photo: Mapped["Photo | None"] = relationship("Photo", back_populates="jobs")

    __table_args__ = (
        Index("ix_photo_jobs_status_available", "status", "available_at"),
    )


class PhotoScanRun(Base):
    """Trace d'un scan/import de stockage (V3) — dernier état affiché dans
    l'interface « Stockage » (dernier scan, fichiers vus, créés, marqués
    manquants)."""

    __tablename__ = "photo_scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    backend: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    # available | unavailable | error | running | interrupted
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    files_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_paths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_marked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_photo_scan_runs_backend_started", "backend", "started_at"),
    )
