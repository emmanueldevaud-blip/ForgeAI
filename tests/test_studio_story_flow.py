"""Parcours Studio : story suggérée identifiée, refus/validation persistés, routes uniques.

Vérifie le parcours frontend -> API -> backend -> base de données
pour les stories suggérées du Community Manager.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.main import app
from app.models.sport import EditorialCalendarEntry, SportPublication
from tests.test_calendar_suggestions import _make_activity, _make_athlete, _make_strategy


async def _make_story_draft(db_session, user):
    """Publication V2 liée à une suggestion de story (source=suggestion)."""
    athlete = await _make_athlete(db_session, user)
    strategy = await _make_strategy(db_session, athlete)
    entry = EditorialCalendarEntry(
        strategy_id=strategy.id,
        date=datetime.now(UTC).date() + timedelta(days=1),
        topic="Souvenir de course",
        status="pending",
        content_type="story_souvenir",
        source="suggestion",
    )
    db_session.add(entry)
    await db_session.commit()
    pub = SportPublication(
        athlete_id=athlete.id,
        calendar_entry_id=entry.id,
        status="draft",
        created_from="calendar",
        title="Un souvenir",
        content="Texte de la story.",
        hashtags="#trail",
    )
    db_session.add(pub)
    await db_session.commit()
    return pub, entry


async def _make_v1_publication(db_session, user):
    """Publication V1 type Garmin : liée à une activité, sans entrée calendrier."""
    athlete = await _make_athlete(db_session, user)
    activity = await _make_activity(db_session, athlete, name="Sortie V1")
    pub = SportPublication(
        athlete_id=athlete.id,
        activity_id=activity.id,
        calendar_entry_id=None,
        status="validated",
        title="Publication V1",
        content="Contenu V1.",
        hashtags="#garmin",
        photo_id=None,
        visual_type="photo",
    )
    db_session.add(pub)
    await db_session.commit()
    return pub


class TestStudioStoryFlow:
    @pytest.mark.asyncio
    async def test_get_draft_exposes_suggestion_source_and_content_type(
        self, db_session, client, admin_headers, admin_user
    ):
        pub, _entry = await _make_story_draft(db_session, admin_user)

        response = await client.get(
            f"/community-manager/studio/draft/{pub.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["calendar_entry_id"] == pub.calendar_entry_id
        assert data["calendar_entry"]["source"] == "suggestion"
        assert data["calendar_entry"]["content_type"] == "story_souvenir"

    @pytest.mark.asyncio
    async def test_refuse_suggestion_persiste_en_base(
        self, db_session, client, admin_headers, admin_user
    ):
        _pub, entry = await _make_story_draft(db_session, admin_user)
        entry_id = entry.id

        response = await client.post(
            f"/community-manager/suggestions/{entry_id}/refuse",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "refused"

        db_session.expire_all()
        row = await db_session.execute(
            select(EditorialCalendarEntry).where(EditorialCalendarEntry.id == entry_id)
        )
        assert row.scalar_one().status == "refused"

    @pytest.mark.asyncio
    async def test_validate_story_persiste_en_base(
        self, db_session, client, admin_headers, admin_user
    ):
        pub, _entry = await _make_story_draft(db_session, admin_user)
        pub_id = pub.id

        response = await client.post(
            f"/community-manager/studio/draft/{pub_id}/validate",
            json={"confirm": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "validated"

        db_session.expire_all()
        row = await db_session.execute(
            select(SportPublication).where(SportPublication.id == pub_id)
        )
        persisted = row.scalar_one()
        assert persisted.status == "validated"
        assert persisted.validated_at is not None

    @pytest.mark.asyncio
    async def test_publication_v1_garmin_sans_impact(
        self, db_session, client, admin_headers, admin_user
    ):
        pub = await _make_v1_publication(db_session, admin_user)
        pub_id = pub.id

        response = await client.get(
            f"/community-manager/studio/draft/{pub_id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["calendar_entry_id"] is None
        assert data["calendar_entry"] is None
        assert data["status"] == "validated"

        validate_response = await client.post(
            f"/community-manager/studio/draft/{pub_id}/validate",
            json={"confirm": True},
            headers=admin_headers,
        )
        assert validate_response.status_code == 200

        db_session.expire_all()
        row = await db_session.execute(
            select(SportPublication).where(SportPublication.id == pub_id)
        )
        assert row.scalar_one().status == "validated"


class TestStudioRoutes:
    def test_post_preview_route_unique(self):
        """POST /studio/draft/{id}/preview doit être déclaré une seule fois."""
        paths = app.openapi()["paths"]
        preview_paths = [
            path
            for path in paths
            if path.endswith("/studio/draft/{publication_id}/preview")
        ]
        assert len(preview_paths) == 1, (
            f"Route preview en doublon : {len(preview_paths)} déclarations"
        )
        assert "post" in paths[preview_paths[0]]
