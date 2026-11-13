"""Tests de la refonte Community Manager : calendrier, suggestions, Garmin."""

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.module import Module, ModuleConfig, ModuleStatus
from app.models.photo import Photo
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
from app.services.ai_gateway import AIGatewayError, ai_gateway


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


# ============================================================
# Studio : régénération d'une publication V2 (sans activité liée)
# ============================================================

class TestRegenerateCalendarPublication:
    """Reprise après échec IA pour une publication créée depuis le calendrier.

    Ces publications ont calendar_entry_id mais activity_id NULL :
    la régénération ne doit pas renvoyer « Publication introuvable ».
    """

    @staticmethod
    async def _make_calendar_pub(db_session, user):
        athlete = await _make_athlete(db_session, user)
        strategy = await _make_strategy(db_session, athlete)
        entry = EditorialCalendarEntry(
            strategy_id=strategy.id,
            date=date.today() + timedelta(days=1),
            topic="Sortie longue en montagne",
            status="planifié",
            content_type="publication_sportive",
            source="manuel",
        )
        db_session.add(entry)
        await db_session.commit()
        pub = SportPublication(
            athlete_id=athlete.id,
            calendar_entry_id=entry.id,
            status="draft",
            created_from="calendar",
        )
        db_session.add(pub)
        await db_session.commit()
        return pub

    @pytest.mark.asyncio
    async def test_regenerate_returns_pub_with_content(self, db_session, auth_user, monkeypatch):
        async def fake_generate(**kwargs):
            class FakeResp:
                text = (
                    '{"proposals": ['
                    '{"title": "T1", "content": "Texte 1.", "hashtags": "#run"},'
                    '{"title": "T2", "content": "Texte 2.", "hashtags": "#trail"},'
                    '{"title": "T3", "content": "Texte 3.", "hashtags": "#sport"}'
                    ']}'
                )
            return FakeResp()

        monkeypatch.setattr(ai_gateway, "generate", fake_generate)
        pub = await self._make_calendar_pub(db_session, auth_user)

        service = SportGarminConnectService(db_session)
        result = await service.regenerate_publication_content(pub.id, auth_user)

        assert result is not None
        assert result.id == pub.id
        assert result.error_message is None
        assert len(result.proposals) == 3

    @pytest.mark.asyncio
    async def test_regenerate_ai_failure_still_returns_pub(self, db_session, auth_user, monkeypatch):
        async def failing_generate(**kwargs):
            raise AIGatewayError("Aucun fournisseur IA disponible")

        monkeypatch.setattr(ai_gateway, "generate", failing_generate)
        pub = await self._make_calendar_pub(db_session, auth_user)

        service = SportGarminConnectService(db_session)
        result = await service.regenerate_publication_content(pub.id, auth_user)

        # La publication reste récupérable : l'endpoint doit répondre et non404
        assert result is not None
        assert result.error_message


    @pytest.mark.asyncio
    async def test_regenerate_preserves_custom_params(self, db_session, auth_user, monkeypatch):
        """Une publication V2 personnalisée conserve styles, ton, consignes et visuel
        après régénération (seul le contenu texte/propositions est régénéré)."""
        async def fake_generate(**kwargs):
            class FakeResp:
                text = (
                    '{"proposals": ['
                    '{"title": "N1", "content": "Nouveau texte 1.", "hashtags": "#new1"},'
                    '{"title": "N2", "content": "Nouveau texte 2.", "hashtags": "#new2"},'
                    '{"title": "N3", "content": "Nouveau texte 3.", "hashtags": "#new3"}'
                    ']}'
                )
            return FakeResp()

        monkeypatch.setattr(ai_gateway, "generate", fake_generate)
        pub = await self._make_calendar_pub(db_session, auth_user)

        photo = Photo(
            owner_id=auth_user.id,
            original_filename="paysage.jpg",
            storage_path="2026/11/paysage.jpg",
            mime_type="image/jpeg",
            taken_at=datetime.now(timezone.utc),
            content_hash="a" * 64,
        )
        db_session.add(photo)
        await db_session.commit()

        # Personnalisation type Studio
        pub.styles = ["story"]
        pub.custom_instructions = "Ton décontracté, phrases courtes"
        pub.tone_used = "humor"
        pub.visual_type = "reel"
        pub.photo_id = photo.id
        pub.title_locked = True
        pub.content_locked = True
        await db_session.commit()

        service = SportGarminConnectService(db_session)
        result = await service.regenerate_publication_content(pub.id, auth_user)

        assert result is not None
        # Paramètres et style conservés
        assert result.styles == ["story"]
        assert result.custom_instructions == "Ton décontracté, phrases courtes"
        assert result.tone_used == "humor"
        assert result.visual_type == "reel"
        assert result.photo_id == photo.id
        assert result.title_locked is True
        assert result.content_locked is True
        # Contenu régénéré (c'est le but du bouton)
        assert len(result.proposals) == 3
        assert result.proposals[0]["title"] == "N1"
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_regenerate_ai_failure_preserves_existing_content(self, db_session, auth_user, monkeypatch):
        """Un échec IA enregistre l'erreur sans écraser le contenu existant du brouillon."""
        async def fake_generate(**kwargs):
            class FakeResp:
                text = (
                    '{"proposals": ['
                    '{"title": "T1", "content": "Texte 1.", "hashtags": "#run"},'
                    '{"title": "T2", "content": "Texte 2.", "hashtags": "#trail"},'
                    '{"title": "T3", "content": "Texte 3.", "hashtags": "#sport"}'
                    ']}'
                )
            return FakeResp()

        monkeypatch.setattr(ai_gateway, "generate", fake_generate)
        pub = await self._make_calendar_pub(db_session, auth_user)
        pub.styles = ["story"]
        pub.custom_instructions = "Ton décontracté"
        await db_session.commit()

        service = SportGarminConnectService(db_session)
        ok = await service.regenerate_publication_content(pub.id, auth_user)
        assert ok is not None and len(ok.proposals) == 3
        before_proposals = list(ok.proposals)
        before_content = ok.content
        before_title = ok.title
        before_hashtags = ok.hashtags

        # Échec IA à la régénération suivante
        async def failing_generate(**kwargs):
            raise AIGatewayError("Aucun fournisseur IA disponible")

        monkeypatch.setattr(ai_gateway, "generate", failing_generate)
        result = await service.regenerate_publication_content(pub.id, auth_user)

        # L'erreur est enregistrée...
        assert result is not None
        assert result.error_message
        # ...sans écraser le contenu existant
        assert result.proposals == before_proposals
        assert result.content == before_content
        assert result.title == before_title
        assert result.hashtags == before_hashtags
        # ...ni les paramètres
        assert result.styles == ["story"]
        assert result.custom_instructions == "Ton décontracté"
