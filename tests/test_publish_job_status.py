"""Statut réel des jobs de publication (Story slide + Studio classique).

Le POST de publication ne renvoie que « queued » : si GET /publish-job casse
sur un payload Story (pas de publication_id), le front ne peut jamais savoir
si Meta a publié ou refusé. Ces tests verrouillent le contrat de polling.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.community_manager import get_publish_job


class FakeDb:
    def __init__(self, objects):
        self.objects = objects

    async def get(self, model, key):
        return self.objects.get((model.__name__, str(key)))


class FakePubService:
    def __init__(self, publication=None):
        self.publication = publication

    async def get_publication(self, publication_id):
        return self.publication if str(publication_id) == "77" else None


def make_service(payload, *, draft=None, publication=None):
    job = SimpleNamespace(
        id="job-1",
        status="done",
        error=None,
        attempts=1,
        progress=100,
        payload_json=payload,
    )
    objects = {("PhotoJob", "job-1"): job}
    if draft is not None:
        objects[("StoryDraft", str(draft.id))] = draft
    db = FakeDb(objects)
    return job, SimpleNamespace(
        db=db,
        current_user=SimpleNamespace(id=1),
        pub_service=FakePubService(publication),
    )


@pytest.mark.asyncio
async def test_story_slide_job_reports_real_meta_result():
    """Un job Story n'a pas de publication_id : le_endpoint ne doit pas 500."""
    draft = SimpleNamespace(
        id=42,
        status="published",
        error_message=None,
        publication_results=[{
            "slide_index": 0,
            "media_id": "ig-media-1",
            "permalink": "https://instagram.com/p/abc/",
        }],
    )
    _, service = make_service({
        "kind": "story_slide_publish",
        "draft_id": 42,
        "slide_index": 0,
        "photo_id": 11,
        "user_id": 1,
    }, draft=draft)

    result = await get_publish_job("job-1", service)

    assert result["kind"] == "story_slide_publish"
    assert result["publication_status"] == "published"
    assert result["instagram_media_id"] == "ig-media-1"
    assert result["instagram_permalink"].endswith("/p/abc/")


@pytest.mark.asyncio
async def test_story_slide_job_reports_facebook_result():
    """Un job Facebook expose son propre média sans usurper le champ Instagram."""
    draft = SimpleNamespace(
        id=42,
        status="published",
        error_message=None,
        publication_results=[{
            "slide_index": 0,
            "platform": "facebook",
            "media_id": "fb-story-1",
            "permalink": "https://facebook.com/stories/1",
        }],
    )
    _, service = make_service({
        "kind": "story_slide_publish",
        "draft_id": 42,
        "slide_index": 0,
        "platform": "facebook",
        "expected_platforms": ["instagram", "facebook"],
        "photo_id": 11,
        "user_id": 1,
    }, draft=draft)

    result = await get_publish_job("job-1", service)

    assert result["platform"] == "facebook"
    assert result["media_id"] == "fb-story-1"
    assert result["facebook_media_id"] == "fb-story-1"
    assert result["instagram_media_id"] is None
    assert result["facebook_permalink"].endswith("/stories/1")


@pytest.mark.asyncio
async def test_story_slide_job_reports_failure():
    draft = SimpleNamespace(
        id=42,
        status="failed",
        error_message="Meta API: échec du container",
        publication_results=[],
    )
    job, service = make_service({
        "kind": "story_slide_publish",
        "draft_id": 42,
        "slide_index": 0,
        "user_id": 1,
    }, draft=draft)
    job.status = "failed"
    job.error = "RuntimeError: Meta API: échec du container"

    result = await get_publish_job("job-1", service)

    assert result["status"] == "failed"
    assert "échec du container" in result["error_message"]
    assert result["instagram_media_id"] is None


@pytest.mark.asyncio
async def test_classic_job_reports_publication_status():
    publication = SimpleNamespace(
        status="shared",
        error_message=None,
        instagram_media_id="ig-post-1",
        instagram_permalink="https://instagram.com/p/post/",
        shared_at=None,
    )
    _, service = make_service({
        "publication_id": 77,
        "user_id": 1,
    }, publication=publication)

    result = await get_publish_job("job-1", service)

    assert result["publication_status"] == "shared"
    assert result["instagram_media_id"] == "ig-post-1"


@pytest.mark.asyncio
async def test_publish_job_is_private():
    _, service = make_service({
        "kind": "story_slide_publish",
        "draft_id": 42,
        "slide_index": 0,
        "user_id": 999,
    })

    with pytest.raises(HTTPException) as exc:
        await get_publish_job("job-1", service)
    assert exc.value.status_code == 404
