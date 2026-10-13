"""Reverse-geocoding des lieux photos (opt-in, cache en base).

Les photos sont associées à une ``PhotoPlace`` (cellule GPS de 0,01°)
lors de l'ingest, avec un ``label`` vide. Ce module résout le label via
l'API Nominatim (OpenStreetMap) **en arrière-plan uniquement** (job
``place_geocode``), jamais dans le chemin HTTP ni pendant l'import.

Politique de usage respectée :

- 1 requête/seconde (``MIN_REQUEST_INTERVAL_SECONDS``) ;
- un seul appel par cellule GPS : le résultat (``label``, ``country``,
  ``source="nominatim"``, ``resolved_at``) est caché en base ;
- un lieu sans résultat (océan, zone inconnue) est marqué
  ``resolved_at`` avec un label vide : il n'est jamais retenté ;
- une erreur réseau échoue le job (retry avec backoff du mécanisme
  existant), les lieux déjà résolus restent acquis (commit par lieu).

Opt-in : tout est un no-op si ``PHOTO_GEOCODING_ENABLED`` est désactivé
aucun octet ne sort du serveur par défaut).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import PhotoPlace

logger = logging.getLogger(__name__)

# Cadence maximale imposée par la politique d'usage de Nominatim.
MIN_REQUEST_INTERVAL_SECONDS = 1.0

_last_request_at = 0.0
_rate_lock = asyncio.Lock()

# Clés d'adresse Nominatim (jsonv2), de la plus locale à la plus large :
# le label d'une cellule ~1 km est d'abord la commune.
_ADDRESS_LABEL_KEYS = (
    "city",
    "town",
    "village",
    "hamlet",
    "municipality",
    "suburb",
    "neighbourhood",
    "county",
    "state",
    "country",
)


class GeocodeError(Exception):
    """Erreur réseau/API lors du reverse-geocoding (retryable)."""


def _build_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        timeout=settings.PHOTO_GEOCODING_TIMEOUT,
        follow_redirects=True,
        headers={
            "User-Agent": "ForgeAI-PhotoGeocoding/1.0 (module photos, reverse geocoding)",
        },
    )


async def _throttle() -> None:
    """Espace les requêtes sortantes à au moins 1/s (verrou partagé)."""
    global _last_request_at
    async with _rate_lock:
        now = time.monotonic()
        wait = _last_request_at + MIN_REQUEST_INTERVAL_SECONDS - now
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


def build_label(address: dict[str, Any]) -> str | None:
    """Construit un label court (≤ 200 caractères) depuis une adresse Nominatim."""
    for key in _ADDRESS_LABEL_KEYS:
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return None


async def reverse_geocode(lat: float, lon: float) -> tuple[str | None, str | None] | None:
    """Reverse-geocode une coordonnée → ``(label, country)`` ou ``None``.

    Retourne ``None`` si le géocodage est désactivé ou si l'API ne renvoie
    aucune adresse (océan, zone inconnue) — dans ce cas l'appelant marque
    le lieu comme traité pour ne jamais retenter. Les erreurs réseau lèvent
    ``GeocodeError`` (retryable par le mécanisme de jobs).
    """
    settings = get_settings()
    if not settings.PHOTO_GEOCODING_ENABLED:
        return None
    url = f"{settings.PHOTO_GEOCODING_NOMINATIM_URL.rstrip('/')}/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "accept-language": settings.PHOTO_GEOCODING_LANGUAGE,
    }
    await _throttle()
    try:
        async with _build_client() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        # 4xx Nominatim (requête malformée, quota) : pas de retry ciblé
        # possible sur la même requête — traitée comme une absence de résultat
        # côté 404, re-montée sinon.
        if exc.response.status_code == 404:
            return None
        raise GeocodeError(f"Nominatim HTTP {exc.response.status_code}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise GeocodeError(f"Nominatim injoignable: {exc}") from exc

    if not isinstance(data, dict):
        return None
    address = data.get("address")
    if not isinstance(address, dict):
        return None
    label = build_label(address)
    country = address.get("country")
    if not isinstance(country, str) or not country.strip():
        country = None
    if label is None and country is None:
        return None
    return label, (country.strip() if country else None)


async def count_pending_places(db: AsyncSession) -> int:
    """Lieux jamais résolus (label vide et resolved_at nul)."""
    result = await db.execute(
        select(func.count())
        .select_from(PhotoPlace)
        .where(PhotoPlace.label == "", PhotoPlace.resolved_at.is_(None))
    )
    return int(result.scalar_one())


async def resolve_pending_places(db: AsyncSession, *, limit: int) -> tuple[int, int]:
    """Résout les lieux en attente (par lot, cadence 1 req/s).

    Retourne ``(résolus, restants)``. Chaque lieu est validé par un commit
    individuel : un plantage réseau plus loin dans le lot ne perd pas le
    travail déjà fait. Les échecs réseau lèvent ``GeocodeError`` (le job est
    rejoué avec backoff).
    """
    settings = get_settings()
    if not settings.PHOTO_GEOCODING_ENABLED:
        return 0, 0
    result = await db.execute(
        select(PhotoPlace)
        .where(PhotoPlace.label == "", PhotoPlace.resolved_at.is_(None))
        .order_by(PhotoPlace.id)
        .limit(limit)
    )
    places = list(result.scalars().all())
    resolved = 0
    for place in places:
        outcome = await reverse_geocode(place.lat_cell, place.lon_cell)
        # Marquage « traité » même sans résultat (océan…) : jamais retenté.
        place.source = "nominatim"
        place.resolved_at = datetime.now(UTC).replace(tzinfo=None)
        if outcome is not None:
            place.label = outcome[0] or ""
            place.country = outcome[1]
            resolved += 1
        else:
            logger.info(
                "[PHOTO-GEOCOD] lieu=%s (%s, %s): aucune adresse",
                place.id, place.lat_cell, place.lon_cell,
            )
        await db.commit()
    remaining = await count_pending_places(db)
    return resolved, remaining
