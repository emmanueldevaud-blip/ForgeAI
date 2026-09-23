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
