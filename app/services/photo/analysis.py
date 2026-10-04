"""Pipeline d'analyse IA des photos.

L'analyseur est pluggable : le pipeline (jobs, tags, table ``photo_analyses``)
reste identique quel que soit le moteur utilisé.

Moteurs prévus :
- ``metadata``    : analyseur local sans modèle (implémenté) — tags objectifs
                    déduits des métadonnées (portrait/paysage, nuit, GPS...).
- ``local_vision``: modèle local (classification/détection) — à ajouter ici.
- ``llm_vision``  : modèle vision via l'AI Gateway — à ajouter ici sans
                    toucher au gateway existant (voir docs/photos.md).

Aucun de ces moteurs ne bloque l'affichage de la galerie : l'analyse est
toujours exécutée par un job d'arrière-plan.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from datetime import datetime, time
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo, PhotoAnalysis, PhotoTag, PhotoTagLink

logger = logging.getLogger(__name__)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    cleaned = "".join(c if c.isalnum() else "-" for c in without_accents)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "tag"


class PhotoAnalysisProvider(Protocol):
    """Contrat d'un moteur d'analyse photo.

    ``model`` / ``version`` alimentent la table ``photo_analyses`` :
    quand ils changent, la photo est ré-analysée (ré-indexation).
    """

    name: str
    model: str
    version: int

    async def analyze(self, photo: Photo, image_path) -> dict[str, Any]:
        """Retourne {"tags": [{"name", "category", "confidence"}], "result": {...}}."""
        ...


# Alias historique conservé pour les imports existants.
PhotoAnalyzer = PhotoAnalysisProvider


class MetadataAnalyzer:
    """Analyseur local de base : tags objectifs issus des métadonnées.

    Ne nécessite aucun modèle externe — sert de filet de sécurité et de
    source de tags pour la recherche tant que les analyseurs visuels ne sont
    pas installés.
    """

    name = "metadata"
    model = "metadata-rules"
    version = 1

    async def analyze(self, photo: Photo, image_path) -> dict[str, Any]:
        return await asyncio.to_thread(self._analyze_sync, photo)

    @staticmethod
    def _analyze_sync(photo: Photo) -> dict[str, Any]:
        tags: list[dict[str, Any]] = []
        result: dict[str, Any] = {}

        if photo.width and photo.height:
            if photo.height > photo.width:
                tags.append({"name": "portrait", "category": "metadata", "confidence": 1.0})
            else:
                tags.append({"name": "paysage", "category": "metadata", "confidence": 1.0})

        if photo.gps_latitude is not None and photo.gps_longitude is not None:
            tags.append({"name": "avec gps", "category": "metadata", "confidence": 1.0})

        if photo.taken_at:
            local_time = photo.taken_at.time()
            if local_time >= time(22, 0) or local_time <= time(5, 0):
                tags.append({"name": "nuit", "category": "scene", "confidence": 0.6})
                result["night"] = True

        if photo.camera_model:
            tags.append(
                {"name": photo.camera_model, "category": "metadata", "confidence": 1.0}
            )

        result["width"] = photo.width
        result["height"] = photo.height
        return {"tags": tags, "result": result}


_ANALYZERS: dict[str, PhotoAnalyzer] = {
    MetadataAnalyzer.name: MetadataAnalyzer(),
}


def get_analyzer(name: str | None = None) -> PhotoAnalyzer:
    configured = name or get_settings().PHOTO_ANALYZER
    return _ANALYZERS.get(configured) or _ANALYZERS["metadata"]


async def get_or_create_tag(
    db: AsyncSession, owner_id: int, name: str, category: str | None = None
) -> PhotoTag:
    slug = slugify(name)
    result = await db.execute(
        select(PhotoTag).where(PhotoTag.owner_id == owner_id, PhotoTag.slug == slug)
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = PhotoTag(owner_id=owner_id, name=name.strip(), slug=slug, category=category)
        db.add(tag)
        await db.flush()
    elif category and not tag.category:
        tag.category = category
    return tag


async def link_tag(
    db: AsyncSession,
    photo: Photo,
    tag: PhotoTag,
    *,
    confidence: float = 1.0,
    source: str = "analysis",
) -> None:
    exists = await db.execute(
        select(PhotoTagLink).where(
            PhotoTagLink.photo_id == photo.id, PhotoTagLink.tag_id == tag.id
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(
            PhotoTagLink(
                photo_id=photo.id,
                tag_id=tag.id,
                confidence=confidence,
                source=source,
            )
        )


async def resolve_analysis_image(db: AsyncSession, photo: Photo):
    """Chemin de l'image à analyser : la miniature configurée, sinon l'original.

    Le pipeline d'analyse travaille sur une miniature (performance) — jamais
    besoin de décoder un original de plusieurs mégapixels.
    """
    from app.models.photo import PhotoThumbnail
    from app.services.photo.storage import get_photo_storage

    settings = get_settings()
    size = settings.PHOTO_ANALYSIS_THUMB_SIZE
    thumb = (
        await db.execute(
            select(PhotoThumbnail).where(
                PhotoThumbnail.photo_id == photo.id, PhotoThumbnail.size == size
            )
        )
    ).scalar_one_or_none()
    storage = get_photo_storage()
    if thumb is not None:
        path = storage.thumbnail_path(thumb.storage_path)
        if path.is_file():
            return path
    return storage.backend_for_photo(photo).original_path(photo.storage_path)


async def run_analysis(db: AsyncSession, photo: Photo) -> PhotoAnalysis:
    """Exécute l'analyseur configuré et persiste tags + résultat.

    Une seule ligne ``photo_analyses`` par photo (ré-utilisée à chaque
    ré-analyse) : la table sert d'index d'état (provider / model / version /
    completed_at), pas d'historique. Toute erreur est consignée dans la ligne
    sans faire échouer le reste du pipeline — c'est l'appelant (le job) qui
    décide de réessayer.
    """
    analyzer = get_analyzer()

    existing = (
        await db.execute(
            select(PhotoAnalysis).where(
                PhotoAnalysis.photo_id == photo.id,
                PhotoAnalysis.kind == "classification",
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = PhotoAnalysis(
            photo_id=photo.id, kind="classification", status="pending"
        )
        db.add(existing)
    analysis = existing
    analysis.status = "running"
    analysis.provider = analyzer.name
    analysis.model = getattr(analyzer, "model", None)
    analysis.version = getattr(analyzer, "version", 1)
    analysis.error = None
    photo.analysis_status = "running"
    await db.commit()

    try:
        image_path = await resolve_analysis_image(db, photo)
        payload = await analyzer.analyze(photo, image_path)
        result = dict(payload.get("result") or {})
        if get_settings().PHOTO_QUALITY_ENABLED:
            try:
                from app.services.photo.quality import assess_quality

                quality = await asyncio.to_thread(assess_quality, image_path)
                result["quality"] = quality
            except Exception:  # noqa: BLE001 - la qualité ne casse jamais l'analyse
                logger.exception(
                    "[PHOTO] score de qualité indisponible photo_id=%s", photo.id
                )
        for tag_spec in payload.get("tags", []):
            name = str(tag_spec.get("name") or "").strip()
            if not name:
                continue
            tag = await get_or_create_tag(
                db, photo.owner_id, name, tag_spec.get("category")
            )
            await link_tag(
                db,
                photo,
                tag,
                confidence=float(tag_spec.get("confidence", 1.0)),
                source=analyzer.name,
            )
        analysis.status = "done"
        analysis.result_json = result
        photo.analysis_status = "done"
        photo.error = None
    except Exception as exc:  # noqa: BLE001 - l'analyse ne doit pas casser la galerie
        logger.exception("[PHOTO] analyse échouée photo_id=%s", photo.id)
        analysis.status = "failed"
        analysis.error = f"{type(exc).__name__}: {exc}"
        photo.analysis_status = "failed"
    analysis.completed_at = datetime.now()
    await db.commit()
    await db.refresh(analysis)
    return analysis
