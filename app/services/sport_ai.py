import json
import logging
from typing import Any, Protocol

from app.services.ai_gateway import AIGatewayError, ai_gateway

logger = logging.getLogger(__name__)


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


class GatewaySportAIProvider:
    """IA sport via l'AI Gateway de l'application.

    La cascade de fournisseurs (Groq, Gemini, OpenRouter) est gérée par
    l'AI Gateway; ce provider se contente de lui soumettre la question.
    """

    async def answer(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        user_content = (
            f"Question: {question}\n"
            f"Contexte JSON:\n{json.dumps(context, ensure_ascii=True, default=str)}"
        )
        try:
            response = await ai_gateway.generate(
                prompt=user_content,
                system_prompt=self._system_prompt(),
                temperature=0.6,
                max_tokens=900,
            )
            if response.text:
                return {
                    "available": True,
                    "provider": "ai-gateway",
                    "answer": response.text,
                    "sources": self._sources(context),
                }
        except (AIGatewayError, TypeError, KeyError, IndexError) as exc:
            logger.warning("[SPORT-AI] AI Gateway indisponible (%s) : %s", type(exc).__name__, exc)
        return await LocalSportAIProvider().answer(question, context)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Tu es Coach Sport de ForgeAI. Réponds en français, uniquement à partir du contexte fourni. "
            "Ne fabrique aucune métrique manquante. Distingue donnée, calcul, observation et hypothèse. "
            "Ne donne aucun diagnostic médical ni recommandation médicale. Si une information manque, dis-le clairement. "
            "Ton style : une vraie conversation de coach, en « toi », naturelle et engageante — pas un rapport chiffré. "
            "Utilise les chiffres seulement quand ils étayent un point : pas de tableaux, pas d'avalanche de pourcentages. "
            "Une pointe d'humour léger (jamais sarcastique ni blessant), et termine toujours par un conseil concret et applicable."
        )

    @staticmethod
    def _sources(context: dict[str, Any]) -> list[str]:
        return [key for key in ("athlete", "current_activity", "recent_activities", "weekly_summary", "monthly_summary", "goals") if context.get(key)]


def get_sport_ai_provider() -> SportAIProvider:
    """Le sport utilise exclusivement l'AI Gateway (cascade Groq/Gemini/OpenRouter)."""
    return GatewaySportAIProvider()
