"""Tests du provider OpenCode (modèles gratuits) dans l'AI Gateway."""

import pytest

from app.services.ai_gateway.errors import AIProviderUnavailable, AIRequestTimeout
from app.services.ai_gateway.providers import OpenCodeProvider
from app.services.development_agent.opencode import OpenCodeResult


def make_settings(**values):
    from app.core.config import Settings

    defaults = {
        "_env_file": None,
        "SECRET_KEY": "test-secret-key-test-secret-key-test",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "AI_MAX_RETRIES": 0,
        "AI_RETRY_BACKOFF_SECONDS": 0,
        "AI_TIMEOUT_SECONDS": 30,
        "OPENCODE_ENABLED": True,
        "GROQ_ENABLED": False,
        "GROQ_API_KEY": "",
        "GEMINI_ENABLED": False,
        "GEMINI_API_KEY": "",
        "OPENROUTER_ENABLED": False,
        "OPENROUTER_API_KEY": "",
    }
    defaults.update(values)
    return Settings(**defaults)


class FakeOpenCodeClient:
    """Remplace OpenCodeClient : aucune exécution réelle du CLI."""

    def __init__(self, result: OpenCodeResult, calls: list | None = None):
        self.result = result
        self.calls = calls if calls is not None else []

    def is_available(self) -> bool:
        return True

    async def run_task(self, prompt, model=None, timeout=300, **kwargs):
        self.calls.append({"prompt": prompt, "model": model, "timeout": timeout})
        return self.result


def patch_opencode_client(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.development_agent.opencode.OpenCodeClient",
        lambda settings=None, work_dir=None: client,
    )


async def test_chat_returns_cli_output(monkeypatch):
    client = FakeOpenCodeClient(OpenCodeResult(success=True, output="Bonjour !"))
    patch_opencode_client(monkeypatch, client)

    provider = OpenCodeProvider(make_settings())
    assert provider.is_available is True

    text, tokens_in, tokens_out = await provider.chat(
        model="mimo-v2.6-flash-free",
        messages=[{"role": "user", "content": "Salut"}],
        temperature=None,
        max_tokens=None,
    )

    assert text == "Bonjour !"
    assert tokens_in is None and tokens_out is None
    assert client.calls[0]["model"] == "opencode/mimo-v2.6-flash-free"
    assert "Salut" in client.calls[0]["prompt"]


async def test_disabled_provider_is_not_available():
    provider = OpenCodeProvider(make_settings(OPENCODE_ENABLED=False))
    assert provider.is_available is False


async def test_timeout_error_is_classified(monkeypatch):
    client = FakeOpenCodeClient(
        OpenCodeResult(success=False, output="", error="Timeout après 30s")
    )
    patch_opencode_client(monkeypatch, client)

    provider = OpenCodeProvider(make_settings())
    with pytest.raises(AIRequestTimeout):
        await provider.chat(
            model="mimo-v2.6-flash-free",
            messages=[{"role": "user", "content": "Salut"}],
            temperature=None,
            max_tokens=None,
        )


async def test_other_error_is_classified_as_unavailable(monkeypatch):
    client = FakeOpenCodeClient(
        OpenCodeResult(success=False, output="", error="boom")
    )
    patch_opencode_client(monkeypatch, client)

    provider = OpenCodeProvider(make_settings())
    with pytest.raises(AIProviderUnavailable):
        await provider.chat(
            model="mimo-v2.6-flash-free",
            messages=[{"role": "user", "content": "Salut"}],
            temperature=None,
            max_tokens=None,
        )


async def test_cascade_calls_opencode_first(monkeypatch):
    """La cascade appelle réellement le provider OpenCode en premier candidat."""
    from app.services.ai_gateway.gateway import AIGateway

    calls: list[dict] = []
    client = FakeOpenCodeClient(
        OpenCodeResult(success=True, output="Réponse gratuite"), calls=calls
    )
    patch_opencode_client(monkeypatch, client)

    free_models = [
        {"id": "mimo-v2.6-flash-free", "provider": "opencode", "name": "mimo", "free": True},
    ]
    monkeypatch.setattr(
        "app.services.ai.model_router.discover_opencode_models",
        lambda: free_models,
    )

    gateway = AIGateway(settings=make_settings())
    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "opencode"
    assert response.model_used == "mimo-v2.6-flash-free"
    assert response.text == "Réponse gratuite"
    assert calls[0]["model"] == "opencode/mimo-v2.6-flash-free"
