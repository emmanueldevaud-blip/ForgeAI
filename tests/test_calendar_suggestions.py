"""Tests de la refonte Community Manager : calendrier, suggestions, Garmin."""

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.module import Module, ModuleConfig, ModuleStatus
from app.models.sport import (
    CommunityManagerStrategy,
    EditorialCalendarEntry,
    SportActivity,
    SportAthlete,
    SportPublication,
)
from app.models.user import User
from app.services.community_manager.suggestions import EditorialSuggestionService
from app.services.garmin import SportGarminConnectService
from app.services.ai_gateway import ai_gateway


# ============================================================
# Helpers
# ============================================================

async def _make_athlete(db_session, user):
    athlete = SportAthlete(user_id=user.id)
    db_session.add(athlete)
    await db_session.commit()
    return athlete


async def _make_strategy(db_session, athlete):
    # S'assurer que le module administration existe
    result = await db_session.execute(select(Module).where(Module.code == "administration"))
    module = result.scalar_one_or_none()
    if module is None:
        module = Module(
            code="administration",
            name="Administration",
            description="Administration",
            icon="settings",
            order=1000,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/administration",
            component_path="Administration",
            is_core=True,
        )
        db_session.add(module)
        await db_session.commit()

    strategy = CommunityManagerStrategy(
        athlete_id=athlete.id,
        brand_identity="Marque test",
        tone=["inspiration"],
        target_audience="Coureurs",
        objectives=["engagement"],
        themes=["running", "training"],
        frequency=3,
        networks=["instagram"],
        rules=[],
        forbidden_topics=[],
    )
    db_session.add(strategy)
    await db_session.commit()
    return strategy


async def _make_activity(db_session, athlete, name="Sortie test", days_ago=0):
    act = SportActivity(
        athlete_id=athlete.id,
        external_id=f"garmin-ext-{athlete.id}-{days_ago}-{name}",
        activity_name=name,
        sport_type="running",
        started_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        duration_seconds=3600,
        distance_m=10000,
        elevation_gain_m=200,
        source_type="garmin",
    )
    db_session.add(act)
    await db_session.commit()
    return act


# ============================================================
# Suggestions : idempotence 3/semaine
# ============================================================

class TestSuggestionsIdempotence:
    @pytest.mark.asyncio
    async def test_generate_creates_exactly_three(self, db_session, auth_user, monkeypatch):
        athlete = await _make_athlete(db_session, auth_user)
        await _make_strategy(db_session, athlete)

        # Mock de l'IA pour éviter les appels réseau
        async def fake_generate(**kwargs):
            class FakeResp:
                text = '{"suggestions": ['
                text += '{"title": "Souvenir 1", "objectif": "engagement", "justification": "Test 1", "hashtags": "#test1"},'
                text += '{"title": "Édito 1", "objectif": "visibility", "justification": "Test 2", "hashtags": "#test2"},'
                text += '{"title": "Souvenir 2", "objectif": "brand_awareness", "justification": "Test 3", "hashtags": "#test3"}'
                text += ']}'
            return FakeResp()

        monkeypatch.setattr(ai_gateway, "generate", fake_generate)

        service = EditorialSuggestionService(db_session, auth_user)
        result = await service.generate_weekly_suggestions()

        assert len(result["suggestions"]) == 3
        ids = [s["id"] for s in result["suggestions"]]
        assert len(set(ids)) == 3

    @pytest.mark.asyncio
    async def test_generate_idempotent_second_call(self, db_session, auth_user):
        athlete = await _make_athlete(db_session, auth_user)
        await _make_strategy(db_session, athlete)

        service = EditorialSuggestionService(db_session, auth_user)
        r1 = await service.generate_weekly_suggestions()
        r2 = await service.generate_weekly_suggestions()

        assert len(r1["suggestions"]) == 3
        assert len(r2["suggestions"]) == 3
        # Même identifiants (idempotent)
        assert [s["id"] for s in r1["suggestions"]] == [s["id"] for s in r2["suggestions"]]

    @pytest.mark.asyncio
    async def test_accept_suggestion(self, db_session, auth_user):
        athlete = await _make_athlete(db_session, auth_user)
        await _make_strategy(db_session, athlete)

        service = EditorialSuggestionService(db_session, auth_user)
        result = await service.generate_weekly_suggestions()
        entry_id = result["suggestions"][0]["id"]

        entry = await service.accept_suggestion(entry_id)
        assert entry is not None
        assert entry.status == "accepted"

    @pytest.mark.asyncio
    async def test_refuse_suggestion_keeps_history(self, db_session, auth_user):
        athlete = await _make_athlete(db_session, auth_user)
        await _make_strategy(db_session, athlete)

        service = EditorialSuggestionService(db_session, auth_user)
        result = await service.generate_weekly_suggestions()
        entry_id = result["suggestions"][0]["id"]

        entry = await service.refuse_suggestion(entry_id)
        assert entry is not None
        assert entry.status == "refused"

        # L'entrée doit encore exister dans la base
        from sqlalchemy import select as sa_select
        res = await db_session.execute(sa_select(EditorialCalendarEntry).where(EditorialCalendarEntry.id == entry_id))
        assert res.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_reschedule_suggestion(self, db_session, auth_user):
        athlete = await _make_athlete(db_session, auth_user)
        await _make_strategy(db_session, athlete)

        service = EditorialSuggestionService(db_session, auth_user)
        result = await service.generate_weekly_suggestions()
        entry_id = result["suggestions"][0]["id"]
        new_date = date.today() + timedelta(days=10)

        entry = await service.reschedule_suggestion(entry_id, new_date)
        assert entry is not None
        assert entry.date == new_date
        assert entry.status == "pending"


# ============================================================
# Garmin : une publication par activité (idempotence)
# ============================================================

class TestGarminPublicationIdempotence:
    @pytest.mark.asyncio
    async def test_one_activity_one_publication(self, db_session, auth_user):
        athlete = await _make_athlete(db_session, auth_user)
        await _make_strategy(db_session, athlete)
        act = await _make_activity(db_session, athlete, "Sortie trail", days_ago=0)

        service = SportGarminConnectService(db_session)
        created = await service._create_publication_records_for_new_activities(athlete)

        assert len(created) == 1
        activity, entry, pub = created[0]
        assert activity.id == act.id
        assert entry.source_activity_id == act.id
        assert entry.source == "garmin"
        assert entry.content_type == "publication_sportive"
        assert pub.activity_id == act.id
        assert pub.calendar_entry_id == entry.id
        assert pub.status == "draft"
        assert pub.source == "garmin"

    @pytest.mark.asyncio
    async def test_second_sync_no_duplicate(self, db_session, auth_user):
        athlete = await _make_athlete(db_session, auth_user)
        await _make_strategy(db_session, athlete)
        act = await _make_activity(db_session, athlete, "Sortie trail", days_ago=0)

        service = SportGarminConnectService(db_session)
        created1 = await service._create_publication_records_for_new_activities(athlete)
        created2 = await service._create_publication_records_for_new_activities(athlete)

        assert len(created1) == 1
        assert len(created2) == 0  # Idempotent : rien de nouveau

    @pytest.mark.asyncio
    async def test_two_activities_two_publications(self, db_session, auth_user):
        athlete = await _make_athlete(db_session, auth_user)
        await _make_strategy(db_session, athlete)
        await _make_activity(db_session, athlete, "Sortie A", days_ago=0)
        await _make_activity(db_session, athlete, "Sortie B", days_ago=1)

        service = SportGarminConnectService(db_session)
        created = await service._create_publication_records_for_new_activities(athlete)

        assert len(created) == 2
