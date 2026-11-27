"""Musique Instagram choisie par IA au moment du choix de la photo.

Au choix (ou au changement) de la photo dans le Studio, l'IA analyse le
visuel (entrée image de l'AI Gateway), recherche des pistes dans le
catalogue Instagram via l'endpoint Graph ``ig_audio`` (Audio API) et
persiste le choix dans ``design["ig_audio"]``.

Le choix est rattaché au Reel au moment de la publication via le paramètre
``audio_configuration`` (voir sport_instagram_publish.create_media_container).
La musique Instagram n'est attachable qu'aux Reels (limite Meta).
"""

import asyncio
import base64
import io
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.services.ai_gateway import ai_gateway

logger = logging.getLogger(__name__)

IG_AUDIO_SEARCH_LIMIT = 10
_MAX_IMAGE_SIDE = 768
_FALLBACK_QUERY = "running motivation"


def _is_instagram_page(url: str) -> bool:
    """Différencie une page instagram.com d'un fichier audio lisible par <audio>."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except (TypeError, ValueError):
        return False
    return host == "instagram.com" or host.endswith(".instagram.com")


def normalize_audio_result(item: dict) -> dict:
    """Normalise un résultat `/ig_audio` pour l'aperçu audio du front.

    Meta renvoie `download_url` (fichier MP3 temporaire, ~1,5 jour) pour la
    lecture et `on_platform_audio_preview_link` (page instagram.com) pour
    l'ouverture sur la plateforme : les deux ne sont pas interchangeables.
    """
    out = dict(item)
    audio_url = ""
    for key in ("download_url", "preview_link", "preview_url", "audio_url", "preview"):
        value = out.get(key)
        if isinstance(value, str) and value.strip() and not _is_instagram_page(value):
            audio_url = value.strip()
            break
    platform = out.get("on_platform_audio_preview_link") or out.get("on_platform_audio_preview_url")
    if audio_url:
        out["preview_link"] = audio_url
    else:
        out.pop("preview_link", None)
    if isinstance(platform, str) and platform.strip():
        out["platform_preview_link"] = platform.strip()
    return out


def _extract_json(text: str) -> Optional[dict]:
    """Extrait le premier objet JSON d'une réponse IA (avec ou sans bloc de code)."""
    if not text or not isinstance(text, str):
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _fallback_query(title: Optional[str]) -> str:
    words = [w for w in re.split(r"\s+", (title or "").strip()) if w][:4]
    return " ".join(words) if words else _FALLBACK_QUERY


async def photo_image_b64(db, current_user, photo_id: int) -> Optional[str]:
    """Charge la photo et la retourne en JPEG base64 réduit (pour l'analyse vision)."""
    try:
        from PIL import Image, ImageOps

        from app.services.photo.service import PhotoService

        photo_service = PhotoService(db, current_user)
        photo = await photo_service._get_owned(photo_id, include_deleted=True)
        storage = photo_service.storage
        src_path = storage.backend_for_photo(photo).original_path(photo.storage_path)
        if not src_path:
            return None
        try:
            src = Image.open(src_path)
        except Exception:
            # Les sélections Garmin peuvent contenir des vidéos MOV. On en
            # extrait une image représentative sans faire échouer les autres
            # médias de la sélection.
            ffmpeg = shutil.which("ffmpeg") or "/home/edevaud/.local/bin/ffmpeg"
            if not Path(ffmpeg).is_file() and not shutil.which("ffmpeg"):
                return None
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(src_path), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                capture_output=True,
                timeout=20,
                check=False,
            )
            if result.returncode != 0 or not result.stdout:
                return None
            src = Image.open(io.BytesIO(result.stdout))
        with src:
            img = ImageOps.exif_transpose(src).convert("RGB")
            img.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        logger.warning("[IG-MUSIC] Impossible de lire la photo %s pour l'analyse IA", photo_id, exc_info=True)
        return None


async def search_ig_audio(db, query: str, limit: int = IG_AUDIO_SEARCH_LIMIT) -> list[dict]:
    """Recherche de musiques dans le catalogue Instagram (GET /ig_audio)."""
    from app.services.sport_instagram_publish import MetaPublishService

    service = MetaPublishService(db)
    context = await service.resolve_publish_context()
    if not context:
        logger.warning("[IG-MUSIC] Contexte Meta absent — recherche '%s' impossible", query)
        return []
    token = await service._get_valid_token(context)
    if not token:
        return []

    params = {
        "audio_type": "music",
        "search_query": query,
        "ig_user_id": context.instagram_business_account_id,
        "access_token": token,
        "limit": str(limit),
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{service._base_url}/ig_audio", params=params)
        data = response.json()
    except Exception as exc:
        logger.warning("[IG-MUSIC] Recherche '%s' en échec: %s", query, exc)
        return []
    if "audio" not in data:
        error = (data or {}).get("error") or {}
        logger.warning(
            "[IG-MUSIC] Recherche '%s' refusée par Meta: %s", query, error.get("message")
        )
        return []
    results = [a for a in (data.get("audio") or []) if isinstance(a, dict) and a.get("audio_id")]
    return [normalize_audio_result(item) for item in results[:limit]]


async def _analyze_photo(image_b64: str, title: Optional[str], hashtags: Optional[str]) -> Optional[dict]:
    """Analyse vision de la photo -> description + requête de recherche musique."""
    prompt = (
        "Photo d'une sortie sportive (course à pied / trail, données Garmin).\n"
        f"Titre de la publication : {title or '(sans titre)'}\n"
        f"Hashtags : {hashtags or '-'}\n\n"
        "Décris brièvement la scène et l'ambiance, puis propose une RECHERCHE "
        "de musique Instagram (3 à 5 mots, en anglais) qui correspond à la photo, "
        "au titre et à ses mots-clés. Privilégie une chanson avec paroles plutôt "
        "qu'une musique instrumentale.\n"
        'Réponds uniquement en JSON : {"scene": "...", "ambiance": "...", '
        '"mots_cles": ["...", "..."], "recherche": "running motivation"}'
    )
    try:
        response = await ai_gateway.generate(
            prompt=prompt,
            system_prompt=(
                "Tu analyses des photos de sorties sportives pour choisir la "
                "musique Instagram la plus juste. Tu réponds uniquement en JSON valide."
            ),
            task_type="vision",
            image_b64=image_b64,
            temperature=0.2,
            max_tokens=400,
        )
    except Exception as exc:
        logger.warning("[IG-MUSIC] Analyse vision impossible: %s", exc)
        return None
    data = _extract_json(response.text)
    if not data:
        return None
    return data


async def _pick_track(
    results: list[dict], analysis: Optional[dict], avoid_audio_id: str | None = None
) -> Optional[dict]:
    """Choisit une piste parmi les résultats de recherche (IA texte, sinon la première)."""
    if not results:
        return None
    if len(results) == 1:
        return results[0]

    lines = [
        f"{i}. {r.get('title') or '?'} — {r.get('display_artist') or '?'}"
        for i, r in enumerate(results, start=1)
    ]
    scene = (analysis or {}).get("scene") or ""
    ambiance = (analysis or {}).get("ambiance") or ""
    prompt = (
        f"Photo : {scene}\nAmbiance : {ambiance}\n\n"
        "Parmi ces musiques Instagram, choisis celle dont le thème / les paroles "
        "collent le mieux à la photo et au titre :\n" + "\n".join(lines) +
            '\nRéponds uniquement en JSON : {"index": <numéro>, "start_time_ms": <millisecondes>, "raison": "..."}. '
            "Choisis un passage compris dans la durée du morceau qui sert le mieux le titre et l'ambiance."
    )
    try:
        response = await ai_gateway.generate(
            prompt=prompt,
            system_prompt="Tu choisis la musique Instagram la plus cohérente. Tu réponds uniquement en JSON valide.",
            task_type="fast",
            temperature=0.2,
            max_tokens=300,
        )
        data = _extract_json(response.text)
        if data:
            index = data.get("index")
            if isinstance(index, int) and 1 <= index <= len(results):
                chosen = results[index - 1]
                if avoid_audio_id and str(chosen.get("audio_id")) == str(avoid_audio_id):
                    alternatives = [item for item in results if str(item.get("audio_id")) != str(avoid_audio_id)]
                    if alternatives:
                        chosen = alternatives[0]
                chosen = dict(chosen)
                chosen["_raison"] = str(data.get("raison") or "")
                duration = chosen.get("duration_in_ms")
                try:
                    requested = max(0, int(data.get("start_time_ms") or 0))
                    if duration is not None:
                        requested = min(requested, max(0, int(duration) - 1000))
                    chosen["_start_time_ms"] = requested
                except (TypeError, ValueError):
                    chosen["_start_time_ms"] = 0
                return chosen
    except Exception as exc:
        logger.warning("[IG-MUSIC] Choix IA de la piste impossible: %s", exc)
    # Repli : conserver la cohérence avec une nouvelle photo en évitant la
    # piste précédente lorsque le catalogue fournit une alternative.
    if avoid_audio_id:
        for item in results:
            if str(item.get("audio_id")) != str(avoid_audio_id):
                return item
    return results[0]


async def pick_audio_for_photo(
    db,
    current_user,
    photo_id: int,
    title: Optional[str] = None,
    hashtags: Optional[str] = None,
    avoid_audio_id: str | None = None,
) -> Optional[dict]:
    """Analyse la photo, cherche et choisit une musique Instagram.

    Retourne l'entrée à persister dans ``design["ig_audio"]`` ou ``None``
    (échec non bloquant : la publication garde son état précédent).
    """
    image_b64 = await photo_image_b64(db, current_user, photo_id)
    if not image_b64:
        return None

    analysis = await _analyze_photo(image_b64, title, hashtags)
    query = str((analysis or {}).get("recherche") or "").strip() or _fallback_query(title)

    results = await search_ig_audio(db, query)
    if not results:
        fallback = _fallback_query(title)
        if fallback != query:
            results = await search_ig_audio(db, fallback)
            if results:
                query = fallback
    if not results:
        logger.info("[IG-MUSIC] Aucune musique trouvée pour '%s'", query)
        return None

    chosen = await _pick_track(results, analysis, avoid_audio_id=avoid_audio_id)
    if not chosen or not chosen.get("audio_id"):
        return None

    entry: dict[str, Any] = {
        "source": "instagram",
        "status": "selected",
        "audio_id": str(chosen.get("audio_id")),
        "title": chosen.get("title") or "",
        "artist": chosen.get("display_artist") or "",
        "duration_in_ms": chosen.get("duration_in_ms"),
        "preview_link": chosen.get("preview_link") or chosen.get("download_url"),
        "platform_preview_link": chosen.get("platform_preview_link") or chosen.get("on_platform_audio_preview_link"),
        "query": query,
        "scene": (analysis or {}).get("scene"),
        "ambiance": (analysis or {}).get("ambiance"),
        "raison": chosen.get("_raison"),
        # La liste est conservée pour permettre un choix explicite dans le Studio.
        # L'offset est fourni par Meta quand il est disponible ; sinon Instagram
        # démarre naturellement au début du morceau.
        "suggestions": [
            {
                "audio_id": str(item.get("audio_id")),
                "title": item.get("title") or "",
                "artist": item.get("display_artist") or "",
                "duration_in_ms": item.get("duration_in_ms"),
                "preview_link": item.get("preview_link") or item.get("download_url"),
                "platform_preview_link": item.get("platform_preview_link") or item.get("on_platform_audio_preview_link"),
                "start_time_ms": item.get("start_time_ms") or item.get("start_offset_ms") or 0,
            }
            for item in results[:10]
            if item.get("audio_id")
        ],
        "start_time_ms": chosen.get("_start_time_ms") or chosen.get("start_time_ms") or chosen.get("start_offset_ms") or 0,
        "picked_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        "[IG-MUSIC] Musique choisie: '%s' — %s (photo=%s, requête='%s')",
        entry["title"], entry["artist"], photo_id, query,
    )
    return entry


async def pick_audio_for_photos(
    db,
    current_user,
    photo_ids: list[int],
    title: Optional[str] = None,
    hashtags: Optional[str] = None,
    avoid_audio_id: str | None = None,
) -> Optional[dict]:
    """Choisit une piste à partir de plusieurs photos sélectionnées.

    Les analyses visuelles sont fusionnées dans une seule recherche afin que
    l'ajout ou le remplacement d'une photo puisse réellement modifier le
    contexte musical sans créer plusieurs pistes concurrentes.
    """
    ids = []
    for raw_id in photo_ids or []:
        try:
            photo_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if photo_id not in ids and len(ids) < 5:
            ids.append(photo_id)
    if not ids:
        return None

    analyses: list[dict] = []
    for photo_id in ids:
        image_b64 = await photo_image_b64(db, current_user, photo_id)
        if not image_b64:
            continue
        analysis = await _analyze_photo(image_b64, title, hashtags)
        if isinstance(analysis, dict):
            analyses.append(analysis)
    if not analyses:
        return None

    merged = {
        "scene": ", ".join(str(item.get("scene") or "") for item in analyses if item.get("scene")),
        "ambiance": ", ".join(str(item.get("ambiance") or "") for item in analyses if item.get("ambiance")),
        "recherche": " ".join(str(item.get("recherche") or "") for item in analyses if item.get("recherche")),
    }
    query = merged["recherche"].strip() or _fallback_query(title)
    results = await search_ig_audio(db, query)
    if not results:
        return None
    chosen = await _pick_track(results, merged, avoid_audio_id=avoid_audio_id)
    if not chosen or not chosen.get("audio_id"):
        return None
    duration = chosen.get("duration_in_ms")
    start_time = 0
    # Le passage est choisi par la même logique IA que pour une photo unique.
    # Ici, _pick_track porte déjà la sélection de l'index ; l'offset éventuel
    # est conservé lorsqu'il a été renvoyé par le catalogue.
    if chosen.get("start_time_ms") is not None:
        try:
            start_time = max(0, int(chosen.get("start_time_ms") or 0))
            if duration is not None:
                start_time = min(start_time, max(0, int(duration) - 1000))
        except (TypeError, ValueError):
            start_time = 0
    return {
        "source": "instagram",
        "status": "selected",
        "audio_id": str(chosen.get("audio_id")),
        "title": chosen.get("title") or "",
        "artist": chosen.get("display_artist") or "",
        "duration_in_ms": duration,
        "preview_link": chosen.get("preview_link") or chosen.get("download_url"),
        "platform_preview_link": chosen.get("platform_preview_link") or chosen.get("on_platform_audio_preview_link"),
        "query": query,
        "scene": merged["scene"],
        "ambiance": merged["ambiance"],
        "raison": chosen.get("_raison"),
        "suggestions": [
            {
                "audio_id": str(item.get("audio_id")),
                "title": item.get("title") or "",
                "artist": item.get("display_artist") or "",
                "duration_in_ms": item.get("duration_in_ms"),
                "preview_link": item.get("preview_link") or item.get("download_url"),
                "platform_preview_link": item.get("platform_preview_link") or item.get("on_platform_audio_preview_link"),
                "start_time_ms": item.get("start_time_ms") or item.get("start_offset_ms") or 0,
            }
            for item in results[:10] if item.get("audio_id")
        ],
        "start_time_ms": chosen.get("_start_time_ms") or start_time,
        "photo_ids": ids,
        "picked_at": datetime.now(timezone.utc).isoformat(),
    }


async def pick_audio_for_photo_bounded(*args, timeout_seconds: float = 15.0, **kwargs) -> Optional[dict]:
    """Variante bornée dans le temps (usage Studio : ne jamais bloquer un PATCH)."""
    try:
        return await asyncio.wait_for(pick_audio_for_photo(*args, **kwargs), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning("[IG-MUSIC] Choix musique dépassé (%ss)", timeout_seconds)
        return None


async def pick_audio_for_photos_bounded(*args, timeout_seconds: float = 20.0, **kwargs) -> Optional[dict]:
    """Version bornée de l'analyse multi-photos utilisée par le Studio."""
    try:
        return await asyncio.wait_for(pick_audio_for_photos(*args, **kwargs), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning("[IG-MUSIC] Choix multi-photos dépassé (%ss)", timeout_seconds)
        return None
