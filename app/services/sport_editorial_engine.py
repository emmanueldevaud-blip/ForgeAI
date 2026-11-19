"""Moteur métier éditorial sportif V2.

Ce module reste indépendant d'Instagram, Facebook et du renderer. Il produit
un brief éditorial déterministe à partir des données réellement disponibles;
la génération IA existante peut ensuite l'utiliser comme contexte.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable

from app.services.community_manager.hashtags import DEFAULT_BRAND_HASHTAG


@dataclass(frozen=True)
class ActivityEditorialAnalysis:
    activity_type: str
    distance_km: float | None
    duration_seconds: int | None
    elevation_gain_m: float | None
    pace_sec_km: float | None
    location: str | None
    characteristics: tuple[str, ...]
    confidence: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"characteristics": list(self.characteristics)}


@dataclass(frozen=True)
class EditorialDirection:
    primary: str
    secondary: str | None
    template: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _metadata(activity: Any) -> dict[str, Any]:
    raw = getattr(activity, "metadata_json", None)
    return raw if isinstance(raw, dict) else {}


def _location(activity: Any) -> str | None:
    meta = _metadata(activity)
    for key in ("location", "place", "city", "locality", "municipality"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    summary = meta.get("garmin_summary")
    if isinstance(summary, dict):
        for key in ("locationName", "city", "location"):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def analyze_activity(activity: Any) -> ActivityEditorialAnalysis:
    """Analyse une activité sans déduire de faits absents des données."""
    distance_m = _number(getattr(activity, "distance_m", None))
    distance = distance_m / 1000 if distance_m is not None else None
    duration = getattr(activity, "duration_seconds", None) or None
    elevation = _number(getattr(activity, "elevation_gain_m", None))
    pace = _number(getattr(activity, "avg_pace_sec_km", None))
    activity_type = str(getattr(activity, "sport_type", None) or "other")
    characteristics: list[str] = []
    if distance is not None:
        if distance >= 25:
            characteristics.append("sortie_longue")
        elif distance <= 8:
            characteristics.append("sortie_courte")
    if elevation is not None:
        if elevation >= 1000:
            characteristics.append("fort_denivele")
        elif elevation >= 500:
            characteristics.append("sortie montagne")
    if duration and distance is not None and distance > 0 and duration / 3600 >= 2.5:
        characteristics.append("endurance")
    if not characteristics:
        characteristics.append("sortie_reguliere")
    available = sum(value is not None for value in (distance, duration, elevation, pace))
    confidence = "high" if available >= 3 else "medium" if available >= 2 else "low"
    return ActivityEditorialAnalysis(
        activity_type=activity_type,
        distance_km=round(distance, 2) if distance is not None else None,
        duration_seconds=int(duration) if duration is not None else None,
        elevation_gain_m=round(elevation, 1) if elevation is not None else None,
        pace_sec_km=round(pace, 1) if pace is not None else None,
        location=_location(activity),
        characteristics=tuple(characteristics),
        confidence=confidence,
    )


def choose_direction(analysis: ActivityEditorialAnalysis, photo_count: int = 0) -> EditorialDirection:
    """Choisit une direction stable et explicable, sans aléatoire opaque."""
    chars = set(analysis.characteristics)
    if "sortie_courte" in chars:
        return EditorialDirection("humour", "performance", "quick-stats", "sortie courte")
    if "fort_denivele" in chars or "sortie montagne" in chars:
        return EditorialDirection("aventure", "performance", "mountain-card", "dénivelé significatif")
    if "sortie_longue" in chars or "endurance" in chars:
        return EditorialDirection("performance", "humour", "stats-reel", "distance ou durée importante")
    if photo_count >= 3:
        return EditorialDirection("aventure", "souvenir", "story-carousel", "plusieurs photos disponibles")
    return EditorialDirection("souvenir", None, "clean-photo", "données ou contexte limités")


def build_hashtags(analysis: ActivityEditorialAnalysis) -> list[str]:
    """Retourne au maximum deux hashtags contextuels + la signature."""
    context: list[str] = []
    if analysis.activity_type in {"trail_running", "trailrunning", "trail"}:
        context.append("#TrailRunning")
    elif analysis.activity_type not in {"other", ""}:
        context.append("#Running")
    if "fort_denivele" in analysis.characteristics or "sortie montagne" in analysis.characteristics:
        context.append("#MountainRunning")
    elif analysis.location:
        context.append(f"#{''.join(part.capitalize() for part in analysis.location.split())}")
    return context[:2] + [DEFAULT_BRAND_HASHTAG]


def editorial_memory(publications: Iterable[Any], limit: int = 12) -> dict[str, list[str]]:
    """Extrait une mémoire légère depuis les publications existantes."""
    titles: list[str] = []
    captions: list[str] = []
    styles: list[str] = []
    for publication in list(publications)[:limit]:
        if getattr(publication, "title", None):
            titles.append(str(publication.title))
        if getattr(publication, "content", None):
            captions.append(str(publication.content)[:240])
        design = getattr(publication, "design", None)
        if isinstance(design, dict) and design.get("editorial_engine", {}).get("style"):
            styles.append(str(design["editorial_engine"]["style"]))
    return {"titles": titles, "captions": captions, "styles": styles}


def build_editorial_brief(activity: Any, photo_count: int = 0, recent_publications: Iterable[Any] = ()) -> dict[str, Any]:
    analysis = analyze_activity(activity)
    direction = choose_direction(analysis, photo_count)
    return {
        "analysis": analysis.as_dict(),
        "direction": direction.as_dict(),
        "hashtags": build_hashtags(analysis),
        "photo_count": photo_count,
        "memory": editorial_memory(recent_publications),
    }
