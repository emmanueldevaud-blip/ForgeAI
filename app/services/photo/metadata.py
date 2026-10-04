"""Extraction des métadonnées EXIF (Pillow, sans dépendance externe).

Rien n'écrit dans l'original : on lit uniquement les informations utiles
(date de prise de vue, dimensions affichées, GPS, appareil).
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from PIL import Image, ExifTags

# Tags EXIF conservés pour l'affichage « Informations ».
_EXIF_TAGS = {
    "Make": "make",
    "Model": "model",
    "LensModel": "lens",
    "ISOSpeedRatings": "iso",
    "PhotographicSensitivity": "iso",
    "FNumber": "aperture",
    "ExposureTime": "exposure_time",
    "FocalLength": "focal_length",
    "Flash": "flash",
    "Software": "software",
    "Orientation": "orientation",
    "DateTimeOriginal": "taken_at",
    "OffsetTimeOriginal": "timezone_offset",
}

_TAGS_BY_ID = {value: key for key, value in ExifTags.TAGS.items()}
_GPS_TAGS_BY_ID = dict(ExifTags.GPSTAGS)


class MetadataError(Exception):
    pass


def _rational_to_float(value: Any) -> float | None:
    try:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            denom = float(value.denominator)
            return float(value.numerator) / denom if denom else None
        if isinstance(value, tuple) and len(value) == 2:
            denom = float(value[1])
            return float(value[0]) / denom if denom else None
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _parse_exif_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _gps_to_decimal(gps_info: dict) -> tuple[float, float] | None:
    try:
        lat_ref = gps_info.get("GPSLatitudeRef") or gps_info.get(1)
        lat_vals = gps_info.get("GPSLatitude") or gps_info.get(2)
        lon_ref = gps_info.get("GPSLongitudeRef") or gps_info.get(3)
        lon_vals = gps_info.get("GPSLongitude") or gps_info.get(4)
        if not lat_vals or not lon_vals:
            return None
        lat = sum(
            _rational_to_float(v) / (60 ** index) for index, v in enumerate(lat_vals)
        )
        lon = sum(
            _rational_to_float(v) / (60 ** index) for index, v in enumerate(lon_vals)
        )
        if lat is None or lon is None:
            return None
        if str(lat_ref).upper().startswith("S"):
            lat = -lat
        if str(lon_ref).upper().startswith("W"):
            lon = -lon
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None
        return lat, lon
    except Exception:
        return None


def _read_ifd(exif, ifd_code: int) -> dict:
    try:
        return dict(exif.get_ifd(ifd_code))
    except Exception:
        return {}


def extract_metadata(data: bytes) -> dict:
    """Ouvre les octets d'une image et en extrait les métadonnées.

    Retourne un dict : width, height, taken_at, gps, camera_make, camera_model,
    exif (dict compact pour l'API), format.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            img_format = (img.format or "").lower()
            width, height = img.size
            orientation = None
            taken_at = None
            gps: tuple[float, float] | None = None
            camera_make = None
            camera_model = None
            compact: dict[str, Any] = {}

            try:
                exif = img.getexif()
            except Exception:
                exif = None

            if exif:
                exif_ifd = _read_ifd(exif, 0x8769)
                gps_ifd = _read_ifd(exif, 0x8825)

                raw_taken = (
                    exif_ifd.get(_TAGS_BY_ID.get("DateTimeOriginal", 0x9003))
                    or exif.get(_TAGS_BY_ID.get("DateTimeOriginal", 0x9003))
                )
                taken_at = _parse_exif_datetime(raw_taken)

                raw_orientation = exif_ifd.get(274) or exif.get(274)
                if raw_orientation:
                    try:
                        orientation = int(raw_orientation)
                    except (TypeError, ValueError):
                        orientation = None

                make = exif_ifd.get(_TAGS_BY_ID.get("Make", 271)) or exif.get(271)
                model = exif_ifd.get(_TAGS_BY_ID.get("Model", 272)) or exif.get(272)
                camera_make = str(make).strip() if make else None
                camera_model = str(model).strip() if model else None

                if gps_ifd:
                    named = {}
                    for tag_id, value in gps_ifd.items():
                        name = _GPS_TAGS_BY_ID.get(tag_id, str(tag_id))
                        named[name] = value
                    gps = _gps_to_decimal(named)
                    if gps:
                        compact["gps"] = {"latitude": gps[0], "longitude": gps[1]}

                for tag_name, key in _EXIF_TAGS.items():
                    tag_id = _TAGS_BY_ID.get(tag_name)
                    if tag_id is None:
                        continue
                    value = exif_ifd.get(tag_id, exif.get(tag_id))
                    if value is None:
                        continue
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8", "ignore").strip("\x00")
                        except Exception:
                            continue
                    if hasattr(value, "numerator"):
                        converted = _rational_to_float(value)
                        if converted is not None:
                            value = converted
                    if key in ("make", "model") and camera_make and key == "make":
                        value = camera_make
                    if isinstance(value, (str, int, float)) and value != "":
                        compact[key] = value

                if taken_at:
                    compact["taken_at"] = taken_at.strftime("%Y:%m:%d %H:%M:%S")

            # L'orientation EXIF 5-8 échange largeur/hauteur à l'affichage.
            swapped = orientation in (5, 6, 7, 8)
            display_width, display_height = (
                (height, width) if swapped else (width, height)
            )

            return {
                "width": display_width,
                "height": display_height,
                "taken_at": taken_at,
                "gps": gps,
                "camera_make": camera_make,
                "camera_model": camera_model,
                "exif": compact,
                "format": img_format,
            }
    except MetadataError:
        raise
    except Exception as exc:
        raise MetadataError(f"Image illisible: {exc}") from exc


def sniff_image_format(data: bytes) -> str | None:
    """Retourne le format (jpeg/png/webp...) si les octets sont une image lisible."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            return (img.format or "").lower() or None
    except Exception:
        return None
