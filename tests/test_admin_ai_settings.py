"""Tests de l'API de paramètres de l'assistant IA (/admin/settings/ai)."""

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.module import Module, ModuleConfig, ModuleStatus
from app.models.maintenance import AIConversation, AIMessage
from app.services.ai_gateway import AIGateway, AINoProviderAvailable, AIResponse
from app.services.ai_gateway.config_store import AI_SETTINGS_FIELDS, SECRET_FIELDS

PROVIDER_PREFIXES = ("GROQ", "GEMINI", "OPENROUTER")


@pytest.fixture(autouse=True)
async def administration_module(db_session):
    """Ligne module « administration » requise pour stocker les configs."""
    result = await db_session.execute(select(Module).where(Module.code == "administration"))
    module = result.scalar_one_or_none()
    if module is None:
        module = Module(
            code="administration",
            name="Administration",
            description="Administration système et configuration",
            icon="settings",
            order=1000,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/administration",
            component_path="Administration",
            is_core=True,
        )
        db_session.add(module)
        await db_session.commit()
    return module


@pytest.fixture(autouse=True)
def restore_ai_settings():
    """Le PUT écrit sur l'instance Settings partagée : restaure après test."""
    settings = get_settings()
    snapshot = {field: getattr(settings, field) for field in AI_SETTINGS_FIELDS}
    yield
    for field, value in snapshot.items():
        setattr(settings, field, value)


def payload(**overrides):
    body = {
        "enabled": True,
        "default_provider": "auto",
        "default_model": "auto",
        "provider_order": "groq,gemini,openrouter",
        "timeout_seconds": 30,
        "max_retries": 2,
        "retry_backoff_seconds": 1.0,
        "groq": {"enabled": True, "api_key": "", "base_url": "https://api.groq.com/openai/v1", "model": ""},
        "gemini": {"enabled": True, "api_key": "", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": ""},
        "openrouter": {"enabled": True, "api_key": "", "base_url": "https://openrouter.ai/api/v1", "model": ""},
    }
    body.update(overrides)
    return body


async def test_get_ai_settings_returns_defaults(client, admin_headers):
    # Neutralise d'éventuelles clés présentes dans le .env local.
    settings = get_settings()
    for prefix in PROVIDER_PREFIXES:
        setattr(settings, f"{prefix}_API_KEY", "")

    response = await client.get("/admin/settings/ai", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["default_provider"] == "auto"
    assert data["provider_order"] == "groq,gemini,openrouter"
    assert data["groq"]["api_key_configured"] is False
    assert data["gemini"]["api_key_configured"] is False
    assert data["openrouter"]["api_key_configured"] is False
    # Aucune valeur de clé ne doit figurer dans la réponse.
    raw = response.text
    for prefix in PROVIDER_PREFIXES:
        assert f'"{prefix.lower()}_api_key"' not in raw


async def test_get_ai_settings_masks_env_api_key(client, admin_headers):
    settings = get_settings()
    settings.GROQ_API_KEY = "gsk_env_secret_value"

    response = await client.get("/admin/settings/ai", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["groq"]["api_key_configured"] is True
    assert "gsk_env_secret_value" not in response.text


async def test_put_ai_settings_persists_and_applies(client, admin_headers, db_session):
    body = payload(
        default_provider="gemini",
        provider_order="gemini,groq,openrouter",
        timeout_seconds=15,
        max_retries=1,
        groq={"enabled": True, "api_key": "gsk_saved_secret", "base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    )

    response = await client.put("/admin/settings/ai", json=body, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["default_provider"] == "gemini"
    assert data["provider_order"] == "gemini,groq,openrouter"
    assert data["timeout_seconds"] == 15
    assert data["max_retries"] == 1
    assert data["groq"]["api_key_configured"] is True
    # La clé ne remonte jamais dans la réponse.
    assert "gsk_saved_secret" not in response.text

    # Appliqué à chaud sur l'instance Settings (donc vu par la gateway).
    settings = get_settings()
    assert settings.GROQ_API_KEY == "gsk_saved_secret"
    assert settings.AI_DEFAULT_PROVIDER == "gemini"
    assert settings.AI_TIMEOUT_SECONDS == 15.0

    # Stocké en DB comme secret.
    result = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "groq_api_key"))
    config = result.scalar_one()
    assert config.is_secret is True
    assert config.value == "gsk_saved_secret"


async def test_put_with_empty_key_preserves_existing(client, admin_headers):
    first = payload(groq={"enabled": True, "api_key": "gsk_first_key", "base_url": "https://api.groq.com/openai/v1", "model": ""})
    response = await client.put("/admin/settings/ai", json=first, headers=admin_headers)
    assert response.status_code == 200

    second = payload(groq={"enabled": True, "api_key": "", "base_url": "https://api.groq.com/openai/v1", "model": ""})
    response = await client.put("/admin/settings/ai", json=second, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["groq"]["api_key_configured"] is True
    assert get_settings().GROQ_API_KEY == "gsk_first_key"


async def test_ai_settings_requires_permission(client, auth_headers):
    response = await client.get("/admin/settings/ai", headers=auth_headers)
    assert response.status_code == 403

    response = await client.put("/admin/settings/ai", json=payload(), headers=auth_headers)
    assert response.status_code == 403


async def test_ai_settings_reject_invalid_default_provider(client, admin_headers):
    response = await client.put(
        "/admin/settings/ai",
        json=payload(default_provider="unknown"),
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_gateway_uses_key_saved_via_settings(client, admin_headers):
    """Clé enregistrée via la page paramètres → utilisée par la gateway."""
    secret = "gsk_via_settings_page"
    response = await client.put(
        "/admin/settings/ai",
        json=payload(groq={"enabled": True, "api_key": secret, "base_url": "https://api.groq.com/openai/v1", "model": ""}),
        headers=admin_headers,
    )
    assert response.status_code == 200

    seen = {}

    async def handler(request):
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
            request=request,
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = AIGateway(settings=get_settings(), client=mock_client)
    ai_response = await gateway.generate(prompt="Bonjour")
    await mock_client.aclose()

    assert ai_response.provider_used == "groq"
    assert seen["authorization"] == f"Bearer {secret}"


async def test_secret_fields_are_declared():
    assert SECRET_FIELDS == frozenset(
        {"GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "WEB_SEARCH_API_KEY"}
    )


# ============================================================
# CHAT (Assistant IA via la passerelle)
# ============================================================


class FakeGateway:
    """Gateway factice injectée à la place du singleton pour les tests."""

    def __init__(self, text="Réponse de test"):
        self.text = text
        self.calls: list[dict] = []
        self.error: Exception | None = None

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return AIResponse(
            text=self.text,
            provider_used="groq",
            model_used="openai/gpt-oss-120b",
            latency=0.123,
            tokens_input=10,
            tokens_output=5,
        )


@pytest.fixture
def fake_gateway(monkeypatch):
    gateway = FakeGateway()

    def _get():
        return gateway

    monkeypatch.setattr("app.services.ai_gateway.gateway.get_ai_gateway", _get)
    return gateway


async def test_ai_chat_returns_meta_and_persists(client, admin_headers, db_session, fake_gateway):
    response = await client.post(
        "/admin/settings/ai/chat",
        json={"message": "Bonjour l'assistant", "task_type": "general"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Réponse de test"
    assert data["provider"] == "groq"
    assert data["model"] == "openai/gpt-oss-120b"
    assert data["latency"] == 0.123
    assert data["tokens_input"] == 10
    assert data["tokens_output"] == 5
    assert data["conversation_id"] >= 1

    # Appel gateway : system prompt + message utilisateur, max_tokens suffisant.
    call = fake_gateway.calls[0]
    assert call["system_prompt"]
    assert call["history"][-1] == {"role": "user", "content": "Bonjour l'assistant"}
    assert call["task_type"] == "general"
    assert call["max_tokens"] >= 500

    # Persistance : 1 conversation module=assistant + 2 messages.
    result = await db_session.execute(
        select(AIConversation).where(AIConversation.id == data["conversation_id"])
    )
    conversation = result.scalar_one()
    assert conversation.module == "assistant"
    result = await db_session.execute(
        select(AIMessage).where(AIMessage.conversation_id == conversation.id)
    )
    messages = result.scalars().all()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].model == "openai/gpt-oss-120b"


async def test_ai_chat_second_call_sends_history(client, admin_headers, fake_gateway):
    first = await client.post(
        "/admin/settings/ai/chat",
        json={"message": "Première question"},
        headers=admin_headers,
    )
    conversation_id = first.json()["conversation_id"]

    second = await client.post(
        "/admin/settings/ai/chat",
        json={"message": "Deuxième question", "conversation_id": conversation_id},
        headers=admin_headers,
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    history = fake_gateway.calls[1]["history"]
    contents = [m["content"] for m in history]
    assert contents == [
        "Première question",
        "Réponse de test",
        "Deuxième question",
    ]


async def test_ai_chat_gateway_error_returns_502_and_persists_nothing(
    client, admin_headers, db_session, fake_gateway
):
    fake_gateway.error = AINoProviderAvailable("Aucun fournisseur IA configuré et disponible")

    response = await client.post(
        "/admin/settings/ai/chat",
        json={"message": "Test erreur"},
        headers=admin_headers,
    )

    assert response.status_code == 502
    assert "Aucun fournisseur" in response.json()["detail"]

    result = await db_session.execute(select(AIConversation))
    assert result.scalars().all() == []
    result = await db_session.execute(select(AIMessage))
    assert result.scalars().all() == []


async def test_ai_chat_conversations_list_and_detail(client, admin_headers, fake_gateway):
    first = await client.post(
        "/admin/settings/ai/chat",
        json={"message": "Question de test"},
        headers=admin_headers,
    )
    conversation_id = first.json()["conversation_id"]

    listing = await client.get("/admin/settings/ai/conversations", headers=admin_headers)
    assert listing.status_code == 200
    items = listing.json()
    assert any(c["id"] == conversation_id for c in items)
    assert all(c["module"] == "assistant" for c in items)

    detail = await client.get(
        f"/admin/settings/ai/conversations/{conversation_id}",
        headers=admin_headers,
    )
    assert detail.status_code == 200
    body = detail.json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]


async def test_ai_chat_requires_permission(client, auth_headers):
    response = await client.post(
        "/admin/settings/ai/chat",
        json={"message": "Bonjour"},
        headers=auth_headers,
    )
    assert response.status_code == 403


async def test_ai_chat_rejects_blank_message(client, admin_headers, fake_gateway):
    response = await client.post(
        "/admin/settings/ai/chat",
        json={"message": "   "},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert fake_gateway.calls == []


async def test_ai_chat_unknown_conversation_404(client, admin_headers, fake_gateway):
    response = await client.post(
        "/admin/settings/ai/chat",
        json={"message": "Bonjour", "conversation_id": 99999},
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_ai_stats_endpoint(client, admin_headers):
    response = await client.get("/admin/settings/ai/stats", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "models" in data
