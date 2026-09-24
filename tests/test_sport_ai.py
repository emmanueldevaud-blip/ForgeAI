import json

import httpx

from app.core.config import Settings
from app.services.sport_ai import OpenAICompatibleSportAIProvider, get_sport_ai_provider


def settings(**values):
    return Settings(
        _env_file=None,
        SECRET_KEY="test-secret-key-test-secret-key-test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        **values,
    )


async def test_gemini_provider_returns_model_answer():
    async def handler(request):
        assert request.url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        assert json.loads(request.content)["model"] == "gemini-3.7-flash"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Analyse fondée sur les données."}}]},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    configured_settings = settings(SPORT_AI_API_KEY="secret")
    assert isinstance(get_sport_ai_provider(configured_settings), OpenAICompatibleSportAIProvider)
    provider = OpenAICompatibleSportAIProvider(configured_settings, client)

    result = await provider.answer("Comment va ma semaine ?", {"weekly_summary": {"summary": {"activity_count": 2}}})

    await client.aclose()
    assert result["available"] is True
    assert result["provider"] == "openai-compatible"
    assert result["answer"] == "Analyse fondée sur les données."


async def test_provider_falls_back_when_endpoint_is_unavailable():
    async def handler(request):
        raise httpx.ConnectError("endpoint unavailable", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleSportAIProvider(settings(SPORT_AI_API_KEY="secret"), client)

    result = await provider.answer("Comment va ma semaine ?", {"weekly_summary": {"summary": {"activity_count": 0}}})

    await client.aclose()
    assert result["available"] is False
    assert result["provider"] == "local-fallback"
    assert "temporairement indisponible" in result["answer"]


async def test_provider_retries_when_model_is_temporarily_unavailable(monkeypatch):
    calls = 0

    async def no_wait(_seconds):
        pass

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Analyse disponible après reprise."}}]},
            request=request,
        )

    monkeypatch.setattr("app.services.sport_ai.asyncio.sleep", no_wait)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleSportAIProvider(settings(SPORT_AI_API_KEY="secret"), client)

    result = await provider.answer("Comment va ma semaine ?", {})

    await client.aclose()
    assert calls == 2
    assert result["available"] is True
    assert result["answer"] == "Analyse disponible après reprise."


async def test_gemini_provider_uses_flash_fallback_after_retries(monkeypatch):
    models = []

    async def no_wait(_seconds):
        pass

    async def handler(request):
        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "gemini-3.7-flash":
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Analyse fournie par le modèle de repli."}}]},
            request=request,
        )

    monkeypatch.setattr("app.services.sport_ai.asyncio.sleep", no_wait)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleSportAIProvider(settings(SPORT_AI_API_KEY="secret"), client)

    result = await provider.answer("Comment va ma semaine ?", {})

    await client.aclose()
    assert models == ["gemini-3.7-flash", "gemini-3.7-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
    assert result["available"] is True
    assert result["answer"] == "Analyse fournie par le modèle de repli."
