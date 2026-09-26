"""Tests de l'API chat du module Assistant IA (/maintenance/ai/chat)."""

import pytest
from sqlalchemy import select

from app.models.maintenance import AIConversation, AIMessage
from app.services.ai_gateway import AIGateway, AINoProviderAvailable, AIResponse


class FakeGateway:
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


async def test_ai_chat_calls_gateway_and_persists(client, admin_headers, db_session, fake_gateway):
    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Bonjour", "module": "maintenance"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Réponse de test"
    assert data["model"] == "openai/gpt-oss-120b"
    assert data["conversation_id"] >= 1

    call = fake_gateway.calls[0]
    assert call["system_prompt"]
    assert call["history"] == [{"role": "user", "content": "Bonjour"}]

    result = await db_session.execute(
        select(AIMessage).where(AIMessage.conversation_id == data["conversation_id"])
    )
    messages = result.scalars().all()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].model == "openai/gpt-oss-120b"


async def test_ai_chat_second_call_sends_history(client, admin_headers, fake_gateway):
    first = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Première question", "module": "maintenance"},
        headers=admin_headers,
    )
    conversation_id = first.json()["conversation_id"]

    second = await client.post(
        "/maintenance/ai/chat",
        json={
            "message": "Deuxième question",
            "module": "maintenance",
            "conversation_id": conversation_id,
        },
        headers=admin_headers,
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    history = fake_gateway.calls[1]["history"]
    contents = [m["content"] for m in history]
    assert contents == ["Première question", "Réponse de test", "Deuxième question"]


async def test_ai_chat_gateway_error_returns_502(client, admin_headers, db_session, fake_gateway):
    fake_gateway.error = AINoProviderAvailable("Aucun fournisseur IA configuré et disponible")

    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Test erreur", "module": "maintenance"},
        headers=admin_headers,
    )

    assert response.status_code == 502
    assert "Aucun fournisseur" in response.json()["detail"]

    result = await db_session.execute(select(AIConversation))
    assert result.scalars().all() == []


async def test_ai_chat_rejects_blank_message(client, admin_headers, fake_gateway):
    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "   ", "module": "maintenance"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert fake_gateway.calls == []


async def test_ai_chat_sport_question_uses_sport_context(client, admin_headers, fake_gateway, monkeypatch):
    async def fake_context(db, user):
        return {"weekly_summary": {"summary": {"activity_count": 3}}}

    class FakeSportProvider:
        async def answer(self, question, context):
            assert context.get("weekly_summary")
            return {"available": True, "provider": "ai-gateway", "answer": "Réponse du coach", "sources": ["weekly_summary"]}

    monkeypatch.setattr("app.api.maintenance._build_sport_context", fake_context)
    monkeypatch.setattr("app.api.maintenance.get_sport_ai_provider", lambda: FakeSportProvider())

    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Analyse mon activité sportive de la semaine", "module": "maintenance"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Réponse du coach"
    assert data["model"] == "ai-gateway"
    assert fake_gateway.calls == []
