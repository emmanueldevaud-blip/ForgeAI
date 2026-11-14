"""Analyse IA editoriale pour Meta Analytics.

Reutilise exclusivement la passerelle IA existante (ai_gateway). Aucun
nouveau systeme IA n'est cree. L'IA ne produit jamais de statistiques
inventees : elle analyse uniquement les donnees reelles recuperees depuis
les snapshots Meta et indique le niveau de confiance et les donnees qui
justifient chaque recommandation.
"""

import json
import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import select as sa_select

from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.meta_analytics.scoring_service import MetaAnalyticsScoringService, compute_account_benchmarks, default_weights

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Tu es un analyste editorial pour les reseaux sociaux (Instagram et Facebook). "
    "Tu analyses exclusivement des donnees de performance REELLES fournies. "
    "N'invente jamais de statistiques. Ne presente jamais une hypothese comme un fait. "
    "Pour chaque recommandation, indique : la periode analysee, les donnees qui la justifient, "
    "les indicateurs concerns, le niveau de confiance (faible/moyen/eleve) et la raison. "
    "Distings les donnees brutes des indicateurs calcules. "
    "Ne confonds pas corrélation et causalité. Reponds en JSON uniquement."
)


class MetaAnalyticsAIService:
    def __init__(self, db):
        self.db = db

    async def analyze_performance(
        self,
        period_start: date,
        period_end: date,
        instagram_data: dict[str, Any],
        facebook_data: dict[str, Any],
        media_performance: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Produit une analyse editoriale IA a partir des donnees reelles."""
        payload = {
            "periode": {
                "debut": period_start.isoformat(),
                "fin": period_end.isoformat(),
            },
            "instagram": instagram_data,
            "facebook": facebook_data,
            "medias": media_performance,
        }

        prompt = (
            "Analyse la performance editoriale suivante pour la periode "
            f"{period_start.isoformat()} au {period_end.isoformat()}.\n\n"
            f"Donnees reelles (JSON) :\n{json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            "Produis :\n"
            "1. un bilan des performances (points forts, points faibles),\n"
            "2. les tendances positives et negatives,\n"
            "3. les sujets qui fonctionnent le mieux,\n"
            "4. les formats a privilegier,\n"
            "5. les horaires a tester,\n"
            "6. les publications a reproduire et celles a ameliorer,\n"
            "7. des pistes de progression de l'audience,\n"
            "8. des recommandations concretes pour le calendrier editorial.\n\n"
            "Pour chaque recommandation inclut : periode_analysee, donnees_justificatives, "
            "indicateurs_concernes, niveau_confiance (faible/moyen/eleve), raison. "
            "Reponds uniquement en JSON avec les clés : bilan, tendances, sujets, formats, "
            "horaires, publications_a_reproduire, publications_a_ameliorer, progression_audience, "
            "recommandations_calendrier, note_methode."
        )

        try:
            response = await ai_gateway.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.5,
                max_tokens=2000,
            )
        except AIGatewayError as exc:
            logger.warning("IA analyse indisponible: %s", exc)
            return {
                "disponible": False,
                "erreur": str(exc),
                "periode": {"debut": period_start.isoformat(), "fin": period_end.isoformat()},
            }

        parsed = self._parse_json(response.text)
        if parsed is None:
            return {
                "disponible": True,
                "periode": {"debut": period_start.isoformat(), "fin": period_end.isoformat()},
                "analyse_brute": response.text,
            }

        parsed["disponible"] = True
        parsed["periode"] = {"debut": period_start.isoformat(), "fin": period_end.isoformat()}
        parsed["source_donnees"] = {
            "instagram_comptes": bool(instagram_data),
            "facebook_comptes": bool(facebook_data),
            "medias_analyses": len(media_performance),
        }
        return parsed

    async def generate_recommendations(
        self,
        period_start: date,
        period_end: date,
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Génère des recommandations de contenus concretes (idees de publication, Reels, carrousels)."""
        prompt = (
            "A partir de l'analyse de performance suivante (periode "
            f"{period_start.isoformat()} au {period_end.isoformat()}), propose des recommandations de contenus "
            "concretes pour le calendrier editorial.\n\n"
            f"Analyse (JSON) :\n{json.dumps(analysis, ensure_ascii=False, default=str)}\n\n"
            "Pour chaque recommandation, indique :\n"
            "- type (idee_publication, idee_reel, idee_carrousel, legende, hashtag, format, ton_editorial)\n"
            "- titre\n"
            "- description\n"
            "- justification (donnees reelles qui la justifient)\n"
            "- indicateurs_concernes\n"
            "- niveau_confiance (faible/moyen/eleve)\n"
            "- action_suggeree (ajouter_au_calendrier, transformer_en_idee, envoyer_au_studio, ignorer)\n\n"
            "Reponds uniquement en JSON avec une cle 'recommandations' contenant une liste."
        )

        try:
            response = await ai_gateway.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.6,
                max_tokens=2000,
            )
        except AIGatewayError as exc:
            logger.warning("IA recommandations indisponible: %s", exc)
            return [
                {
                    "type": "erreur",
                    "titre": "IA indisponible",
                    "description": str(exc),
                    "niveau_confiance": "faible",
                }
            ]

        parsed = self._parse_json(response.text)
        if parsed is None:
            return [
                {
                    "type": "idee_publication",
                    "titre": "Recommandation IA",
                    "description": response.text[:500],
                    "justification": "Analyse des performances reelles",
                    "niveau_confiance": "moyen",
                    "action_suggeree": "transformer_en_idee",
                }
            ]
        return parsed.get("recommandations", []) if isinstance(parsed, dict) else []

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        cleaned = text.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            if len(parts) >= 3:
                cleaned = parts[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        try:
            s, e = cleaned.find("{"), cleaned.rfind("}")
            if s >= 0 and e > s:
                return json.loads(cleaned[s : e + 1])
        except (json.JSONDecodeError, ValueError):
            pass
        return None


def build_editorial_score_summary(media_performance: list[dict[str, Any]]) -> dict[str, Any]:
    """Resume des scores editoriaux pour alimenter l'IA et le frontend."""
    weights = default_weights()
    scorer = MetaAnalyticsScoringService(weights)
    benchmarks = compute_account_benchmarks(media_performance)

    scored = []
    for m in media_performance:
        res = scorer.score_media(m, benchmarks)
        scored.append({
            "media_id": m.get("media_id"),
            "media_type": m.get("media_type"),
            "permalink": m.get("permalink"),
            "score": res["score"],
            "details": res["details"],
            "indicators": res["indicators_used"],
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {
        "benchmarks": benchmarks,
        "medias": scored,
        "meilleure_portee": scored[0] if scored else None,
        "meilleur_engagement": None,
    }
