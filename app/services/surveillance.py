"""Gestion des sources et métadonnées de vidéosurveillance.

La capture et la détection sont volontairement séparées : cette couche ne
déclare jamais un flux opérationnel sans test explicite et ne lance aucun
processus par simple ouverture de la page.
"""
import base64
import hashlib
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


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
