"""Tests de l'endpoint Story audio-proposals (présélection IA par photos)."""

from types import SimpleNamespace

import pytest

from app.api.community_manager import suggest_story_audio_proposals
import app.services.community_manager.ig_music as ig_music
from app.services.community_manager.ig_music import normalize_audio_result


class FakeOrchestrator:
    def __init__(self, draft):
        self.db = object()
        self.current_user = SimpleNamespace(id=1)
        self._draft = draft
        self.get_calls = []

    async def get_draft(self, draft_id):
        self.get_calls.append(draft_id)
        return self._draft if draft_id == 42 else None


@pytest.fixture
def music_calls(monkeypatch):
    """Remplace les appels IA/Meta par des stubs déterministes."""
    stubs = {"pick": None, "search": None}

    async def pick(db, current_user, photo_ids, **kwargs):
        assert stubs["pick"] is not None, "pick_audio_for_photos_bounded non stubé"
        return await stubs["pick"](db, current_user, photo_ids, **kwargs)

    async def search(db, query, limit=10):
        assert stubs["search"] is not None, "search_ig_audio non stubé"
        return await stubs["search"](db, query, limit=limit)

    monkeypatch.setattr(ig_music, "pick_audio_for_photos_bounded", pick)
    monkeypatch.setattr(ig_music, "search_ig_audio", search)
    return stubs


@pytest.mark.asyncio
async def test_story_proposals_use_selected_photos(music_calls):
    captured = {}

    async def pick(db, current_user, photo_ids, **kwargs):
        captured.update(
            db=db,
            current_user=current_user,
            photo_ids=photo_ids,
            title=kwargs.get("title"),
            hashtags=kwargs.get("hashtags"),
        )
        return {
            "suggestions": [{
                "audio_id": "ai1",
                "title": "Photo Mix",
                "display_artist": "IA",
                "duration_in_ms": 120000,
            }],
        }

    music_calls["pick"] = pick
    draft = SimpleNamespace(
        selected_asset_ids=[11, "12", 11, "invalide"],
        caption="Trail du matin",
        hashtags="#trail",
    )
    orchestrator = FakeOrchestrator(draft)

    result = await suggest_story_audio_proposals(42, orchestrator)

    assert orchestrator.get_calls == [42]
    assert captured["photo_ids"] == [11, 12]
    assert captured["db"] is orchestrator.db
    assert captured["current_user"] is orchestrator.current_user
    assert captured["title"] == "Trail du matin"
    assert captured["hashtags"] == "#trail"
    assert result["items"][0]["audio_id"] == "ai1"
    assert result["items"][0]["source"] == "instagram"
    assert result["items"][0]["status"] == "available_on_meta"
    assert "Analyse IA" in result["reason"]
    assert result["local_render"] is False


def test_normalize_audio_result_separates_audio_and_platform_page():
    item = {
        "audio_id": "a1",
        "download_url": "https://scontent.example/preview.mp3",
        "on_platform_audio_preview_link": "https://www.instagram.com/reel/abc/",
    }
    out = normalize_audio_result(item)
    assert out["preview_link"] == "https://scontent.example/preview.mp3"
    assert out["platform_preview_link"] == "https://www.instagram.com/reel/abc/"


def test_normalize_audio_result_never_uses_instagram_page_as_audio():
    out = normalize_audio_result({
        "audio_id": "a2",
        "on_platform_audio_preview_link": "https://www.instagram.com/reel/abc/",
    })
    assert "preview_link" not in out
    assert out["platform_preview_link"] == "https://www.instagram.com/reel/abc/"


@pytest.mark.asyncio
async def test_story_proposals_without_photo_are_empty(music_calls):
    async def pick(*args, **kwargs):
        raise AssertionError("Aucun appel IA attendu sans photo")

    music_calls["pick"] = pick
    result = await suggest_story_audio_proposals(
        42, FakeOrchestrator(SimpleNamespace(selected_asset_ids=[], caption="", hashtags=None)),
    )

    assert result["items"] == []
    assert result["eligible_count"] == 0
    assert "Aucune photo" in result["reason"]


@pytest.mark.asyncio
async def test_story_proposals_fallback_is_explicit(music_calls):
    queries = []

    async def pick(*args, **kwargs):
        return None

    async def search(db, query, limit=10):
        queries.append(query)
        return [{"audio_id": "fb1", "title": "Catalogue", "display_artist": "Meta"}]

    music_calls["pick"] = pick
    music_calls["search"] = search
    result = await suggest_story_audio_proposals(
        42,
        FakeOrchestrator(SimpleNamespace(
            selected_asset_ids=[11], caption="Trail du matin", hashtags="#trail",
        )),
    )

    assert queries[0] == "Trail du matin"
    assert result["items"][0]["audio_id"] == "fb1"
    assert "Repli catalogue" in result["reason"]
