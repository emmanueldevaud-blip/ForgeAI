"""Tests ciblés de l'AI Gateway."""

import logging

import httpx

from app.core.config import Settings
from app.services.ai_gateway import (
    AIGateway,
    AINoProviderAvailable,
)
from app.services.ai_gateway.gateway import get_ai_gateway
from app.services.ai_gateway.models import MODEL_CATALOG, resolve_model


def make_settings(**values):
    defaults = {
        "_env_file": None,
        "SECRET_KEY": "test-secret-key-test-secret-key-test",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "AI_MAX_RETRIES": 0,
        "AI_RETRY_BACKOFF_SECONDS": 0,
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


def make_gateway(handler, **settings_values) -> AIGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AIGateway(settings=make_settings(**settings_values), client=client)


def host_of(request: httpx.Request) -> str:
    return request.url.host


async def test_groq_available_returns_response():
    async def handler(request):
        assert host_of(request) == "api.groq.com"
        return httpx.Response(200, json=openai_response("Réponse Groq"), request=request)

    gateway = make_gateway(handler, GROQ_ENABLED=True, GROQ_API_KEY="gsk_test")

    response = await gateway.generate(prompt="Bonjour", task_type="general")

    assert response.text == "Réponse Groq"
    assert response.provider_used == "groq"
    assert response.model_used
    assert response.tokens_input == 10
    assert response.tokens_output == 5
    assert response.fallback_used is False
    assert response.latency >= 0


async def test_quota_exceeded_falls_back_to_gemini():
    calls = []

    async def handler(request):
        host = host_of(request)
        calls.append(host)
        if host == "api.groq.com":
            return httpx.Response(429, json={"error": "rate limit"}, request=request)
        return httpx.Response(200, json=openai_response("Réponse Gemini"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,
        GROQ_API_KEY="gsk_test",
        GEMINI_ENABLED=True,
        GEMINI_API_KEY="AIza_test",
    )

    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "gemini"
    assert response.text == "Réponse Gemini"
    assert response.fallback_used is True
    # Cascade intra-provider : chaque modèle Groq configuré est tenté (un quota
    # sur un modèle ne rend pas Groq entier indisponible), puis Gemini répond.
    groq_calls = [host for host in calls if host == "api.groq.com"]
    assert groq_calls, "Groq doit être tenté en premier"
    assert calls == groq_calls + ["generativelanguage.googleapis.com"]
    quota = gateway.get_stats()
    groq = next(p for p in quota["providers"] if p["provider"] == "groq")
    assert groq["errors"] == len(groq_calls)
    assert groq["status"] == "quota_exceeded"


async def test_error_chain_falls_back_until_openrouter():
    async def handler(request):
        host = host_of(request)
        if host == "api.groq.com":
            return httpx.Response(500, request=request)
        if host == "generativelanguage.googleapis.com":
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json=openai_response("Réponse OpenRouter"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,
        GROQ_API_KEY="gsk_test",
        GEMINI_ENABLED=True,
        GEMINI_API_KEY="AIza_test",
        OPENROUTER_ENABLED=True,
        OPENROUTER_API_KEY="sk-or_test",
    )

    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "openrouter"
    assert response.text == "Réponse OpenRouter"
    assert response.fallback_used is True


async def test_no_provider_available_raises_clean_error():
    async def handler(request):
        raise AssertionError("aucun appel réseau attendu")

    gateway = make_gateway(handler)

    try:
        await gateway.generate(prompt="Bonjour")
        raise AssertionError("AINoProviderAvailable attendu")
    except AINoProviderAvailable:
        pass


async def test_missing_key_does_not_block_other_providers():
    async def handler(request):
        assert host_of(request) != "api.groq.com", "Groq sans clé ne doit pas être appelé"
        return httpx.Response(200, json=openai_response("OK Gemini"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,  # activé mais clé absente
        GROQ_API_KEY="",
        GEMINI_ENABLED=True,
        GEMINI_API_KEY="AIza_test",
    )

    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "gemini"


async def test_disabled_provider_is_skipped():
    async def handler(request):
        assert host_of(request) == "openrouter.ai"
        return httpx.Response(200, json=openai_response("OK OpenRouter"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=False,
        GROQ_API_KEY="gsk_test",
        OPENROUTER_ENABLED=True,
        OPENROUTER_API_KEY="sk-or_test",
    )

    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "openrouter"


async def test_preferred_provider_is_used_first():
    hosts = []

    async def handler(request):
        hosts.append(host_of(request))
        return httpx.Response(200, json=openai_response("OK"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,
        GROQ_API_KEY="gsk_test",
        OPENROUTER_ENABLED=True,
        OPENROUTER_API_KEY="sk-or_test",
    )

    response = await gateway.generate(prompt="Bonjour", preferred_provider="openrouter")

    assert response.provider_used == "openrouter"
    assert hosts == ["openrouter.ai"]


async def test_preferred_provider_unavailable_falls_back_when_enabled():
    async def handler(request):
        if host_of(request) == "api.groq.com":
            return httpx.Response(500, request=request)
        return httpx.Response(200, json=openai_response("OK Gemini"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,
        GROQ_API_KEY="gsk_test",
        GEMINI_ENABLED=True,
        GEMINI_API_KEY="AIza_test",
    )

    response = await gateway.generate(prompt="Bonjour", preferred_provider="groq")

    assert response.provider_used == "gemini"
    assert response.fallback_used is True


async def test_auth_error_marks_provider_unavailable():
    async def handler(request):
        if host_of(request) == "api.groq.com":
            return httpx.Response(401, json={"error": "invalid key"}, request=request)
        return httpx.Response(200, json=openai_response("OK Gemini"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,
        GROQ_API_KEY="invalid",
        GEMINI_ENABLED=True,
        GEMINI_API_KEY="AIza_test",
    )

    first = await gateway.generate(prompt="Bonjour")
    assert first.provider_used == "gemini"

    # Groq est marqué en cooldown : le second appel ne tente même plus Groq.
    second = await gateway.generate(prompt="Encore")
    assert second.provider_used == "gemini"
    assert not gateway.stats.is_available("groq")


async def test_api_keys_never_appear_in_logs(caplog):
    secret_groq = "gsk_super_secret_value"
    secret_gemini = "AIza_super_secret_value"

    async def handler(request):
        if host_of(request) == "api.groq.com":
            return httpx.Response(429, request=request)
        return httpx.Response(200, json=openai_response("OK"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,
        GROQ_API_KEY=secret_groq,
        GEMINI_ENABLED=True,
        GEMINI_API_KEY=secret_gemini,
    )

    with caplog.at_level(logging.DEBUG):
        await gateway.generate(prompt="Prompt sensible client=Acme")

    all_logs = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_groq not in all_logs
    assert secret_gemini not in all_logs
    assert "Prompt sensible" not in all_logs
    assert any("[AI-GATEWAY]" in r.getMessage() for r in caplog.records)


async def test_stats_are_recorded():
    async def handler(request):
        if host_of(request) == "api.groq.com":
            return httpx.Response(429, request=request)
        return httpx.Response(200, json=openai_response("OK"), request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,
        GROQ_API_KEY="gsk_test",
        GEMINI_ENABLED=True,
        GEMINI_API_KEY="AIza_test",
    )

    await gateway.generate(prompt="Bonjour")
    stats = gateway.get_stats()
    providers = {p["provider"]: p for p in stats["providers"]}
    # Cascade intra-provider : chaque modèle Groq configuré est tenté (quota).
    groq_models = {MODEL_CATALOG[task]["groq"] for task in MODEL_CATALOG}
    assert providers["groq"]["errors"] == len(groq_models)
    assert providers["gemini"]["requests"] == 1
    assert providers["gemini"]["tokens_input"] == 10
    assert providers["gemini"]["tokens_output"] == 5
    assert providers["gemini"]["fallbacks"] == 1
    models = stats["models"]
    assert any(m["provider"] == "gemini" and m["requests"] == 1 for m in models)


async def test_gateway_disabled_returns_no_provider():
    async def handler(request):
        raise AssertionError("aucun appel réseau attendu")

    gateway = make_gateway(handler, AI_GATEWAY_ENABLED=False, GROQ_ENABLED=True, GROQ_API_KEY="k")

    try:
        await gateway.generate(prompt="Bonjour")
        raise AssertionError("AINoProviderAvailable attendu")
    except AINoProviderAvailable as exc:
        assert "désactivée" in str(exc)


async def test_empty_prompt_rejected():
    gateway = make_gateway(lambda request: None)

    try:
        await gateway.generate(prompt="   ")
        raise AssertionError("ValueError attendu")
    except ValueError:
        pass


def test_resolve_model_priority():
    settings = make_settings(GROQ_MODEL="custom-model")
    # Override env prime sur le catalogue
    assert resolve_model(settings, "groq", "general", "auto") == "custom-model"
    # Modèle explicite prime sur tout
    assert resolve_model(settings, "groq", "general", "explicit-model") == "explicit-model"
    # Catalogue par task_type sans override
    settings_no_override = make_settings()
    assert resolve_model(settings_no_override, "gemini", "reasoning", "auto") == "gemini-2.5-flash"
    assert resolve_model(settings_no_override, "openrouter", "coding", None) == (
        "qwen/qwen-2.5-coder-32b-instruct"
    )


def test_singleton_is_cached():
    get_ai_gateway.cache_clear()
    first = get_ai_gateway()
    second = get_ai_gateway()
    assert first is second
    get_ai_gateway.cache_clear()


async def test_all_providers_failing_raises_with_collected_errors():
    async def handler(request):
        return httpx.Response(503, request=request)

    gateway = make_gateway(
        handler,
        GROQ_ENABLED=True,
        GROQ_API_KEY="gsk_test",
        GEMINI_ENABLED=True,
        GEMINI_API_KEY="AIza_test",
        OPENROUTER_ENABLED=True,
        OPENROUTER_API_KEY="sk-or_test",
    )

    try:
        await gateway.generate(prompt="Bonjour")
        raise AssertionError("AINoProviderAvailable attendu")
    except AINoProviderAvailable as exc:
        assert len(exc.errors) == 3
