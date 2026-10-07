"""Génération des miniatures (Pillow) — images et sources iPhone (V3.1).

Plusieurs tailles sont produites pour que la galerie ne charge jamais
l'original. Les miniatures sont toujours régénérables : l'original est la
source de vérité — notamment un original NAS, qui n'est **jamais** modifié
ni déplacé (les miniatures vivent uniquement dans le stockage local
ForgeAI).

Sources supportées :

- images classiques via Pillow (JPEG, PNG, …) ;
- **HEIC/HEIF** via ``pillow-heif`` (enregistré à l'import du module ; sans
  lui, ``Image.open`` lève et l'import dégrade proprement côté ingest) ;
- **vidéos MOV/MP4** : une frame représentative extraite par ``ffmpeg``
  (binaire système, ``shutil.which``). Frame 0 puis, si elle est noire,
  frame ≈ 1 s. Pas d'analyse de la vidéo entière, tout reste en flux.
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageFile, ImageOps, ImageStat

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Certains JPEG d'import sont tronqués en fin de flux (« broken data stream »)
# : le décodage tolère les données manquantes pour produire une miniature.
# L'original reste intact et non modifié.
ImageFile.LOAD_TRUNCATED_IMAGES = True

DEFAULT_QUALITY = 80

# Extensions vidéo traitées pour extraction de frame (V3.1).
VIDEO_EXTS = {".mov", ".mp4"}

# Seuil (luminosité moyenne 0..255) sous lequel une frame est considérée
# comme noire / non exploitable.
_BLANK_MEAN_THRESHOLD = 8.0

# Timeout d'une extraction ffmpeg (une frame, pas un transcodage).
_FFMPEG_TIMEOUT_SECONDS = 60


class ThumbnailError(Exception):
    """Miniature impossible à générer (codec absent, fichier corrompu…).

    Ne doit jamais faire échouer l'import : l'appelant dégrade proprement."""


_HEIF_OK = False


def _register_heif() -> bool:
    """Enregistre l'opérateur HEIF/HEIC de pillow-heif (idempotent)."""
    global _HEIF_OK
    if _HEIF_OK:
        return True
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        _HEIF_OK = True
    except Exception as exc:  # noqa: BLE001 - dégradation documentée
        logger.warning(
            "[PHOTO-THUMBS] HEIC/HEIF non disponible (pillow-heif absent ?): %s", exc
        )
    return _HEIF_OK


_register_heif()


def heif_supported() -> bool:
    return _HEIF_OK


def ffmpeg_available() -> bool:
    """FFmpeg est-il utilisable (binaire système) ?"""
    return shutil.which("ffmpeg") is not None


def parse_thumbnail_sizes(raw: str | None = None) -> dict[str, int]:
    """Parse « tiny:96,small:256,... » en {nom: largeur_px} trié croissant."""
    if raw is None:
        raw = get_settings().PHOTO_THUMBNAIL_SIZES
    sizes: dict[str, int] = {}
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        name, _, width = chunk.partition(":")
        try:
            value = int(width)
        except ValueError:
            continue
        if name.strip() and value > 0:
            sizes[name.strip()] = value
    if not sizes:
        sizes = {"small": 256, "medium": 640, "preview": 2048}
    return dict(sorted(sizes.items(), key=lambda item: item[1]))


def _as_rgb(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        flattened = Image.new("RGB", image.size, (255, 255, 255))
        converted = image.convert("RGBA")
        flattened.paste(converted, mask=converted.split()[-1])
        return flattened
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


# ------------------------------------------------------------------- vidéos

def _run_ffmpeg(args: list[str]) -> bytes:
    """Lance ffmpeg (une seule frame, sortie PNG sur stdout)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ThumbnailError(
            "ffmpeg introuvable : miniature vidéo indisponible "
            "(installer ffmpeg pour l'extraction de frames)"
        )
    try:
        proc = subprocess.run(
            [ffmpeg, *args],
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ThumbnailError(f"ffmpeg timeout ({_FFMPEG_TIMEOUT_SECONDS}s)") from exc
    except OSError as exc:
        raise ThumbnailError(f"ffmpeg impossible à lancer: {exc}") from exc
    if proc.returncode != 0 or not proc.stdout:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise ThumbnailError(f"ffmpeg en échec: {stderr[-300:]}")
    return proc.stdout


def _decode_frame(png_bytes: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(png_bytes))
    image.load()
    return image


def _is_blank_frame(image: Image.Image) -> bool:
    try:
        mean = ImageStat.Stat(image.convert("L")).mean[0]
        return mean < _BLANK_MEAN_THRESHOLD
    except Exception:  # noqa: BLE001 - image illisible = non exploitable
        return True


def _extract_video_frame(path: Path) -> Image.Image:
    """Frame représentative d'une vidéo, sans la charger en mémoire.

    1. frame 0 (flux, une seule frame décodée) ;
    2. si noire / non exploitable : frame ≈ 1 s (seek rapide avant ``-i``) ;
    3. si ce second essai échoue (vidéo < 1 s) : la frame 0 fait foi.
    """
    out_args = ["-frames:v", "1", "-f", "image2", "-vcodec", "png", "pipe:1"]
    first = _decode_frame(
        _run_ffmpeg(["-loglevel", "error", "-i", str(path), *out_args])
    )
    if not _is_blank_frame(first):
        return first
    try:
        retry = _decode_frame(
            _run_ffmpeg(["-loglevel", "error", "-ss", "1", "-i", str(path), *out_args])
        )
    except ThumbnailError:
        logger.debug("[PHOTO-THUMBS] frame à 1s indisponible pour %s", path.name)
        return first
    return retry


def _open_source(original_path: Path) -> Image.Image:
    """Ouvre la source : image Pillow (HEIC compris) ou frame vidéo."""
    if original_path.suffix.lower() in VIDEO_EXTS:
        return _extract_video_frame(original_path)
    return Image.open(original_path)


# --------------------------------------------------------------- thumbnails

def generate_thumbnails(
    original_path: Path,
    thumbs_dir: Path,
    sizes: dict[str, int] | None = None,
    quality: int = DEFAULT_QUALITY,
) -> list[dict]:
    """Génère les miniatures de ``original_path`` dans ``thumbs_dir``.

    L'image source (photo HEIC ou frame de vidéo) est décodée **une fois**,
    puis réduite pour chaque taille — mêmes tailles, noms, qualité et
    cache local que depuis la V1 (aucun second système de cache).
    L'original n'est jamais écrit.

    Retourne une liste de dicts {size, storage_path, width, height,
    byte_size, source_width, source_height} — chemins relatifs à
    ``thumbs_dir``. Lève ``ThumbnailError`` / ``UnidentifiedImageError``
    si la source est illisible.
    """
    sizes = sizes or parse_thumbnail_sizes()
    results: list[dict] = []
    with _open_source(original_path) as source:
        # L'orientation EXIF est appliquée dans la miniature, pas dans l'original.
        base = ImageOps.exif_transpose(source)
        base = _as_rgb(base)
        for name, width in sizes.items():
            variant = base.copy()
            variant.thumbnail((width, width), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            variant.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
            payload = buffer.getvalue()
            rel = f"{name}.jpg"
            target = thumbs_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            results.append(
                {
                    "size": name,
                    "storage_path": rel,
                    "width": variant.width,
                    "height": variant.height,
                    "byte_size": len(payload),
                    # Dimensions de la source (frame vidéo / image décodée) —
                    # utilisé par l'ingest pour renseigner la photo.
                    "source_width": base.width,
                    "source_height": base.height,
                }
            )
    return results
