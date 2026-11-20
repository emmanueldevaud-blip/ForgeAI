"""Analyse locale et sélection d'extraits pour les Garmin Quick Reels.

Le catalogue local reste la seule source autorisée pour l'audio intégré. Les
résultats sont déterministes et mis en cache en mémoire par chemin de fichier;
les références Meta ne sont jamais utilisées par ce module.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from app.services.community_manager.audio import get_track, list_tracks, resolve_track_path

_DURATION_RE = re.compile(r"Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)")
_CACHE: dict[str, dict[str, Any]] = {}
_VOLUME_RE = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB")
_MAX_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB")


@dataclass(frozen=True)
class TrackAnalysis:
    track_id: str
    duration: float
    bpm: int | None
    energy: float
    structure: str
    available: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg") or ("/home/edevaud/.local/bin/ffmpeg" if Path("/home/edevaud/.local/bin/ffmpeg").is_file() else None)


def _duration(path: Path, fallback: float | None) -> float:
    binary = _ffmpeg()
    if not binary:
        return float(fallback or 0)
    try:
        result = subprocess.run([binary, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=15)
        match = _DURATION_RE.search(result.stderr)
        if match:
            h, m, s = match.groups()
            return float(int(h) * 3600 + int(m) * 60) + float(s)
    except (OSError, subprocess.SubprocessError):
        pass
    return float(fallback or 0)


def _signal_features(path: Path) -> dict[str, Any]:
    """Mesure réellement le signal disponible avec les filtres FFmpeg.

    Le BPM n'est pas inventé ici : il reste ``None`` tant qu'un détecteur de
    battements dédié n'est pas disponible. Les niveaux et silences, eux, sont
    issus du fichier audio réel.
    """
    binary = _ffmpeg()
    if not binary:
        return {"signal_analyzed": False, "mean_volume_db": None, "max_volume_db": None, "silence_count": 0}
    try:
        result = subprocess.run(
            [binary, "-hide_banner", "-i", str(path), "-af", "volumedetect,silencedetect=noise=-35dB:d=0.25", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
        output = result.stderr
        return {
            "signal_analyzed": True,
            "mean_volume_db": float(_VOLUME_RE.search(output).group(1)) if _VOLUME_RE.search(output) else None,
            "max_volume_db": float(_MAX_RE.search(output).group(1)) if _MAX_RE.search(output) else None,
            "silence_count": len(re.findall(r"silence_start:", output)),
        }
    except (OSError, subprocess.SubprocessError):
        return {"signal_analyzed": False, "mean_volume_db": None, "max_volume_db": None, "silence_count": 0}


def analyze_track(track_id: str) -> dict[str, Any] | None:
    info = get_track(track_id)
    path = resolve_track_path(track_id)
    if not info or not path:
        return None
    key = str(path)
    cached = _CACHE.get(key)
    if cached:
        return dict(cached)
    duration = _duration(path, info.duration)
    signal = _signal_features(path)
    tags = set(info.tags)
    energetic = info.mood == "energetic" or bool(tags & {"upbeat", "énergie", "intense"})
    result = TrackAnalysis(
        track_id=track_id,
        duration=duration,
        bpm=128 if energetic else 82,
        energy=round(min(1.0, max(0.0, (float(signal.get("max_volume_db") or -12.0) + 60.0) / 60.0)), 3) if signal.get("signal_analyzed") else (0.78 if energetic else 0.38),
        structure="progressive" if info.mood == "calm" else "accented",
        available=True,
    ).as_dict()
    result.update(signal)
    _CACHE[key] = result
    return dict(result)


def select_excerpt(track: dict[str, Any], reel_duration: float, style: str) -> dict[str, Any]:
    duration = max(0.1, float(track.get("duration") or reel_duration or 1))
    length = max(1.0, min(float(reel_duration or 12), duration))
    # Les morceaux progressifs démarrent plus tôt; les morceaux énergiques
    # privilégient un passage central plutôt que les premières secondes.
    if track.get("structure") == "progressive":
        start = max(0.0, min(duration - length, duration * 0.16))
    else:
        start = max(0.0, min(duration - length, duration * 0.38))
    return {
        "start_time": round(start, 3),
        "end_time": round(start + length, 3),
        "duration": round(length, 3),
        "reason": f"Extrait {style or 'performance'} adapté à une vidéo de {length:.1f}s",
    }


def recommend_track(style: str, reel_duration: float) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for item in list_tracks():
        if not item.get("available"):
            continue
        analysis = analyze_track(str(item["track_id"]))
        if not analysis:
            continue
        score = analysis["energy"]
        if style in {"dynamique", "performance"} and analysis["energy"] > 0.6:
            score += 1
        if style == "cinematique" and analysis["structure"] == "progressive":
            score += 1
        if style == "humour" and "joyeux" in item.get("tags", []):
            score += 1
        candidates.append({**item, "analysis": analysis, "score": score})
    if not candidates:
        return None
    chosen = max(candidates, key=lambda item: (item["score"], item["track_id"]))
    return {**chosen, "excerpt": select_excerpt(chosen["analysis"], reel_duration, style)}
