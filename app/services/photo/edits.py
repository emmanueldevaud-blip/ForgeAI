"""Retouche photo : production de versions dérivées.

Règle absolue : l'original n'est jamais modifié. Chaque retouche crée une
nouvelle ``PhotoEdit`` rendue à partir de l'original avec des paramètres
cumulés, ce qui permet de « revenir à l'original » à tout moment.

Opérations locales implémentées (Pillow) : rotate, crop, adjust,
auto_enhance. Les opérations IA (ai_remove, ai_upscale, ai_restore) sont
acceptées par le schéma mais renvoient 501 tant qu'aucun moteur n'est branché
(framework prêt, voir docs/photos.md).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageEnhance, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo, PhotoEdit
from app.services.photo.storage import get_photo_storage

logger = logging.getLogger(__name__)

SUPPORTED_KINDS = ("rotate", "crop", "adjust", "auto_enhance")
AI_KINDS = ("ai_remove", "ai_upscale", "ai_restore")

_ROTATE_CLOCKWISE = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}


class PhotoEditError(Exception):
    pass


class PhotoEditUnavailable(Exception):
    """Opération IA préparée mais sans moteur branché (501)."""


def merge_params(previous: dict | None, kind: str, params: dict | None) -> dict:
    """Fusionne l'opération courante dans les paramètres cumulés."""
    merged: dict[str, Any] = dict(previous or {})
    params = params or {}
    if kind == "rotate":
        previous_deg = int(merged.get("rotate_degrees", 0) or 0)
        degrees = int(params.get("degrees", 90) or 0) % 360
        total = (previous_deg + degrees) % 360
        if total == 0:
            merged.pop("rotate_degrees", None)
        else:
            merged["rotate_degrees"] = total
    elif kind == "crop":
        merged["crop"] = {
            "x": float(params.get("x", 0)),
            "y": float(params.get("y", 0)),
            "w": float(params.get("w", 1)),
            "h": float(params.get("h", 1)),
        }
    elif kind == "adjust":
        adjust = dict(merged.get("adjust") or {})
        for key in ("brightness", "contrast", "saturation"):
            if key in params:
                adjust[key] = float(params[key])
        merged["adjust"] = adjust
    elif kind == "auto_enhance":
        merged["auto_enhance"] = bool(params.get("enabled", True))
    return merged


def _apply_pipeline(image: Image.Image, params: dict) -> Image.Image:
    result = image

    degrees = int(params.get("rotate_degrees", 0) or 0) % 360
    if degrees:
        transpose = _ROTATE_CLOCKWISE.get(degrees)
        if transpose is None:
            raise PhotoEditError(f"Angle de rotation non supporté: {degrees}")
        result = result.transpose(transpose)

    crop = params.get("crop")
    if crop:
        width, height = result.size
        x = max(0.0, min(0.999, float(crop.get("x", 0))))
        y = max(0.0, min(0.999, float(crop.get("y", 0))))
        w = max(0.001, min(1.0 - x, float(crop.get("w", 1))))
        h = max(0.001, min(1.0 - y, float(crop.get("h", 1))))
        box = (
            int(round(x * width)),
            int(round(y * height)),
            int(round((x + w) * width)),
            int(round((y + h) * height)),
        )
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            raise PhotoEditError("Zone de recadrage trop petite")
        result = result.crop(box)

    adjust = params.get("adjust") or {}
    brightness = float(adjust.get("brightness", 1.0))
    contrast = float(adjust.get("contrast", 1.0))
    saturation = float(adjust.get("saturation", 1.0))
    if brightness != 1.0:
        result = ImageEnhance.Brightness(result).enhance(max(0.1, min(2.0, brightness)))
    if contrast != 1.0:
        result = ImageEnhance.Contrast(result).enhance(max(0.1, min(2.0, contrast)))
    if saturation != 1.0:
        result = ImageEnhance.Color(result).enhance(max(0.1, min(2.0, saturation)))

    if params.get("auto_enhance"):
        result = ImageOps.autocontrast(result, cutoff=1)
        result = ImageEnhance.Color(result).enhance(1.08)
        result = ImageEnhance.Sharpness(result).enhance(1.15)

    return result


def _render(original_path: Path, target_path: Path, params: dict, keep_alpha: bool) -> tuple[int, int, int]:
    with Image.open(original_path) as source:
        base = ImageOps.exif_transpose(source)
        rendered = _apply_pipeline(base, params)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if keep_alpha and rendered.mode in ("RGBA", "LA", "P"):
            rendered = rendered.convert("RGBA")
            rendered.save(target_path, format="PNG", optimize=True)
        else:
            if rendered.mode != "RGB":
                if rendered.mode in ("RGBA", "LA", "P"):
                    flattened = Image.new("RGB", rendered.size, (255, 255, 255))
                    rgba = rendered.convert("RGBA")
                    flattened.paste(rgba, mask=rgba.split()[-1])
                    rendered = flattened
                else:
                    rendered = rendered.convert("RGB")
            rendered.save(target_path, format="JPEG", quality=92, optimize=True, progressive=True)
        return rendered.width, rendered.height, target_path.stat().st_size


async def create_edit(
    db: AsyncSession,
    photo: Photo,
    *,
    kind: str,
    params: dict | None = None,
    name: str | None = None,
    created_by: int | None = None,
) -> PhotoEdit:
    if kind in AI_KINDS:
        raise PhotoEditUnavailable(
            f"Traitement « {kind} » préparé mais aucun moteur IA n'est branché"
        )
    if kind not in SUPPORTED_KINDS:
        raise PhotoEditError(f"Type de retouche inconnu: {kind}")

    storage = get_photo_storage()
    original_path = storage.backend_for_photo(photo).original_path(photo.storage_path)
    if not original_path.is_file():
        raise PhotoEditError("Original introuvable sur le disque")

    previous_result = await db.execute(
        select(PhotoEdit)
        .where(PhotoEdit.photo_id == photo.id, PhotoEdit.is_active.is_(True))
        .order_by(PhotoEdit.created_at.desc())
        .limit(1)
    )
    previous = previous_result.scalar_one_or_none()
    merged = merge_params(previous.params_json if previous else None, kind, params)

    edit_uuid = str(uuid4())
    keep_alpha = photo.mime_type in ("image/png", "image/webp")
    rel = storage.edit_rel(photo.id, edit_uuid, ".png" if keep_alpha else ".jpg")
    target = storage.edit_path(rel)

    width, height, byte_size = await asyncio.to_thread(
        _render, original_path, target, merged, keep_alpha
    )

    if previous:
        previous.is_active = False
    edit = PhotoEdit(
        photo_id=photo.id,
        parent_edit_id=previous.id if previous else None,
        kind=kind,
        name=name,
        params_json=merged,
        storage_path=rel,
        width=width,
        height=height,
        byte_size=byte_size,
        status="ready",
        is_active=True,
        created_by=created_by,
        created_at=datetime.now(),
    )
    db.add(edit)
    await db.commit()
    await db.refresh(edit)
    return edit


async def revert_to_original(db: AsyncSession, photo: Photo) -> int:
    """Désactive toutes les versions : la photo repasse à son original."""
    result = await db.execute(
        select(PhotoEdit).where(
            PhotoEdit.photo_id == photo.id, PhotoEdit.is_active.is_(True)
        )
    )
    deactivated = 0
    for edit in result.scalars().all():
        edit.is_active = False
        deactivated += 1
    await db.commit()
    return deactivated
