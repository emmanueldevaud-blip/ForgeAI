"""Notification Service generique de ForgeAI.

Tout module peut demander l'envoi d'une notification :

    from app.services.notification import NotificationService

    await NotificationService(db).send(
        user_id=user_id,
        title="Analyse Sport",
        message="Ton analyse est disponible.",
        category="sport_analysis",
    )

La notification est toujours stockee en base (consultable dans ForgeAI).
Lorsqu'un abonnement Web Push existe pour l'utilisateur, un message chiffré
(RFC 8291, aes128gcm) est envoyé au service de push : il arrive en
notification standard sur le telephone, que Garmin Connect replique ensuite
sur la montre. L'envoi push est toujours best-effort : il ne fait jamais
echouer l'appelant.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import struct
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.notification import Notification, NotificationPushSubscription

logger = logging.getLogger(__name__)

# Taille de record impose par RFC 8291 (section 4) : superieure au plaintext.
_RECORD_SIZE = 4096
_PUSH_TIMEOUT_SECONDS = 10.0
_VAPID_EXPIRY_SECONDS = 12 * 3600


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand (RFC 5869) avec HMAC-SHA-256, blocs consecutifs."""
    output = b""
    block = b""
    counter = 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def encrypt_push_payload(
    plaintext: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    *,
    local_private: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """Chiffre un message Web Push selon RFC 8291 (Content-Encoding aes128gcm).

    Retourne le corps complet : en-tête (salt || rs || idlen || keyid) ++ ciphertext ++ tag.
    ``local_private`` et ``salt`` sont injectables uniquement pour les tests
    (vecteur de l'Appendix A du RFC 8291).
    """
    local = local_private or ec.generate_private_key(ec.SECP256R1())
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh_secret = local.exchange(ec.ECDH(), peer)
    as_public = local.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    # Combinaison du secret ECDH avec le secret d'authentification (RFC 8291 3.3)
    prk_key = hmac.new(auth_secret, ecdh_secret, hashlib.sha256).digest()
    key_info = b"WebPush: info\x00" + ua_public + as_public
    ikm = _hkdf_expand(prk_key, key_info, 32)

    # Derivation CEK / nonce via HKDF (RFC 8188)
    salt = salt or os.urandom(16)
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    cek = hmac.new(prk, b"Content-Encoding: aes128gcm\x00\x01", hashlib.sha256).digest()[:16]
    nonce = hmac.new(prk, b"Content-Encoding: nonce\x00\x01", hashlib.sha256).digest()[:12]

    body = plaintext + b"\x02"  # delimiteur de padding (aucun padding)
    encryptor = Cipher(algorithms.AES(cek), modes.GCM(nonce)).encryptor()
    ciphertext = encryptor.update(body) + encryptor.finalize()

    header = salt + struct.pack(">I", _RECORD_SIZE) + bytes([len(as_public)]) + as_public
    return header + ciphertext + encryptor.tag


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ #
    # Envoi
    # ------------------------------------------------------------------ #

    async def send(
        self,
        *,
        user_id: int,
        title: str,
        message: str,
        category: str = "system",
        data: dict[str, Any] | None = None,
    ) -> Notification:
        """Cree la notification et tente (best-effort) l'envoi push telephone."""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            category=category,
            data_json=data or {},
        )
        self.db.add(notification)
        await self.db.flush()
        notification.push_sent = await self._push_all(notification)
        return notification

    async def _push_all(self, notification: Notification) -> bool:
        subscriptions = (
            await self.db.execute(
                select(NotificationPushSubscription).where(
                    NotificationPushSubscription.user_id == notification.user_id
                )
            )
        ).scalars().all()
        if not subscriptions:
            return False
        sent = False
        async with httpx.AsyncClient(timeout=_PUSH_TIMEOUT_SECONDS) as client:
            for subscription in subscriptions:
                try:
                    outcome = await self._push_one(client, subscription, notification)
                except Exception:
                    logger.warning(
                        "[NOTIFICATION] Echec push notification=%s", notification.id, exc_info=True
                    )
                    continue
                if outcome == "sent":
                    sent = True
                elif outcome == "expired":
                    # Abonnement rigone par le service de push : on le retire.
                    await self.db.delete(subscription)
        return sent

    async def _push_one(
        self,
        client: httpx.AsyncClient,
        subscription: NotificationPushSubscription,
        notification: Notification,
    ) -> str:
        keys = get_settings()
        if not keys.NOTIFICATION_VAPID_PRIVATE_KEY:
            return "skipped"
        try:
            ua_public = _b64url_decode(subscription.p256dh)
            auth_secret = _b64url_decode(subscription.auth)
        except (ValueError, TypeError):
            logger.warning("[NOTIFICATION] Abonnement push invalide id=%s", subscription.id)
            await self.db.delete(subscription)
            return "expired"

        payload = json.dumps(
            {
                "title": notification.title,
                "body": notification.message,
                "tag": (notification.data_json or {}).get("url") or notification.category,
                "url": (notification.data_json or {}).get("url"),
            },
            ensure_ascii=False,
        ).encode("utf-8")

        try:
            body = encrypt_push_payload(payload, ua_public, auth_secret)
            vapid = self._vapid_authorization(subscription.endpoint)
        except (ValueError, TypeError) as exc:
            logger.warning("[NOTIFICATION] Impossible de chiffrer le push: %s", exc)
            return "error"

        response = await client.post(
            subscription.endpoint,
            content=body,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Encoding": "aes128gcm",
                "TTL": "86400",
                "Urgency": "normal",
                "Authorization": vapid,
            },
        )
        if response.status_code in (200, 201, 202):
            return "sent"
        if response.status_code in (404, 410):
            return "expired"
        logger.warning(
            "[NOTIFICATION] Push refuse statut=%s subscription=%s",
            response.status_code,
            subscription.id,
        )
        subscription.failed_at = datetime.now(timezone.utc)
        return "error"

    @staticmethod
    def _vapid_authorization(endpoint: str) -> str:
        """Autorisation VAPID (RFC 8292) : JWT ES256 signe avec la cle privee."""
        settings = get_settings()
        private_key = _load_vapid_private_key(settings.NOTIFICATION_VAPID_PRIVATE_KEY)
        parts = urlsplit(endpoint)
        audience = f"{parts.scheme}://{parts.netloc}"
        subject = settings.NOTIFICATION_VAPID_SUBJECT or "mailto:admin@localhost"

        header = _b64url_encode(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
        claims = _b64url_encode(
            json.dumps(
                {"aud": audience, "exp": int(time.time()) + _VAPID_EXPIRY_SECONDS, "sub": subject},
                separators=(",", ":"),
            ).encode()
        )
        signing_input = f"{header}.{claims}".encode("ascii")
        der_signature = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_signature)
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        token = f"{header}.{claims}.{_b64url_encode(signature)}"

        public_raw = private_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return f"vapid t={token}, k={_b64url_encode(public_raw)}"

    @staticmethod
    def vapid_public_key() -> str:
        settings = get_settings()
        if settings.NOTIFICATION_VAPID_PUBLIC_KEY:
            return settings.NOTIFICATION_VAPID_PUBLIC_KEY
        if settings.NOTIFICATION_VAPID_PRIVATE_KEY:
            private_key = _load_vapid_private_key(settings.NOTIFICATION_VAPID_PRIVATE_KEY)
            public_raw = private_key.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
            return _b64url_encode(public_raw)
        return ""

    # ------------------------------------------------------------------ #
    # Consultation
    # ------------------------------------------------------------------ #

    async def list_for_user(
        self,
        user_id: int,
        *,
        unread_only: bool = False,
        category: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        query = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        if category:
            query = query.where(Notification.category == category)
        result = await self.db.execute(query.order_by(Notification.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def unread_count(self, user_id: int) -> int:
        result = await self.db.execute(
            select(Notification).where(
                Notification.user_id == user_id, Notification.is_read.is_(False)
            )
        )
        return len(list(result.scalars().all()))

    async def mark_read(self, user_id: int, notification_id: int) -> Notification | None:
        notification = await self.db.scalar(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
        )
        if notification and not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            await self.db.flush()
        return notification

    async def mark_all_read(self, user_id: int, category: str | None = None) -> int:
        query = select(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
        if category:
            query = query.where(Notification.category == category)
        items = list((await self.db.execute(query)).scalars().all())
        now = datetime.now(timezone.utc)
        for item in items:
            item.is_read = True
            item.read_at = now
        if items:
            await self.db.flush()
        return len(items)

    # ------------------------------------------------------------------ #
    # Abonnements push
    # ------------------------------------------------------------------ #

    async def subscribe(self, user_id: int, endpoint: str, p256dh: str, auth: str) -> NotificationPushSubscription:
        if len(endpoint) > 500:
            raise ValueError("Endpoint de notification trop long")
        existing = await self.db.scalar(
            select(NotificationPushSubscription).where(
                NotificationPushSubscription.user_id == user_id,
                NotificationPushSubscription.endpoint == endpoint,
            )
        )
        if existing:
            existing.p256dh = p256dh
            existing.auth = auth
            existing.failed_at = None
            await self.db.flush()
            return existing
        subscription = NotificationPushSubscription(
            user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth
        )
        self.db.add(subscription)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError("Abonnement push déjà enregistré") from exc
        return subscription

    async def unsubscribe(self, user_id: int, endpoint: str) -> bool:
        result = await self.db.execute(
            delete(NotificationPushSubscription).where(
                NotificationPushSubscription.user_id == user_id,
                NotificationPushSubscription.endpoint == endpoint,
            )
        )
        return bool(result.rowcount)


def _load_vapid_private_key(value: str) -> ec.EllipticCurvePrivateKey:
    value = (value or "").strip()
    if not value:
        raise ValueError("Cle VAPID privee absente")
    if value.startswith("-----BEGIN"):
        key = serialization.load_pem_private_key(value.encode("ascii"), password=None)
    else:
        raw = _b64url_decode(value)
        if len(raw) == 32:
            key = ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
        else:
            key = serialization.load_der_private_key(raw, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("Cle VAPID invalide")
    return key
