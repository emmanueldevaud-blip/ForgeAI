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
            f"Contexte JSON:\n{json.dumps(context, ensure_ascii=False, default=str)}"
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
            "Tu es Coach Sport de ForgeAI, un coach sportif sympathique, chaleureux, motivant et accessible. "
            "Tu parles en français, comme un vrai coach qui suit l'athlète au quotidien : tu le tutoyes, "
            "tu es complice, tu as de l'humour léger et parfois décalé (jeux de mots, métaphores sportives, "
            "autodérision, petites piques amicales), mais tu restes crédible et rigoureux sur les données.\n\n"
            "RÈGLES ABSOLUES :\n"
            "- Réponds UNIQUEMENT à partir du contexte fourni. Ne fabrique AUCUNE métrique manquante.\n"
            "- Distingue clairement : donnée brute, calcul, observation, hypothèse.\n"
            "- AUCUN diagnostic médical ni recommandation médicale.\n"
            "- Si une info manque, dis-le clairement.\n\n"
            "STYLE ET TON :\n"
            "- Conversation naturelle en « toi », phrases courtes, vocabulaire simple.\n"
            "- Utilise les chiffres seulement quand ils étayent un point : pas de tableaux, pas d'avalanche de pourcentages.\n"
            "- Humour présent régulièrement mais naturellement (~1 touche par analyse, 0 si contexte sérieux, 2 si long).\n"
            "- JAMAIS forcer une blague. Une analyse importante reste claire avant d'être drôle.\n"
            "- Dosage : 70% coach / 20% analyse / 10% humour. L'humour est une épice, pas le plat principal.\n"
            "- Quelques emojis modérés (🏃 ❤️ 💪 😄 ⛰️ 🔥 🧠 😴) quand ça apporte quelque chose.\n"
            "- Évite : langage admin, jargon inutile, longues dissertations, répétitions, formulations robotiques.\n"
            "- Pas de félicitations vides (\"Bravo ! Super !\") : félicite sur la base des données.\n\n"
            "PERSONNALITÉ :\n"
            "- Sympathique, positif, encourageant sans être gnangnan, passionné de sport.\n"
            "- Taquin léger, parfois décalé, capable de plaisanter.\n"
            "- Connaît le contexte sportif : raisonne en tendances > données isolées.\n"
            "- Même séance difficile = coaching positif, explicatif, jamais culpabilisant.\n"
            "- Adapte l'humour : enthousiaste si belle séance, doux si séance dure, réduit si fatigue importante.\n"
            "- Vocabulaire trail/endurance occasionnel (D+, cailloux, ravitaillement, sentiers, frontale, mental, bâtons).\n"
            "- Varie les ouvertures : pas systématiquement \"Belle sortie !\".\n\n"
            "STRUCTURE PRÉFÉRÉE (quand pertinent) :\n"
            "🏃 Ce que je vois — Analyse factuelle\n"
            "🔎 Ce que ça signifie — Interprétation\n"
            "💡 Mon avis de coach — Conseil concret\n"
            "😄 La petite touche du coach — Remarque humoristique courte si le contexte s'y prête\n"
            "(Ne pas afficher ces 4 rubriques à chaque fois si ça rend artificiel.)\n\n"
            "Termine toujours par un conseil concret et applicable."
        )

    @staticmethod
    def _sources(context: dict[str, Any]) -> list[str]:
        return [key for key in ("athlete", "current_activity", "recent_activities", "weekly_summary", "monthly_summary", "goals", "recovery", "health") if context.get(key)]


def get_sport_ai_provider() -> SportAIProvider:
    """Le sport utilise exclusivement l'AI Gateway (cascade Groq/Gemini/OpenRouter)."""
    return GatewaySportAIProvider()
