"""Gestion des sources et métadonnées de vidéosurveillance.

La capture et la détection sont volontairement séparées : cette couche ne
déclare jamais un flux opérationnel sans test explicite et ne lance aucun
processus par simple ouverture de la page.
"""
import asyncio
import base64
import hashlib
import ipaddress
import logging
import socket
import time
from io import BytesIO
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from PIL import Image, ImageChops

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Un client.get() sur un flux MJPEG ne se termine jamais (les trames arrivent
# en continu) : on impose donc un delai global par tentative de capture.
_FETCH_DEADLINE_SECONDS = 8.0
_MAX_SNAPSHOT_BYTES = 10_000_000
_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"


def _cipher() -> Fernet:
    secret = get_settings().SECRET_KEY.encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def encrypt_password(value: str | None) -> str | None:
    return _cipher().encrypt(value.encode()).decode() if value else None


def decrypt_password(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Mot de passe caméra illisible") from exc


def has_password(value: str | None) -> bool:
    return bool(value)


def validate_camera_target(protocol: str | None, host: str | None, port: int | None, stream_url: str | None) -> None:
    """Valide une cible caméra et bloque les URLs munies d'identifiants."""
    if stream_url:
        parsed = urlparse(stream_url)
        if parsed.scheme not in {"http", "https", "rtsp"} or parsed.username or parsed.password:
            raise ValueError("URL de flux invalide ou contenant des identifiants")
        if not parsed.hostname:
            raise ValueError("Hôte de flux manquant")
    if protocol and protocol not in {"http", "https", "rtsp", "onvif"}:
        raise ValueError("Protocole caméra non supporté")
    if host:
        try:
            address = ipaddress.ip_address(host)
            if address.is_multicast or address.is_unspecified or address.is_reserved:
                raise ValueError("Adresse caméra non autorisée")
        except ValueError:
            try:
                socket.getaddrinfo(host, port or 80, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise ValueError("Nom d'hôte caméra introuvable") from exc


async def test_camera_connection(camera) -> tuple[bool, str, str]:
    if camera.source_type in {"usb", "integrated", "remote_agent"}:
        return False, "Cette source nécessite un agent de capture configuré", "unsupported"
    validate_camera_target(camera.protocol, camera.host, camera.port, camera.stream_url)
    if camera.protocol in {"rtsp", "onvif"}:
        return False, "Le diagnostic RTSP/ONVIF nécessite FFmpeg ou un agent caméra", "unsupported"
    url = camera.stream_url or f"{camera.protocol or 'http'}://{camera.host}:{camera.port or 80}"
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(url, headers={"Range": "bytes=0-0"})
        if response.status_code < 400:
            return True, f"Source joignable (HTTP {response.status_code})", "online"
        return False, f"La source répond avec HTTP {response.status_code}", "error"
    except httpx.HTTPError as exc:
        return False, f"Source inaccessible : {type(exc).__name__}", "offline"


async def _read_mjpeg_frame(response: httpx.Response) -> bytes | None:
    """Extraire la premiere image JPEG complete d'un flux MJPEG."""
    deadline = time.monotonic() + _FETCH_DEADLINE_SECONDS
    buffer = bytearray()
    async for chunk in response.aiter_bytes():
        buffer.extend(chunk)
        soi = buffer.find(_JPEG_SOI)
        if soi >= 0:
            eoi = buffer.find(_JPEG_EOI, soi + 2)
            if eoi >= 0:
                return bytes(buffer[soi : eoi + 2])
            # Trame incomplete : on conserve le debut de l'image (SOI).
            del buffer[:soi]
        elif len(buffer) > _MAX_SNAPSHOT_BYTES:
            buffer = buffer[-4096:]
        if time.monotonic() >= deadline:
            break
    return None


async def _read_body(response: httpx.Response) -> bytes:
    """Lire un corps HTTP simple en imposant une taille et un delai maximums."""
    deadline = time.monotonic() + _FETCH_DEADLINE_SECONDS
    buffer = bytearray()
    async for chunk in response.aiter_bytes():
        buffer.extend(chunk)
        if len(buffer) >= _MAX_SNAPSHOT_BYTES or time.monotonic() >= deadline:
            break
    return bytes(buffer)


async def _fetch_snapshot(camera) -> Image.Image | None:
    """Prendre une capture snapshot HTTP depuis la camera.

    Les flux MJPEG (multipart/x-mixed-replace) sont geres en extrayant la
    premiere image JPEG complete du flux : une simple requete GET complete
    n'aboutit jamais sur ce type de source.
    """
    url = camera.stream_url or f"{camera.protocol or 'http'}://{camera.host}:{camera.port or 80}"
    try:
        timeout = httpx.Timeout(
            connect=3.0,
            read=_FETCH_DEADLINE_SECONDS,
            write=5.0,
            pool=3.0,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    logger.warning(
                        "[SURVEILLE] Snapshot HTTP %s pour %s",
                        response.status_code,
                        camera.name,
                    )
                    return None
                content_type = response.headers.get("content-type", "")
                if "multipart" in content_type:
                    data = await _read_mjpeg_frame(response)
                else:
                    data = await _read_body(response)
        if not data:
            logger.warning("[SURVEILLE] Aucune image lue depuis %s", camera.name)
            return None
        image = Image.open(BytesIO(data))
        image.load()
        return image.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SURVEILLE] Snapshot impossible pour %s: %s", camera.name, exc)
        return None


async def detect_motion(camera, min_pixel_diff: int = 5, pixel_threshold: int = 25) -> bool:
    """Detecter un mouvement en comparant deux snapshots successifs.

    Deux captures sont prises a 3 secondes d'intervalle. ``pixel_threshold``
    ignore les variations faibles (codage JPEG, bruit capteur) et
    ``min_pixel_diff`` fixe le pourcentage minimum de pixels modifies de facon
    significative pour declencher une alerte (5 % par defaut).
    """
    img1 = await _fetch_snapshot(camera)
    if img1 is None:
        return False
    await asyncio.sleep(3)
    img2 = await _fetch_snapshot(camera)
    if img2 is None or img1.size != img2.size:
        return False
    diff = ImageChops.difference(img1, img2).convert("L")
    histogram = diff.histogram()
    changed = sum(histogram[pixel_threshold:])
    ratio = changed / float(img1.width * img1.height)
    return ratio >= min_pixel_diff / 100


_MOTION_COOLDOWN_SECONDS = 60


async def detect_motion_and_notify(db, camera) -> None:
    """Detecter un mouvement, enregistrer l'evenement puis notifier (in-app + push).

    Un evenement est au maximum cree toutes les ``_MOTION_COOLDOWN_SECONDS``
    secondes par camera pour eviter de spammer les notifications.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.domotique import SurveillanceEvent
    from app.services.domotique.engine import _notify_users

    if not await detect_motion(camera):
        return
    since = datetime.now(timezone.utc) - timedelta(seconds=_MOTION_COOLDOWN_SECONDS)
    recent = (
        await db.execute(
            select(SurveillanceEvent)
            .where(
                SurveillanceEvent.camera_id == camera.id,
                SurveillanceEvent.event_type == "motion",
                SurveillanceEvent.created_at >= since,
            )
            .limit(1)
        )
    ).scalars().first()
    if recent is not None:
        logger.info(
            "[SURVEILLE] Mouvement ignore (cooldown) camera=%s",
            camera.name,
        )
        return
    event = SurveillanceEvent(
        camera_id=camera.id,
        event_type="motion",
        confidence=1.0,
        metadata_json={"camera_name": camera.name},
    )
    db.add(event)
    await db.commit()
    await _notify_users(
        db,
        title="Alerte surveillance",
        message=f"Mouvement détecté à la caméra {camera.name}",
        data={"url": "/domotique/surveillance", "event_id": event.id},
    )
    await db.commit()
    logger.info(
        "[SURVEILLE] Mouvement detecte camera=%s event=%s",
        camera.name,
        event.id,
    )
