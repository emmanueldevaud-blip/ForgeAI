"""Tests des notifications : chiffrement Web Push (RFC 8291) et API."""

from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from app.models.notification import Notification
from app.services.notification import _b64url_decode, _b64url_encode, encrypt_push_payload

# Vecteur de l'Appendix A / Section 5 du RFC 8291.
_PLAINTEXT = b"When I grow up, I want to be a watermelon"
_UA_PUBLIC = (
    "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcx"
    "aOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
)
_AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
_AUTH_SECRET = "BTBZMqHH6r4Tts7J_aSIgg"
_SALT = "DGv6ra1nlYgDCS1FRnbzlw"
_EXPECTED = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
    "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
    "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
)


def test_encrypt_push_payload_matches_rfc8291_vector():
    private_raw = _b64url_decode(_AS_PRIVATE)
    local_private = ec.derive_private_key(int.from_bytes(private_raw, "big"), ec.SECP256R1())

    sealed = encrypt_push_payload(
        _PLAINTEXT,
        _b64url_decode(_UA_PUBLIC),
        _b64url_decode(_AUTH_SECRET),
        local_private=local_private,
        salt=_b64url_decode(_SALT),
    )

    assert _b64url_encode(sealed) == _EXPECTED


def test_encrypt_push_payload_uses_random_salt_by_default():
    private_raw = _b64url_decode(_AS_PRIVATE)
    local_private = ec.derive_private_key(int.from_bytes(private_raw, "big"), ec.SECP256R1())

    first = encrypt_push_payload(
        _PLAINTEXT, _b64url_decode(_UA_PUBLIC), _b64url_decode(_AUTH_SECRET),
        local_private=local_private,
    )
    second = encrypt_push_payload(
        _PLAINTEXT, _b64url_decode(_UA_PUBLIC), _b64url_decode(_AUTH_SECRET),
        local_private=local_private,
    )

    assert first != second
    assert len(first) == len(second)
    # En-tete : salt (16) + record size (4) + idlen (1) + cle (65).
    assert len(first) == 86 + len(_PLAINTEXT) + 1 + 16


async def test_notifications_require_authentication(client):
    response = await client.get("/notifications")
    assert response.status_code == 401


async def test_notification_list_and_read_flow(client, auth_headers, db_session, auth_user):
    from app.services.notification import NotificationService

    await NotificationService(db_session).send(
        user_id=auth_user.id,
        title="Analyse du matin",
        message="Resume de la nuit.",
        category="sport_analysis",
        data={"url": "/sport/analyses", "analysis_id": 1},
    )
    await db_session.commit()

    listing = await client.get("/notifications", headers=auth_headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["unread_count"] == 1
    assert body["items"][0]["title"] == "Analyse du matin"
    assert body["items"][0]["data"]["url"] == "/sport/analyses"
    notification_id = body["items"][0]["id"]

    read = await client.post(f"/notifications/{notification_id}/read", headers=auth_headers)
    assert read.status_code == 200
    assert read.json()["is_read"] is True

    count = await client.get("/notifications/unread-count", headers=auth_headers)
    assert count.status_code == 200
    assert count.json()["count"] == 0

    missing = await client.post("/notifications/999999/read", headers=auth_headers)
    assert missing.status_code == 404


async def test_mark_all_notifications_read(client, auth_headers, db_session, auth_user):
    from app.services.notification import NotificationService

    service = NotificationService(db_session)
    await service.send(user_id=auth_user.id, title="N1", message="M1")
    await service.send(user_id=auth_user.id, title="N2", message="M2")
    await db_session.commit()

    response = await client.post("/notifications/read-all", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["count"] == 2

    count = await client.get("/notifications/unread-count", headers=auth_headers)
    assert count.json()["count"] == 0


async def test_push_subscription_lifecycle(client, auth_headers):
    subscribe = await client.post(
        "/notifications/push/subscribe",
        headers=auth_headers,
        json={
            "endpoint": "https://push.example.com/sub-1",
            "p256dh": "BMockedPublicKey",
            "auth": "MockedAuthSecret",
        },
    )
    assert subscribe.status_code == 200
    assert subscribe.json()["endpoint"] == "https://push.example.com/sub-1"

    # Re-abonnement du meme endpoint : mise a jour, pas de doublon.
    repeat = await client.post(
        "/notifications/push/subscribe",
        headers=auth_headers,
        json={
            "endpoint": "https://push.example.com/sub-1",
            "p256dh": "BMockedPublicKey2",
            "auth": "MockedAuthSecret2",
        },
    )
    assert repeat.status_code == 200

    unsubscribe = await client.post(
        "/notifications/push/unsubscribe",
        headers=auth_headers,
        json={"endpoint": "https://push.example.com/sub-1"},
    )
    assert unsubscribe.status_code == 200
    assert unsubscribe.json()["removed"] is True


async def test_vapid_public_key_endpoint(client):
    response = await client.get("/notifications/push/vapid-public-key")
    assert response.status_code == 200
    assert "publicKey" in response.json()


async def test_push_test_sends_to_own_subscriptions_only(client, auth_headers, db_session, auth_user):
    """Le test cree la notification pour l'utilisateur connecte (push best-effort)."""
    response = await client.post("/notifications/push/test", headers=auth_headers)
    assert response.status_code == 200
    # Sans abonnement actif : rien n'est delivré.
    assert response.json()["push_sent"] is False

    result = await db_session.execute(
        select(Notification).where(Notification.user_id == auth_user.id)
    )
    notification = result.scalars().first()
    assert notification is not None
    assert notification.title == "Test ForgeAI"
    assert notification.category == "system"
