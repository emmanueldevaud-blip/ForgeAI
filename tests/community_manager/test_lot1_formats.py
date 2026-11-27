"""Lot 1 — Programmation et formats (A04, A05, A06, A07).

Correctifs « honnêtes » : désactiver ce qui n'est pas exécutable, bloquer le
carrousel à la publication, aligner le contrat Story sur Instagram uniquement
et documenter la musique Story comme brouillon créatif non publié.

Ce fichier est additif : les 12 échecs A10 restent visibles tels quels.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.community_manager import (
    StoryDraftPublishRequest,
    publish_draft,
    publish_story_draft,
    schedule_draft,
)
from app.schemas.sport import PublicationPublishRequest
from app.services.community_manager.studio import (
    CAROUSEL_PUBLISH_BLOCKED_MESSAGE,
    CommunityManagerStudioService,
)


def _studio_service(pub):
    service = CommunityManagerStudioService(AsyncMock(spec=AsyncSession), MagicMock(id=1))
    service.pub_service.get_publication = AsyncMock(return_value=pub)
    return service


def _story_draft():
    return SimpleNamespace(
        id=7,
        status="awaiting_validation",
        design_documents=[{"format": {"platform": "instagram"}}],
        slides=[{"published_photo_id": 11}],
        caption="Story",
        hashtags="#trail",
        publication_results=[],
        published_at=None,
        current_user=SimpleNamespace(id=1),
    )


# ============================================================
# A04 — Programmation désactivée, pas de promesse mensongère
# ============================================================


async def test_schedule_endpoint_is_disabled_without_writing_status():
    """L'endpoint refuse explicitement la programmation (aucun worker ne la consomme)."""
    service = MagicMock()
    service.schedule_publication = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await schedule_draft(
            publication_id=12,
            scheduled_at=datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc),
            service=service,
        )

    assert exc_info.value.status_code == 503
    assert "désactivée" in exc_info.value.detail
    assert "worker" in exc_info.value.detail
    service.schedule_publication.assert_not_awaited()


def test_schedule_service_method_is_kept_for_future_scheduler():
    """Le code de service existe encore, mais n'est plus exposé (proposition documentée)."""
    service = CommunityManagerStudioService(AsyncMock(spec=AsyncSession), MagicMock(id=1))
    assert callable(service.schedule_publication)


# ============================================================
# A05 — Carrousel bloqué avant tout envoi à Meta
# ============================================================


def test_carousel_format_is_blocked_by_service_guard():
    pub = SimpleNamespace(
        id=3,
        visual_type="carousel",
        design={"carousel": [11, 12]},
        photo_id=11,
        status="draft",
    )
    service = _studio_service(pub)

    with pytest.raises(ValueError, match="carrousel"):
        service.assert_publishable_format(pub)


def test_single_photo_publication_still_allowed():
    """Non-régression : une photo unique reste publiable."""
    pub = SimpleNamespace(
        id=4,
        visual_type="photo",
        design={"carousel": [11]},
        photo_id=11,
        status="draft",
        content="Une photo",
        hashtags="",
        created_from="standalone",
    )
    service = _studio_service(pub)
    service.assert_publishable_format(pub)


async def test_validate_draft_rejects_carousel_without_changing_status():
    pub = SimpleNamespace(
        id=5,
        visual_type="carousel",
        design={"carousel": [11, 12]},
        photo_id=11,
        status="draft",
        content="Deux photos",
    )
    service = _studio_service(pub)

    with pytest.raises(ValueError) as exc_info:
        await service.validate_for_publication(5, MagicMock())

    assert str(exc_info.value) == CAROUSEL_PUBLISH_BLOCKED_MESSAGE
    assert pub.status == "draft"
    service.db.commit.assert_not_awaited()


async def test_publish_endpoint_blocks_carousel_before_enqueue():
    pub = SimpleNamespace(
        id=6,
        visual_type="carousel",
        design={"carousel": [11, 12]},
        photo_id=11,
        status="validated",
    )
    service = _studio_service(pub)

    with patch("app.services.photo.jobs.enqueue_job", new_callable=AsyncMock) as enqueue:
        with pytest.raises(HTTPException) as exc_info:
            await publish_draft(
                publication_id=6,
                data=PublicationPublishRequest(publication_id=6, confirm=True),
                background_tasks=BackgroundTasks(),
                service=service,
            )

    assert exc_info.value.status_code == 422
    assert "carrousel" in exc_info.value.detail
    enqueue.assert_not_awaited()


# ============================================================
# A06 — Une seule vérité : Stories Instagram uniquement
# ============================================================


def test_story_publish_schema_accepts_instagram_only():
    assert StoryDraftPublishRequest().platforms == ["instagram"]
    assert StoryDraftPublishRequest(platforms=["instagram"]).platforms == ["instagram"]
    for invalid in (["facebook"], ["both"], ["instagram", "facebook"]):
        with pytest.raises(ValidationError):
            StoryDraftPublishRequest(platforms=invalid)


async def test_story_publish_handler_still_rejects_other_platforms(monkeypatch):
    """Défense en profondeur si un appelant contourne la validation Pydantic."""
    orchestrator = MagicMock()
    orchestrator.get_draft = AsyncMock(return_value=_story_draft())
    orchestrator.db.commit = AsyncMock()
    orchestrator.current_user.id = 1

    enqueue = AsyncMock()
    monkeypatch.setattr("app.services.photo.jobs.enqueue_job", enqueue)
    monkeypatch.setattr("app.services.photo.jobs.run_pending_jobs_now", MagicMock())

    bad_request = StoryDraftPublishRequest.model_construct(platforms=["facebook"], confirm=True)
    with pytest.raises(HTTPException) as exc_info:
        await publish_story_draft(
            draft_id=7,
            data=bad_request,
            background_tasks=BackgroundTasks(),
            orchestrator=orchestrator,
        )

    assert exc_info.value.status_code == 422
    assert "Instagram uniquement" in exc_info.value.detail
    enqueue.assert_not_awaited()


async def test_story_publish_enqueues_instagram_job_without_multi_platform_payload(monkeypatch):
    draft = _story_draft()
    orchestrator = MagicMock()
    orchestrator.get_draft = AsyncMock(return_value=draft)
    orchestrator.db.commit = AsyncMock()
    orchestrator.current_user.id = 1

    enqueue = AsyncMock(return_value=SimpleNamespace(id="job-1"))
    monkeypatch.setattr("app.services.photo.jobs.enqueue_job", enqueue)
    monkeypatch.setattr("app.services.photo.jobs.run_pending_jobs_now", MagicMock())

    result = await publish_story_draft(
        draft_id=7,
        data=StoryDraftPublishRequest(platforms=["instagram"]),
        background_tasks=BackgroundTasks(),
        orchestrator=orchestrator,
    )

    payload = enqueue.await_args.kwargs["payload"]
    assert payload["kind"] == "story_slide_publish"
    assert "platforms" not in payload  # plus de contrat multi-plateforme mensonger
    assert "Instagram uniquement" in result["message"] or "brouillon créatif" in result["message"]


# ============================================================
# A07 — Musique Story : brouillon créatif, jamais transmis à Meta
# ============================================================


async def test_story_job_does_not_forward_audio_configuration_to_meta(monkeypatch):
    """Même si le draft porte une musique, le job Story n'invente pas de paramètre Meta."""
    from app.services.photo import jobs

    user = SimpleNamespace(id=1)
    draft = _story_draft()
    db = AsyncMock()
    db.get = AsyncMock(side_effect=[user, draft])
    db.commit = AsyncMock()

    meta = MagicMock()
    meta.resolve_publish_context = AsyncMock(
        return_value=SimpleNamespace(instagram_business_account_id="ig-1")
    )
    meta.publish_story = AsyncMock(return_value="media-1")
    meta.get_media_permalink = AsyncMock(return_value="https://instagram.com/story/1")
    monkeypatch.setattr("app.services.sport_instagram_publish.MetaPublishService", MagicMock(return_value=meta))

    media = MagicMock()
    media.prepare_media_for_publish = AsyncMock(
        return_value=SimpleNamespace(
            url="https://example.com/story.jpg",
            mime_type="image/jpeg",
            is_video=False,
        )
    )
    monkeypatch.setattr("app.services.sport_media_publish.MediaPublishService", MagicMock(return_value=media))

    await jobs._community_publish(
        db,
        None,
        {
            "kind": "story_slide_publish",
            "draft_id": 7,
            "slide_index": 0,
            "photo_id": 11,
            "user_id": 1,
            # Musique sélectionnée dans l'UI : donnée créative, pas un paramètre Meta.
            "audio_configuration": {"trackId": "cfg-1", "title": "Run Free"},
        },
    )

    meta.publish_story.assert_awaited_once()
    assert "audio_configuration" not in meta.publish_story.await_args.kwargs
    assert draft.publication_results[0]["platform"] == "instagram"
