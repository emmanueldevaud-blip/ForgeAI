from app.services.ai_gateway import AINoProviderAvailable, ai_gateway
from app.services.sport_ai import (
    GatewaySportAIProvider,
    get_sport_ai_provider,
)


class _FakeGatewayResponse:
    def __init__(self, text: str):
        self.text = text


def test_get_sport_ai_provider_uses_gateway():
    assert isinstance(get_sport_ai_provider(), GatewaySportAIProvider)


async def test_gateway_success_returns_answer(monkeypatch):
    async def fake_generate(**kwargs):
        assert kwargs.get("system_prompt")
        assert kwargs.get("prompt")
        return _FakeGatewayResponse("Bilan solide. Conseil : continue comme ça, et souris !")

    monkeypatch.setattr(ai_gateway, "generate", fake_generate)
    provider = GatewaySportAIProvider()

    result = await provider.answer(
        "Analyse cette activité.",
        {"weekly_summary": {"summary": {"activity_count": 2, "distance_m": 21000}}},
    )

    assert result["available"] is True
    assert result["provider"] == "ai-gateway"
    assert "Conseil" in result["answer"]
    assert result["sources"] == ["weekly_summary"]


async def test_gateway_failure_falls_back_to_local(monkeypatch):
    async def fake_generate(**kwargs):
        raise AINoProviderAvailable("Aucun fournisseur IA configuré et disponible")

    monkeypatch.setattr(ai_gateway, "generate", fake_generate)
    provider = GatewaySportAIProvider()

    result = await provider.answer(
        "Analyse cette activité.",
        {"weekly_summary": {"summary": {"activity_count": 0}}},
    )

    assert result["available"] is False
    assert result["provider"] == "local-fallback"
    assert "temporairement indisponible" in result["answer"]


async def test_gateway_empty_answer_falls_back_to_local(monkeypatch):
    async def fake_generate(**kwargs):
        return _FakeGatewayResponse("")

    monkeypatch.setattr(ai_gateway, "generate", fake_generate)
    provider = GatewaySportAIProvider()

    result = await provider.answer("Analyse cette activité.", {})

    assert result["available"] is False
    assert result["provider"] == "local-fallback"


def test_system_prompt_requests_coaching_tone():
    prompt = GatewaySportAIProvider._system_prompt()
    assert "humour" in prompt
    assert "conseil concret" in prompt.lower()
    assert "français" in prompt
