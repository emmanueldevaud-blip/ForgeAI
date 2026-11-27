"""Lot 0 — Création publiable (A01, A03).

Tests ciblés sur la création serveur de brouillon standalone et sur les
suggestions Garmin ciblées par ``activity_id``. Ce fichier n'altère pas les
suites existantes (les échecs A10 restent visibles tels quels).
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sport import SportPublication
from app.models.user import User
from app.schemas.sport import PublicationDraftCreateRequest
from app.services.community_manager.studio import CommunityManagerStudioService


@pytest.fixture
def studio_service():
    db = AsyncMock(spec=AsyncSession)
    user = MagicMock(spec=User)
    user.id = 1
    return CommunityManagerStudioService(db, user)


@pytest.fixture
def athlete():
    mock = MagicMock()
    mock.id = 10
    return mock


# ============================================================
# A01 — Brouillon standalone côté serveur
# ============================================================


async def test_create_standalone_draft_service(studio_service, athlete):
    """Le service crée un SportPublication « standalone » sans entrée de calendrier."""
    studio_service._get_athlete_and_strategy = AsyncMock(
        return_value=(athlete, MagicMock())
    )

    pub = await studio_service.create_standalone_draft(
        PublicationDraftCreateRequest(visual_type="carousel")
    )

    assert isinstance(pub, SportPublication)
    assert pub.athlete_id == 10
    assert pub.status == "draft"
    assert pub.created_from == "standalone"
    assert pub.visual_type == "carousel"
    assert pub.calendar_entry_id is None
    assert pub.activity_id is None
    studio_service.db.add.assert_called_once_with(pub)
    studio_service.db.flush.assert_awaited_once()
    studio_service.db.commit.assert_awaited_once()
    # Régression MissingGreenlet : les colonnes `server_default` (created_at /
    # updated_at) restent expirées après le commit ; sans refresh, la réponse
    # Pydantic les lit en synchrone et renvoie 422 au lieu du brouillon créé.
    studio_service.db.refresh.assert_awaited_once_with(pub)


async def test_create_standalone_draft_requires_strategy(studio_service):
    """Sans stratégie éditoriale, la création échoue explicitement (ValueError → 422)."""
    studio_service._get_athlete_and_strategy = AsyncMock(
        side_effect=ValueError("Stratégie éditoriale non configurée")
    )

    with pytest.raises(ValueError, match="Stratégie"):
        await studio_service.create_standalone_draft(PublicationDraftCreateRequest())

    studio_service.db.add.assert_not_called()


def test_publication_draft_create_request_visual_type():
    """Seuls les types visuels Studio sont acceptés à la création."""
    from pydantic import ValidationError

    assert PublicationDraftCreateRequest(visual_type="reel").visual_type == "reel"
    with pytest.raises(ValidationError):
        PublicationDraftCreateRequest(visual_type="invalid")


# ============================================================
# A01 — Endpoint dédié
# ============================================================


def test_standalone_draft_route_registered():
    """L'endpoint POST /community-manager/studio/draft est exposé par le routeur."""
    from app.api.community_manager import router

    post_routes = [
        r for r in router.routes
        if getattr(r, "path", None) == "/community-manager/studio/draft"
        and "POST" in getattr(r, "methods", set())
    ]
    assert len(post_routes) == 1


async def test_create_standalone_draft_endpoint_success():
    """L'endpoint renvoie la publication créée (réponse Studio)."""
    from app.api.community_manager import create_standalone_draft
    from app.schemas.sport import PublicationDraftResponse

    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    pub = SportPublication(
        id=42,
        athlete_id=10,
        status="draft",
        created_from="standalone",
        visual_type="photo",
        styles=[],
        proposals=[],
        title=None,
        content=None,
        hashtags=None,
        photo_id=None,
        title_locked=False,
        content_locked=False,
        photo_locked=False,
        companion_video_status="none",
        created_at=now,
        updated_at=now,
    )
    service = MagicMock()
    service.create_standalone_draft = AsyncMock(return_value=pub)

    result = await create_standalone_draft(
        PublicationDraftCreateRequest(visual_type="photo"), service=service
    )

    assert isinstance(result, PublicationDraftResponse)
    assert result.id == 42
    assert result.status == "draft"
    service.create_standalone_draft.assert_awaited_once()


async def test_create_standalone_draft_endpoint_maps_errors():
    """ValueError → 422 (erreur métier), autre exception → 503 (indisponibilité)."""
    from fastapi import HTTPException

    from app.api.community_manager import create_standalone_draft

    data = PublicationDraftCreateRequest()

    service = MagicMock()
    service.create_standalone_draft = AsyncMock(
        side_effect=ValueError("Stratégie éditoriale non configurée")
    )
    with pytest.raises(HTTPException) as exc:
        await create_standalone_draft(data, service=service)
    assert exc.value.status_code == 422

    service = MagicMock()
    service.create_standalone_draft = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(HTTPException) as exc:
        await create_standalone_draft(data, service=service)
    assert exc.value.status_code == 503


# ============================================================
# A03 — Suggestions Garmin par activity_id
# ============================================================


def test_activity_suggested_photos_route_registered():
    """L'endpoint GET .../studio/activity/{activity_id}/suggested-photos est exposé."""
    from app.api.community_manager import router

    get_routes = [
        r for r in router.routes
        if getattr(r, "path", None)
        == "/community-manager/studio/activity/{activity_id}/suggested-photos"
        and "GET" in getattr(r, "methods", set())
    ]
    assert len(get_routes) == 1


async def test_get_suggested_photos_for_activity_unknown_activity(studio_service, athlete):
    """Une activité absente ou appartenant à un autre athlète → ValueError (422)."""
    studio_service._get_athlete_and_strategy = AsyncMock(
        return_value=(athlete, MagicMock())
    )
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    studio_service.db.execute = AsyncMock(return_value=result)

    with pytest.raises(ValueError, match="Activité Garmin introuvable"):
        await studio_service.get_suggested_photos_for_activity(999)


async def test_get_suggested_photos_for_activity_delegates_by_activity(
    studio_service, athlete
):
    """La date de l'activité pilote la recherche de photos suggérées."""
    studio_service._get_athlete_and_strategy = AsyncMock(
        return_value=(athlete, MagicMock())
    )
    activity = MagicMock()
    activity.started_at = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=activity)
    studio_service.db.execute = AsyncMock(return_value=result)
    studio_service._get_suggested_photos_for_date = AsyncMock(
        return_value=[{"id": 5, "is_current": False}]
    )

    photos = await studio_service.get_suggested_photos_for_activity(7, limit=5)

    studio_service._get_suggested_photos_for_date.assert_awaited_once_with(
        date(2026, 5, 4), limit=5
    )
    assert photos == [{"id": 5, "is_current": False}]


async def test_activity_suggested_photos_endpoint_maps_errors():
    """ValueError métier → 422 côté endpoint."""
    from fastapi import HTTPException

    from app.api.community_manager import get_suggested_photos_for_activity

    service = MagicMock()
    service.get_suggested_photos_for_activity = AsyncMock(
        side_effect=ValueError("Activité Garmin introuvable")
    )
    with pytest.raises(HTTPException) as exc:
        await get_suggested_photos_for_activity(activity_id=3, service=service)
    assert exc.value.status_code == 422
