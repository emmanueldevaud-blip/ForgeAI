"""Tests des publications Instagram (module Sport)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.sport import SportActivity, SportPublication
from app.schemas.sport import SportActivityCreate
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.sport import SportService
from app.schemas.sport import SportPublicationSettingsUpdate
from app.services.sport_publications import SportPublicationService

class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.provider_used = "test-provider"
        self.model_used = "test-model"
        self.fallback_used = False

async def _fake_generate(**kwargs):
    assert kwargs.get("prompt")
    assert kwargs.get("system_prompt")
    return _FakeResponse(
        '{"proposals": ['
        '{"title": "T1", "content": "Sortie de 10 km en 50 min.", "hashtags": "#trail #sport"},'
        '{"title": "T2", "content": "Belle sortie ce matin.", "hashtags": "#running"},'
        '{"title": "T3", "content": "Court et percutant.", "hashtags": "#run"}'
        ']}'
    )

async def _failing_generate(**kwargs):
    raise AIGatewayError("Aucun fournisseur IA disponible")

async def _make_activity(db_session, user):
    service = SportService(db_session, user)
    data = SportActivityCreate(
        sport_type="trail",
        activity_name="Sortie test",
        started_at=datetime.now(timezone.utc),
        duration_seconds=3000,
        distance_m=10000,
        elevation_gain_m=350,
        elevation_loss_m=320,
        avg_heart_rate=145,
        calories=600,
    )
    activity = await service.create_activity(data)
    await db_session.commit()
    # reload id
    res = await db_session.execute(select(SportActivity).where(SportActivity.activity_name == "Sortie test"))
    return res.scalars().first()

# --------------------------------------------------------------------------- #
# Detection + notifications
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_publication_notification_toggle(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    svc = SportPublicationService(db_session, admin_user)
    # desactive
    await svc.update_settings(SportPublicationSettingsUpdate(notifications_enabled=False))
    sent = await svc.notify_new_activities()
    assert sent == 0

    # reactive + activite
    await svc.update_settings(SportPublicationSettingsUpdate(notifications_enabled=True))
    act = await _make_activity(db_session, admin_user)
    sent = await svc.notify_new_activities()
    assert sent >= 1

    # second appel : pas de doublon (watermark)
    sent2 = await svc.notify_new_activities()
    assert sent2 == 0

# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_generate_three_proposals(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["stats"]))
    assert pub is not None
    assert len(pub.proposals) == 3
    assert pub.proposals[0]["title"] == "T1"
    assert pub.status == "draft"

@pytest.mark.asyncio
async def test_no_duplicate_publication_per_activity(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    p1 = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["stats"]))
    p2 = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["humor"]))
    assert p1.id == p2.id
    rows = (await db_session.execute(select(SportPublication).where(SportPublication.activity_id == act.id))).scalars().all()
    assert len(rows) == 1

@pytest.mark.asyncio
async def test_each_style_and_mix(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    for style in ["humor", "stats", "motivation", "inspiring", "story", "ultra", "short"]:
        pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=[style]))
        assert pub is not None
        assert style in (pub.styles or [])
    # mix
    pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["mix", "stats", "humor"]))
    assert "mix" in (pub.styles or [])

@pytest.mark.asyncio
async def test_custom_style(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["custom"], custom_instructions="Ton drole"))
    assert pub.custom_instructions == "Ton drole"

@pytest.mark.asyncio
async def test_change_tone_regenerate(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    await svc.generate(act.id, SportPublicationGenerateRequest(styles=["stats"]))
    pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["humor"], regenerate=True))
    assert "humor" in (pub.styles or [])

@pytest.mark.asyncio
async def test_missing_stats_handled(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    service = SportService(db_session, admin_user)
    from app.schemas.sport import SportActivityCreate
    data = SportActivityCreate(
        sport_type="walk",
        activity_name="Marche",
        started_at=datetime.now(timezone.utc),
        duration_seconds=600,
    )
    activity = await service.create_activity(data)
    await db_session.commit()
    res = await db_session.execute(select(SportActivity).where(SportActivity.activity_name == "Marche"))
    act = res.scalars().first()
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["stats"]))
    assert pub is not None
    assert len(pub.proposals) == 3

@pytest.mark.asyncio
async def test_ai_error_raises(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _failing_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    with pytest.raises(Exception):
        await svc.generate(act.id, SportPublicationGenerateRequest(styles=["stats"]))

# --------------------------------------------------------------------------- #
# Edit / draft / validation
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_edit_text_and_photo(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest, SportPublicationUpdate
    pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["stats"]))
    updated = await svc.update(pub.id, SportPublicationUpdate(title="Nouveau", content="Texte modifie", hashtags="#x", photo_id=None))
    assert updated.title == "Nouveau"
    assert updated.content == "Texte modifie"
    assert updated.hashtags == "#x"

@pytest.mark.asyncio
async def test_validation_required(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["stats"]))
    # vide le contenu
    from app.schemas.sport import SportPublicationUpdate
    await svc.update(pub.id, SportPublicationUpdate(content=""))
    with pytest.raises(ValueError):
        await svc.validate(pub.id)

@pytest.mark.asyncio
async def test_draft_then_validate_then_share(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    act = await _make_activity(db_session, admin_user)
    svc = SportPublicationService(db_session, admin_user)
    from app.schemas.sport import SportPublicationGenerateRequest
    pub = await svc.generate(act.id, SportPublicationGenerateRequest(styles=["stats"]))
    v = await svc.validate(pub.id)
    assert v.status == "validated"
    s = await svc.mark_shared(v.id)
    assert s.status == "shared"
    assert s.shared_at is not None

# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_rbac_publications(client, auth_headers):
    r = await client.get("/sport/publications", headers=auth_headers)
    assert r.status_code == 403
    r2 = await client.get("/sport/publications/styles", headers=auth_headers)
    assert r2.status_code == 403

@pytest.mark.asyncio
async def test_rbac_publications_admin(client, admin_headers):
    r = await client.get("/sport/publications/styles", headers=admin_headers)
    assert r.status_code == 200
    assert "styles" in r.json()

# --------------------------------------------------------------------------- #
# API flow
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_api_generate_flow(client, admin_headers, db_session, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    # cree une activite
    from app.schemas.sport import SportActivityCreate
    await client.post("/sport/activities", json={
        "sport_type": "trail", "activity_name": "API test", "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 1200, "distance_m": 5000,
    }, headers=admin_headers)
    res = await client.get("/sport/activities", headers=admin_headers)
    act_id = res.json()["items"][0]["id"]
    gen = await client.post(f"/sport/publications/activity/{act_id}/generate", json={"styles": ["stats"]}, headers=admin_headers)
    assert gen.status_code == 200
    assert len(gen.json()["proposals"]) == 3
    pub_id = gen.json()["id"]
    # update
    up = await client.patch(f"/sport/publications/{pub_id}", json={"content": "Texte final", "title": "Titre final"}, headers=admin_headers)
    assert up.status_code == 200
    assert up.json()["content"] == "Texte final"
    # validate
    val = await client.post(f"/sport/publications/{pub_id}/validate", json={}, headers=admin_headers)
    assert val.status_code == 200
    assert val.json()["status"] == "validated"
    # settings
    st = await client.get("/sport/publications/settings", headers=admin_headers)
    assert st.status_code == 200
    assert st.json()["last_styles"] == ["stats"]
