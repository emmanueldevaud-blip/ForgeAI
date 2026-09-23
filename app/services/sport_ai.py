import json
from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings


class SportAIProvider(Protocol):
    async def answer(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        """Return a structured answer without accessing the database."""


class LocalSportAIProvider:
    """Deterministic fallback that remains available without an API key."""

    async def answer(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        summary = context.get("weekly_summary", {}).get("summary", {})
        activity_count = summary.get("activity_count", 0)
        distance = summary.get("distance_m")
        if not activity_count:
            message = "Je ne dispose d’aucune activité sur la période analysée."
        else:
            distance_text = f"{distance / 1000:.1f} km" if distance is not None else "une distance non renseignée"
            message = f"Sur la période analysée, {activity_count} activité(s) représentent {distance_text}."
        return {
            "available": False,
            "provider": "local-fallback",
            "answer": f"Le LLM est temporairement indisponible. {message} Ces éléments sont descriptifs et ne constituent pas un avis médical.",
            "sources": ["weekly_summary"],
        }


class OpenAICompatibleSportAIProvider:
    """Calls an OpenAI-compatible chat completion endpoint without DB access."""

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    async def answer(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        local_endpoint = self.settings.SPORT_AI_BASE_URL.startswith(("http://127.0.0.1", "http://localhost", "http://host.docker.internal"))
        if not self.settings.SPORT_AI_API_KEY and not local_endpoint:
            return await LocalSportAIProvider().answer(question, context)

        payload = {
            "model": self.settings.SPORT_AI_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": f"Question: {question}\nContexte JSON:\n{json.dumps(context, ensure_ascii=True, default=str)}"},
            ],
        }
        headers = {"Authorization": f"Bearer {self.settings.SPORT_AI_API_KEY}"} if self.settings.SPORT_AI_API_KEY else {}
        client = self._client or httpx.AsyncClient(timeout=self.settings.SPORT_AI_TIMEOUT_SECONDS)
        close_client = self._client is None
        try:
            response = await client.post(
                f"{self.settings.SPORT_AI_BASE_URL.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            answer = body.get("choices", [{}])[0].get("message", {}).get("content")
            if not answer:
                raise ValueError("Réponse LLM vide")
            return {"available": True, "provider": "openai-compatible", "answer": answer, "sources": self._sources(context)}
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            return await LocalSportAIProvider().answer(question, context)
        finally:
            if close_client:
                await client.aclose()

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Tu es Coach Sport de ForgeAI. Réponds en français, uniquement à partir du contexte fourni. "
            "Ne fabrique aucune métrique manquante. Distingue donnée, calcul, observation et hypothèse. "
            "Ne donne aucun diagnostic médical ni recommandation médicale. Si une information manque, dis-le clairement."
        )

    @staticmethod
    def _sources(context: dict[str, Any]) -> list[str]:
        return [key for key in ("athlete", "current_activity", "recent_activities", "weekly_summary", "monthly_summary", "goals") if context.get(key)]


def get_sport_ai_provider(settings: Settings | None = None) -> SportAIProvider:
    resolved = settings or get_settings()
    if resolved.SPORT_AI_PROVIDER.lower() in {"gemini", "openai", "openai-compatible"}:
        return OpenAICompatibleSportAIProvider(resolved)
    return LocalSportAIProvider()
