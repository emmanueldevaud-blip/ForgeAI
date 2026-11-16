"""Service audio centralisé pour les publications sportives.

Catalogue musical local (/music/*.mp3), sélection intelligente + aléatoire
persistée, configuration audio enrichie stockée dans publication.design["audio"].

Contraintes :
- Les chemins internes (filesystem) ne doivent pas être exposés dans les réponses API.
- Une piste est choisie une seule fois et conservée ; la régénération est explicite.
- Les métadonnées de licence reflètent la réalité (CREDITS.txt / FreePD CC0 1.0).
"""

from __future__ import annotations

import logging
import random
import subprocess
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Racine publique des médias audio servis au frontend (pas de chemin interne)
PUBLIC_MUSIC_URL_PREFIX = "/music"

# Chemins internes candidats (résolution best-effort, jamais exposés)
_MUSIC_DIR_CANDIDATES = [
    Path(__file__).resolve().parents[3] / "src" / "public" / "music",
    Path("/app/src/public/music"),
]

LICENSE_CC0 = "CC0-1.0"
LICENSE_NAME = "CC0 1.0 Universal (Public Domain)"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
LICENSE_SOURCE = "FreePD.com (Kevin MacLeod et contributeurs) / miroir 0lhi/FreePD"
LICENSE_ATTRIBUTION = "Aucune attribution requise (CC0)."


@dataclass(frozen=True)
class TrackInfo:
    track_id: str  # identifiant stable = nom de fichier
    filename: str
    title: str
    artist: str
    duration: float | None  # secondes (indicative)
    mood: str
    tags: tuple[str, ...]
    license: str
    license_name: str
    license_url: str
    source: str
    attribution: str
    available: bool


# Catalogue statique (source de vérité = src/public/music + CREDITS.txt)
_CATALOG: dict[str, TrackInfo] = {
    "lovely-piano.mp3": TrackInfo(
        track_id="lovely-piano.mp3", filename="lovely-piano.mp3",
        title="Lovely Piano Song", artist="Kevin MacLeod / FreePD",
        duration=120.0, mood="calm", tags=("piano", "romance", "doux"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
    "calm-piano.mp3": TrackInfo(
        track_id="calm-piano.mp3", filename="calm-piano.mp3",
        title="Calm Sketch for Piano", artist="Kevin MacLeod / FreePD",
        duration=120.0, mood="calm", tags=("piano", "calme", "zoned"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
    "infinite-peace.mp3": TrackInfo(
        track_id="infinite-peace.mp3", filename="infinite-peace.mp3",
        title="Infinite Peace", artist="Kevin MacLeod / FreePD",
        duration=120.0, mood="calm", tags=("piano", "paisible"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
    "nostalgia-piano.mp3": TrackInfo(
        track_id="nostalgia-piano.mp3", filename="nostalgia-piano.mp3",
        title="Nostalgic Piano", artist="Kevin MacLeod / FreePD",
        duration=120.0, mood="calm", tags=("piano", "nostalgie", "romance"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
    "city-sunshine.mp3": TrackInfo(
        track_id="city-sunshine.mp3", filename="city-sunshine.mp3",
        title="City Sunshine", artist="Kevin MacLeod / FreePD",
        duration=120.0, mood="energetic", tags=("upbeat", "été", "énergie"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
    "happy-ukulele.mp3": TrackInfo(
        track_id="happy-ukulele.mp3", filename="happy-ukulele.mp3",
        title="Happy Whistling Ukulele", artist="Kevin MacLeod / FreePD",
        duration=120.0, mood="energetic", tags=("upbeat", "joyeux", "léger"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
    "nomadic-sunset.mp3": TrackInfo(
        track_id="nomadic-sunset.mp3", filename="nomadic-sunset.mp3",
        title="Nomadic Sunset", artist="Kevin MacLeod / FreePD",
        duration=128.0, mood="calm", tags=("world", "voyage", "aventure"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
    "space-ambience.mp3": TrackInfo(
        track_id="space-ambience.mp3", filename="space-ambience.mp3",
        title="Space Ambience", artist="Kevin MacLeod / FreePD",
        duration=180.0, mood="calm", tags=("electronic", "ambiance", "espace"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
    "mysterious-lights.mp3": TrackInfo(
        track_id="mysterious-lights.mp3", filename="mysterious-lights.mp3",
        title="Mysterious Lights", artist="Kevin MacLeod / FreePD",
        duration=120.0, mood="energetic", tags=("ambiance", "intense", "mystère"),
        license=LICENSE_CC0, license_name=LICENSE_NAME, license_url=LICENSE_URL,
        source=LICENSE_SOURCE, attribution=LICENSE_ATTRIBUTION, available=True,
    ),
}

_ENERGETIC_IDS = [tid for tid, t in _CATALOG.items() if t.mood == "energetic"]
_CALM_IDS = [tid for tid, t in _CATALOG.items() if t.mood == "calm"]
_ALL_IDS = list(_CATALOG.keys())


def resolve_music_dir() -> Optional[Path]:
    for p in _MUSIC_DIR_CANDIDATES:
        try:
            if p.is_dir():
                return p
        except Exception:
            continue
    return None


def resolve_track_path(track_id: str) -> Optional[Path]:
    """Résout le chemin interne d'une piste (usage serveur uniquement, ne pas exposer)."""
    info = _CATALOG.get(track_id)
    if not info:
        return None
    base = resolve_music_dir()
    if not base:
        return None
    path = (base / info.filename).resolve()
    try:
        if not str(path).startswith(str(base.resolve())):
            return None
        if path.is_file():
            return path
    except Exception:
        return None
    return None


def get_track(track_id: str) -> Optional[TrackInfo]:
    return _CATALOG.get(track_id)


def list_tracks() -> list[dict[str, Any]]:
    """Catalogue exposable (sans chemins internes)."""
    out = []
    base = resolve_music_dir()
    for t in _CATALOG.values():
        available = bool(base and (base / t.filename).is_file())
        out.append({
            "track_id": t.track_id,
            "title": t.title,
            "artist": t.artist,
            "duration": t.duration,
            "mood": t.mood,
            "tags": list(t.tags),
            "license": t.license,
            "license_name": t.license_name,
            "license_url": t.license_url,
            "attribution": t.attribution,
            "source": t.source,
            "url": f"{PUBLIC_MUSIC_URL_PREFIX}/{t.filename}",
            "available": available,
        })
    return out


def _probe_duration_seconds(path: Path) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        res = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if res.returncode == 0:
            return float(res.stdout.strip())
    except Exception:
        return None
    return None


def _mood_for_context(activity: Any = None, tone: str | None = None) -> tuple[str, str]:
    """Retourne (mood, raison) selon activité/ton (heuristique)."""
    tone_l = (tone or "").lower()
    # Ton éditorial prioritaire si explicite
    if any(k in tone_l for k in ("humor", "fun", "léger", "decale", "décal")):
        return "energetic", "ton léger/décalé"
    if any(k in tone_l for k in ("epique", "épique", "cinema", "cinéma", "exploit", "motivant")):
        return "energetic", "ton épique/motivant"
    if any(k in tone_l for k in ("calm", "zen", "recup", "récup", "longue")):
        return "calm", "ton calme/progressif"

    dist_km = 0.0
    elev = 0.0
    dur = 0.0
    sport_type = ""
    if activity is not None:
        dist_km = (getattr(activity, "distance_m", None) or 0) / 1000.0
        elev = float(getattr(activity, "elevation_gain_m", None) or 0)
        dur = float(getattr(activity, "duration_seconds", None) or 0)
        sport_type = (getattr(activity, "sport_type", None) or "").lower()

    if "trail" in sport_type and (elev >= 300 or dist_km >= 10):
        return "energetic", "trail engagé (dénivelé/distance)"
    if dist_km >= 15 or elev >= 500 or dur >= 5400:
        return "energetic", "effort long/intense"
    if dist_km > 0 or dur > 0:
        # allure/effort modéré -> calme inspirant par défaut
        return "calm", "sortie modérée/inspirante"
    return "calm", "ambiance par défaut"


def select_track(
    activity: Any = None,
    tone: str | None = None,
    existing: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Sélectionne une piste (intelligente + aléatoire) et retourne une config enrichie.

    - Si une piste valide est déjà sélectionnée et force=False : conservée (persistée).
    - Si force=True : nouvelle sélection (régénération volontaire).
    """
    existing = existing or {}
    existing_id = existing.get("track_id") or existing.get("track")
    if not force and existing_id and existing_id in _CATALOG:
        # Conserver la sélection existante en complétant les champs manquants
        info = _CATALOG[existing_id]
        return normalize_audio_config({**_base_config(info, "conservée (persistée)"), **existing, "track_id": info.track_id, "track": info.track_id})

    mood, reason = _mood_for_context(activity, tone)
    pool = _ENERGETIC_IDS if mood == "energetic" else _CALM_IDS
    pool = [tid for tid in pool if tid in _CATALOG]
    if not pool:
        pool = _ALL_IDS
    chosen_id = random.choice(pool)
    info = _CATALOG[chosen_id]
    selection_reason = f"{reason}; humeur={mood}; sélection aléatoire contrôlée"
    return _base_config(info, selection_reason)


def _base_config(info: TrackInfo, selection_reason: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    # Tentative de durée réelle (best-effort, serveur uniquement)
    duration = info.duration
    path = resolve_track_path(info.track_id)
    probed = _probe_duration_seconds(path) if path else None
    if probed:
        duration = probed
    return {
        "source": "library_local",
        "track_id": info.track_id,
        "track": info.track_id,  # compat existante
        "title": info.title,
        "artist": info.artist,
        "url": f"{PUBLIC_MUSIC_URL_PREFIX}/{info.filename}",
        # pas de file_path interne exposé
        "duration": duration,
        "volume": 1.0,
        "fade_in": 0.0,
        "fade_out": 0.0,
        "enabled": True,
        "license": info.license,
        "license_name": info.license_name,
        "license_url": info.license_url,
        "attribution": info.attribution,
        "source_label": info.source,
        "selection_reason": selection_reason,
        "selected_at": now,
        "embedded": False,
        "audio_status": "selected",  # selected | integrated | rendering | ready | error
    }


def normalize_audio_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise une config audio pour exposition (sans chemins internes)."""
    if not isinstance(cfg, dict):
        return {}
    out = dict(cfg)
    # Ne jamais exposer de chemin interne
    out.pop("file_path", None)
    out.pop("path", None)
    # Garantir champs essentiels si track connu
    tid = out.get("track_id") or out.get("track")
    if tid and tid in _CATALOG:
        info = _CATALOG[tid]
        out.setdefault("source", "library_local")
        out.setdefault("track_id", info.track_id)
        out.setdefault("track", info.track_id)
        out.setdefault("title", info.title)
        out.setdefault("artist", info.artist)
        out.setdefault("url", f"{PUBLIC_MUSIC_URL_PREFIX}/{info.filename}")
        out.setdefault("duration", info.duration)
        out.setdefault("license", info.license)
        out.setdefault("license_name", info.license_name)
        out.setdefault("license_url", info.license_url)
        out.setdefault("attribution", info.attribution)
        out.setdefault("source_label", info.source)
    out.setdefault("enabled", True)
    out.setdefault("volume", 1.0)
    out.setdefault("fade_in", 0.0)
    out.setdefault("fade_out", 0.0)
    out.setdefault("embedded", False)
    out.setdefault("audio_status", "selected")
    return out


def ensure_audio_config(
    design: dict[str, Any] | None,
    activity: Any = None,
    tone: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Retourne un design mis à jour avec une config audio valide/persistée."""
    design = dict(design or {})
    current = design.get("audio") if isinstance(design.get("audio"), dict) else {}
    selected = select_track(activity=activity, tone=tone, existing=current, force=force)
    design["audio"] = normalize_audio_config(selected)
    return design
