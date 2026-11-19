"""Tests ciblés : musique Instagram choisie par IA au choix de la photo.

Couvre l'entrée image de l'AI Gateway (vision), l'orchestration
photo -> analyse -> recherche ig_audio -> choix -> persistance
design["ig_audio"].
"""

import json

import httpx
import pytest

from app.core.config import Settings
from app.services.ai_gateway import AIGateway, AINoProviderAvailable
from app.services.ai_gateway.models import MODEL_CATALOG, resolve_model
from app.services.community_manager import ig_music


def make_settings(**values):
    defaults = {
        "_env_file": None,
        "SECRET_KEY": "test-secret-key-test-secret-key-test",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "AI_MAX_RETRIES": 0,
        "AI_RETRY_BACKOFF_SECONDS": 0,
        "OPENCODE_ENABLED": False,
        "GROQ_ENABLED": False,
        "GROQ_API_KEY": "",
        "GEMINI_ENABLED": False,
        "GEMINI_API_KEY": "",
        "OPENROUTER_ENABLED": False,
        "OPENROUTER_API_KEY": "",
    }
    defaults.update(values)
    return Settings(**defaults)


def openai_response(content: str) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


# ============================================================
# AI Gateway : entrée image (vision)
# ============================================================

class TestGatewayVision:

    @pytest.mark.asyncio
    async def test_vision_generate_sends_image_content_block(self, monkeypatch):
        for var in ("AI_DEFAULT_MODEL", "GROQ_MODEL"):
            monkeypatch.delenv(var, raising=False)

        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200, json=openai_response('{"scene": "forêt"}'), request=request
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        gateway = AIGateway(
            settings=make_settings(GROQ_ENABLED=True, GROQ_API_KEY="gsk_test"),
            client=client,
        )

        await gateway.generate(prompt="Décris cette photo", task_type="vision", image_b64="QUJD")

        messages = captured["payload"]["messages"]
        content = messages[-1]["content"]
        assert isinstance(content, list)
        assert content[0] == {"type": "text", "text": "Décris cette photo"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"
        # Modèle du catalogue vision (et non du catalogue général)
        assert captured["payload"]["model"] == MODEL_CATALOG["vision"]["groq"]

    @pytest.mark.asyncio
    async def test_vision_without_image_keeps_text_message(self, monkeypatch):
        monkeypatch.delenv("GROQ_MODEL", raising=False)
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json=openai_response("ok"), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        gateway = AIGateway(
            settings=make_settings(GROQ_ENABLED=True, GROQ_API_KEY="gsk_test"),
            client=client,
        )

        await gateway.generate(prompt="Bonjour", task_type="general")

        content = captured["payload"]["messages"][-1]["content"]
        assert isinstance(content, str)
        assert content == "Bonjour"

    @pytest.mark.asyncio
    async def test_vision_excludes_opencode_provider(self):
        gateway = AIGateway(
            settings=make_settings(OPENCODE_ENABLED=True),
            client=None,
        )
        with pytest.raises(AINoProviderAvailable):
            await gateway.generate(prompt="Décris", task_type="vision", image_b64="QUJD")

    @pytest.mark.asyncio
    async def test_vision_falls_back_to_next_vision_provider(self, monkeypatch):
        for var in ("AI_DEFAULT_MODEL", "GROQ_MODEL", "GEMINI_MODEL"):
            monkeypatch.delenv(var, raising=False)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.groq.com":
                return httpx.Response(429, json={"error": "rate limit"}, request=request)
            return httpx.Response(200, json=openai_response("gemini ok"), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        gateway = AIGateway(
            settings=make_settings(
                GROQ_ENABLED=True, GROQ_API_KEY="gsk_test",
                GEMINI_ENABLED=True, GEMINI_API_KEY="AIza_test",
            ),
            client=client,
        )

        response = await gateway.generate(prompt="Décris", task_type="vision", image_b64="QUJD")

        assert response.provider_used == "gemini"
        assert response.model_used == MODEL_CATALOG["vision"]["gemini"]
        assert response.fallback_used is True

    def test_resolve_model_vision_uses_vision_catalog(self, monkeypatch):
        for var in ("GROQ_MODEL", "GEMINI_MODEL", "OPENROUTER_MODEL"):
            monkeypatch.delenv(var, raising=False)
        settings = make_settings()
        assert resolve_model(settings, "gemini", "vision", None) == MODEL_CATALOG["vision"]["gemini"]
        assert resolve_model(settings, "groq", "vision", None) == MODEL_CATALOG["vision"]["groq"]


# ============================================================
# Helpers du service ig_music
# ============================================================

class TestIgMusicHelpers:

    def test_extract_json_plain_object(self):
        assert ig_music._extract_json('{"index": 2, "raison": "ok"}') == {"index": 2, "raison": "ok"}

    def test_extract_json_from_code_fence(self):
        text = 'Voici :\n```json\n{"recherche": "night run"}\n```'
        assert ig_music._extract_json(text) == {"recherche": "night run"}

    def test_extract_json_surrounding_text(self):
        text = 'Ambiance calme. {"scene": "forêt", "index": 1} fin.'
        assert ig_music._extract_json(text) == {"scene": "forêt", "index": 1}

    def test_extract_json_invalid_returns_none(self):
        assert ig_music._extract_json("pas de json") is None
        assert ig_music._extract_json("") is None
        assert ig_music._extract_json('{"incomplete"') is None

    def test_fallback_query_from_title(self):
        assert ig_music._fallback_query("Sortie nocturne en forêt") == "Sortie nocturne en forêt"

    def test_fallback_query_without_title(self):
        assert ig_music._fallback_query(None) == ig_music._FALLBACK_QUERY
        assert ig_music._fallback_query("   ") == ig_music._FALLBACK_QUERY


# ============================================================
# Orchestration : photo -> analyse -> recherche -> choix
# ============================================================

def _stub_analysis(recherche: str | None = "night forest run"):
    async def fake_analyze(image_b64, title, hashtags):
        if recherche is None:
            return None
        return {
            "scene": "Forêt de nuit",
            "ambiance": "sombre et intense",
            "mots_cles": ["nuit", "forêt"],
            "recherche": recherche,
        }

    return fake_analyze


class TestPickAudioForPhoto:

    @pytest.mark.asyncio
    async def test_success_picks_requested_track(self, monkeypatch):
        queries = []

        async def fake_b64(db, user, photo_id):
            return "QUJD"

        async def fake_search(db, query, limit=10):
            queries.append(query)
            return [
                {"audio_id": "111", "title": "First", "display_artist": "Artiste A"},
                {"audio_id": "222", "title": "Second", "display_artist": "Artiste B"},
            ]

        class FakeGateway:
            async def generate(self, **kwargs):
                class R:
                    text = '{"index": 2, "raison": "thème nocturne"}'

                return R()

        monkeypatch.setattr(ig_music, "photo_image_b64", fake_b64)
        monkeypatch.setattr(ig_music, "_analyze_photo", _stub_analysis())
        monkeypatch.setattr(ig_music, "search_ig_audio", fake_search)
        monkeypatch.setattr(ig_music, "ai_gateway", FakeGateway())

        entry = await ig_music.pick_audio_for_photo(
            None, None, 42, title="Sortie nuit", hashtags="#trail"
        )

        assert entry is not None
        assert entry["audio_id"] == "222"
        assert entry["query"] == "night forest run"
        assert entry["status"] == "selected"
        assert entry["source"] == "instagram"
        assert entry["raison"] == "thème nocturne"
        assert queries == ["night forest run"]

    @pytest.mark.asyncio
    async def test_without_vision_uses_title_query(self, monkeypatch):
        queries = []

        async def fake_b64(db, user, photo_id):
            return "QUJD"

        async def fake_search(db, query, limit=10):
            queries.append(query)
            return [{"audio_id": "333", "title": "Only", "display_artist": "C"}]

        monkeypatch.setattr(ig_music, "photo_image_b64", fake_b64)
        monkeypatch.setattr(ig_music, "_analyze_photo", _stub_analysis(recherche=None))
        monkeypatch.setattr(ig_music, "search_ig_audio", fake_search)

        entry = await ig_music.pick_audio_for_photo(
            None, None, 42, title="Sortie longue", hashtags=None
        )

        assert entry is not None
        assert entry["audio_id"] == "333"
        # Requête de repli dérivée du titre
        assert queries == ["Sortie longue"]
        assert entry["query"] == "Sortie longue"

    @pytest.mark.asyncio
    async def test_empty_search_returns_none_and_falls_back(self, monkeypatch):
        queries = []

        async def fake_b64(db, user, photo_id):
            return "QUJD"

        async def fake_search(db, query, limit=10):
            queries.append(query)
            return []

        monkeypatch.setattr(ig_music, "photo_image_b64", fake_b64)
        monkeypatch.setattr(ig_music, "_analyze_photo", _stub_analysis("unknown query"))
        monkeypatch.setattr(ig_music, "search_ig_audio", fake_search)

        entry = await ig_music.pick_audio_for_photo(
            None, None, 42, title="Sortie longue", hashtags=None
        )

        assert entry is None
        # Recherche initiale + repli sur la requête dérivée du titre
        assert queries == ["unknown query", "Sortie longue"]

    @pytest.mark.asyncio
    async def test_single_result_needs_no_second_ai_call(self, monkeypatch):
        async def fake_b64(db, user, photo_id):
            return "QUJD"

        async def fake_search(db, query, limit=10):
            return [{"audio_id": "777", "title": "Unique", "display_artist": "D"}]

        class NoAIGateway:
            async def generate(self, **kwargs):
                raise AssertionError("aucun appel IA ne doit être fait pour un seul résultat")

        monkeypatch.setattr(ig_music, "photo_image_b64", fake_b64)
        monkeypatch.setattr(ig_music, "_analyze_photo", _stub_analysis())
        monkeypatch.setattr(ig_music, "search_ig_audio", fake_search)
        monkeypatch.setattr(ig_music, "ai_gateway", NoAIGateway())

        entry = await ig_music.pick_audio_for_photo(None, None, 42, title="T", hashtags=None)

        assert entry is not None
        assert entry["audio_id"] == "777"

    @pytest.mark.asyncio
    async def test_missing_image_returns_none_without_analysis(self, monkeypatch):
        called = {"analyze": False}

        async def fake_b64(db, user, photo_id):
            return None

        async def fake_analyze(*args, **kwargs):
            called["analyze"] = True
            return None

        monkeypatch.setattr(ig_music, "photo_image_b64", fake_b64)
        monkeypatch.setattr(ig_music, "_analyze_photo", fake_analyze)

        entry = await ig_music.pick_audio_for_photo(None, None, 42, title="T", hashtags=None)

        assert entry is None
        assert called["analyze"] is False

    @pytest.mark.asyncio
    async def test_ai_pick_failure_falls_back_to_first_result(self, monkeypatch):
        async def fake_b64(db, user, photo_id):
            return "QUJD"

        async def fake_search(db, query, limit=10):
            return [
                {"audio_id": "1", "title": "A", "display_artist": "X"},
                {"audio_id": "2", "title": "B", "display_artist": "Y"},
            ]

        class FailingGateway:
            async def generate(self, **kwargs):
                raise RuntimeError("IA indisponible")

        monkeypatch.setattr(ig_music, "photo_image_b64", fake_b64)
        monkeypatch.setattr(ig_music, "_analyze_photo", _stub_analysis())
        monkeypatch.setattr(ig_music, "search_ig_audio", fake_search)
        monkeypatch.setattr(ig_music, "ai_gateway", FailingGateway())

        entry = await ig_music.pick_audio_for_photo(None, None, 42, title="T", hashtags=None)

        assert entry is not None
        assert entry["audio_id"] == "1"
