"""Tests des analyses sportives automatiques (matin / soir / sortie)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.notification import Notification
from app.models.sport import SportActivity, SportAnalysis, SportGarminConnection
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.sport_analysis_service import SportAnalysisService, run_sport_analysis_cycle


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
        '{"title": "Titre test", '
        '"notification": "Notif courte avec chiffres clés", '
        '"summary": "Resume test.", '
        '"content": "## Resume\\nAnalyse complete de test."}'
    )


async def _failing_generate(**kwargs):
    raise AIGatewayError("Aucun fournisseur IA disponible")


async def test_morning_analysis_is_created_once(db_session, auth_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    service = SportAnalysisService(db_session, auth_user)

    created, first = await service.analyze_morning()
    assert created is True
    assert first is not None
    assert first.analysis_type == "morning"
    assert first.dedupe_key.startswith("morning:")
    assert first.provider == "test-provider"
    assert first.content

    created_again, second = await service.analyze_morning()
    assert created_again is False
    assert second is not None
    assert second.id == first.id

    rows = (await db_session.execute(select(SportAnalysis))).scalars().all()
    assert len(rows) == 1


async def test_evening_analysis_and_plain_text_fallback(db_session, auth_user, monkeypatch):
    async def plain_text_generate(**kwargs):
        return _FakeResponse("Analyse brute sans JSON.")

    monkeypatch.setattr(ai_gateway, "generate", plain_text_generate)
    service = SportAnalysisService(db_session, auth_user)

    created, row = await service.analyze_evening()
    assert created is True
    assert row.analysis_type == "evening"
    assert row.content == "Analyse brute sans JSON."


async def test_gateway_failure_creates_no_analysis(db_session, auth_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _failing_generate)
    service = SportAnalysisService(db_session, auth_user)

    created, row = await service.analyze_morning()
    assert created is False
    assert row is None

    rows = (await db_session.execute(select(SportAnalysis))).scalars().all()
    assert rows == []


async def test_analysis_creates_phone_notification(db_session, auth_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    service = SportAnalysisService(db_session, auth_user)

    created, row = await service.analyze_morning()
    assert created is True
    assert row.notification_sent is True

    notifications = (
        await db_session.execute(select(Notification).where(Notification.user_id == auth_user.id))
    ).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].category == "sport_analysis"
    assert notifications[0].data_json.get("url") == "/sport/analyses"


async def _make_activity(db_session, athlete_id, *, created_delta, started_delta, duration=1800):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    activity = SportActivity(
        athlete_id=athlete_id,
        sport_type="running",
        started_at=now - started_delta,
        duration_seconds=duration,
        distance_m=10000,
        source_type="garmin",
        created_at=now - created_delta,
    )
    db_session.add(activity)
    await db_session.commit()
    return activity


async def test_activity_analysis_is_created_once(db_session, auth_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    service = SportAnalysisService(db_session, auth_user)
    athlete = await service.sport.get_or_create_athlete()
    activity = await _make_activity(
        db_session, athlete.id,
        created_delta=timedelta(minutes=20),
        started_delta=timedelta(minutes=30),
    )

    created, row = await service.analyze_activity(activity.id)
    assert created is True
    assert row.analysis_type == "activity"
    assert row.activity_id == activity.id

    created_again, same = await service.analyze_activity(activity.id)
    assert created_again is False
    assert same.id == row.id


async def test_recent_activities_respect_delay_and_history_window(db_session, auth_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    service = SportAnalysisService(db_session, auth_user)
    athlete = await service.sport.get_or_create_athlete()

    eligible = await _make_activity(
        db_session, athlete.id,
        created_delta=timedelta(minutes=20),
        started_delta=timedelta(minutes=30),
    )
    await _make_activity(
        db_session, athlete.id,
        created_delta=timedelta(minutes=5),
        started_delta=timedelta(minutes=40),
    )
    await _make_activity(
        db_session, athlete.id,
        created_delta=timedelta(days=5),
        started_delta=timedelta(days=5),
    )

    now = datetime.now(timezone.utc)
    created = await service.analyze_recent_activities(now)
    assert created == 1

    rows = (
        await db_session.execute(select(SportAnalysis).where(SportAnalysis.analysis_type == "activity"))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].activity_id == eligible.id

    # Deuxieme passe : rien de plus (idempotence).
    assert await service.analyze_recent_activities(now) == 0


async def test_running_activity_is_not_analyzed_before_its_end(db_session, auth_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    service = SportAnalysisService(db_session, auth_user)
    athlete = await service.sport.get_or_create_athlete()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    activity = SportActivity(
        athlete_id=athlete.id,
        sport_type="running",
        started_at=now - timedelta(minutes=35),
        duration_seconds=7200,  # terminee dans ~1h
        source_type="garmin",
        created_at=now - timedelta(minutes=30),
    )
    db_session.add(activity)
    await db_session.commit()

    created = await service.analyze_recent_activities(datetime.now(timezone.utc))
    assert created == 0


async def test_run_sport_analysis_cycle(db_session, auth_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    service = SportAnalysisService(db_session, auth_user)
    athlete = await service.sport.get_or_create_athlete()
    db_session.add(
        SportGarminConnection(
            athlete_id=athlete.id,
            garmin_email="athlete@example.com",
            encrypted_tokens="encrypted",
            status="connected",
        )
    )
    await db_session.commit()

    # 10:00 UTC = 12:00 Europe/Paris : le bilan du matin est du.
    morning_now = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    stats = await run_sport_analysis_cycle(db_session, morning_now)
    assert stats["status"] == "ok"
    assert stats["morning"] == 1
    assert stats["errors"] == 0

    stats_again = await run_sport_analysis_cycle(db_session, morning_now)
    assert stats_again["morning"] == 0

    # 21:00 UTC = 23:00 Europe/Paris : seule la soiree est due.
    evening_now = datetime(2026, 9, 27, 21, 0, tzinfo=timezone.utc)
    stats_evening = await run_sport_analysis_cycle(db_session, evening_now)
    assert stats_evening["evening"] == 1
    assert stats_evening["morning"] == 0

    rows = (await db_session.execute(select(SportAnalysis))).scalars().all()
    assert sorted(row.analysis_type for row in rows) == ["evening", "morning"]


async def test_run_sport_analysis_cycle_ignores_athletes_without_garmin(db_session, auth_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _failing_generate)
    service = SportAnalysisService(db_session, auth_user)
    await service.sport.get_or_create_athlete()

    stats = await run_sport_analysis_cycle(
        db_session, datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    )
    assert stats["morning"] == 0
    assert stats["errors"] == 0


async def test_sport_analyses_endpoint_requires_permission(client, auth_headers):
    response = await client.get("/sport/analyses", headers=auth_headers)
    assert response.status_code == 403


async def test_sport_analyses_endpoint_lists_analyses(client, admin_headers, db_session, admin_user, monkeypatch):
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    service = SportAnalysisService(db_session, admin_user)
    created, row = await service.analyze_morning()
    assert created is True

    listing = await client.get("/sport/analyses", headers=admin_headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["analysis_type"] == "morning"
    assert body["items"][0]["content"]

    detail = await client.get(f"/sport/analyses/{row.id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == row.id

    missing = await client.get("/sport/analyses/999999", headers=admin_headers)
    assert missing.status_code == 404

    # Sans authentification (nouveau client, sans cookie) : 401.
    from httpx import ASGITransport, AsyncClient

    from app.main import app as fastapi_app

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as fresh:
        anonymous = await fresh.get(f"/sport/analyses/{row.id}")
    assert anonymous.status_code == 401
