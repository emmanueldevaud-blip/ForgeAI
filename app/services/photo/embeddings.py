"""Embeddings image pour la recherche de photos similaires.

Le pipeline ne connaît que le protocol ``EmbeddingProvider`` (name, model,
version, dimensions) : remplacer le provider local par un modèle externe ne
change ni les jobs ni la table ``photo_embeddings`` (ré-indexation
automatique quand provider / model / version changent).

Stockage : JSON dans la base applicative (voir docs/photos.md) — MySQL 8.4
n'a pas de type vector, aucune base vectorielle n'est introduite. Le calcul
de similarité (cosinus) se fait en Python, en streaming, sur les vecteurs du
propriétaire courant : suffisant à l'échelle d'une photothèque personnelle.

Confidentialité : le provider par défaut ``local_grid`` est 100 % local,
aucun octet ne sort du serveur.
"""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo, PhotoEmbedding
from app.services.photo.analysis import resolve_analysis_image

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    """Contrat d'un producteur d'embedding image."""

    name: str
    model: str
    version: int
    dimensions: int

    async def embed_image(self, image_path: Path) -> list[float]:
        """Retourne un vecteur normalisé (norme L2 = 1)."""
        ...


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    return [value / norm for value in vector]


class LocalGridEmbedding:
    """Grille 16×16 RGB aplatie (768 dims), normalisée L2.

    Color histogramme sous-jacente : local, déterministe, aucun modèle ni
    dépendance. Suffisant pour un premier rang de « photos similaires » ;
    un modèle CLIP-like pourra être branché ici sans toucher au pipeline.
    """

    name = "local_grid"
    model = "grid-16x16-rgb"
    version = 1
    dimensions = 16 * 16 * 3

    async def embed_image(self, image_path: Path) -> list[float]:
        return await asyncio.to_thread(self._embed_sync, image_path)

    def _embed_sync(self, image_path: Path) -> list[float]:
        from PIL import Image, ImageOps

        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            grid = image.resize((16, 16), Image.Resampling.BOX)
            # RGB : 3 octets par pixel (pas de dépréciation Image.getdata).
            vector = [channel / 255.0 for channel in grid.tobytes()]
        return l2_normalize(vector)


_PROVIDERS: dict[str, EmbeddingProvider] = {
    LocalGridEmbedding.name: LocalGridEmbedding(),
}


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    configured = name or get_settings().PHOTO_EMBEDDING_PROVIDER
    return _PROVIDERS.get(configured) or _PROVIDERS[LocalGridEmbedding.name]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosinus sans allocation de vecteur intermédiaire."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for value_a, value_b in zip(a, b):
        dot += value_a * value_b
        norm_a += value_a * value_a
        norm_b += value_b * value_b
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def _upsert_vector(
    db: AsyncSession,
    photo_id: int,
    provider: EmbeddingProvider,
    vector: list[float],
    row: PhotoEmbedding | None,
) -> PhotoEmbedding:
    """Insert ou remplace le vecteur de la photo (portable SQLite / MySQL)."""
    if row is None:
        row = PhotoEmbedding(
            photo_id=photo_id,
            provider=provider.name,
            model=provider.model,
            version=provider.version,
            dimensions=len(vector),
            vector_json=vector,
        )
        db.add(row)
    else:
        row.provider = provider.name
        row.model = provider.model
        row.version = provider.version
        row.dimensions = len(vector)
        row.vector_json = vector
    return row


def is_up_to_date(row: PhotoEmbedding | None, provider: EmbeddingProvider) -> bool:
    """True si la ligne indexée correspond au provider courant (pas de ré-indexation)."""
    if row is None:
        return False
    return (
        row.provider == provider.name
        and row.model == provider.model
        and row.version == provider.version
    )


async def run_embedding(
    db: AsyncSession, photo: Photo, *, force: bool = False
) -> PhotoEmbedding | None:
    """Calcule (ou recalcule) l'embedding de ``photo`` et le persiste.

    Un embedding déjà à jour est conservé tel quel sauf ``force=True``
    (ré-indexation demandée explicitement).
    """
    settings = get_settings()
    if not settings.PHOTO_EMBEDDING_ENABLED:
        return None
    provider = get_embedding_provider()
    existing = await db.get(PhotoEmbedding, photo.id)
    if not force and is_up_to_date(existing, provider):
        return existing

    image_path = await resolve_analysis_image(db, photo)
    vector = await provider.embed_image(image_path)
    _upsert_vector(db, photo.id, provider, vector, existing)
    await db.commit()
    logger.info(
        "[PHOTO-EMBED] photo=%s provider=%s model=%s v%s dims=%s",
        photo.id,
        provider.name,
        provider.model,
        provider.version,
        len(vector),
    )
    return await db.get(PhotoEmbedding, photo.id)


async def find_similar_embeddings(
    db: AsyncSession, photo: Photo, limit: int = 12
) -> tuple[list[tuple[int, float]], bool, str | None]:
    """Photos les plus proches de ``photo`` (cosinus), scopées au propriétaire.

    Retourne ``( [(photo_id, score), ...], photo indexée, provider )``.
    """
    source = await db.get(PhotoEmbedding, photo.id)
    if source is None:
        return [], False, None
    result = await db.execute(
        select(PhotoEmbedding.photo_id, PhotoEmbedding.vector_json)
        .join(Photo, Photo.id == PhotoEmbedding.photo_id)
        .where(
            Photo.owner_id == photo.owner_id,
            Photo.is_deleted.is_(False),
            PhotoEmbedding.photo_id != photo.id,
        )
    )
    reference = list(source.vector_json or [])
    scored: list[tuple[int, float]] = []
    for candidate_id, vector in result.all():
        score = cosine_similarity(reference, list(vector or []))
        if score > 0.0:
            scored.append((candidate_id, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit], True, source.provider
