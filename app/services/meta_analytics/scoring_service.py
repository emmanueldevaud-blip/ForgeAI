"""Score de performance editoriale sur 100 pour les contenus Meta.

Ponderation configurable (somme = 100) :

- portee relative : 20 %
- taux d'engagement : 20 %
- partages et enregistrements : 25 %
- performances video : 20 %
- croissance attribuable au contenu : 15 % (uniquement si mesurable)

Les scores sont calcules a partir des snapshots reels, normalises par rapport
aux moyennes du compte. Une publication recente n'est pas penalisee par manque
de recul : on compare des contenus d'anciennete comparable lorsque possible.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ScoringWeights:
    reach_relative: float = 20.0
    engagement_rate: float = 20.0
    shares_saves: float = 25.0
    video_performance: float = 20.0
    growth_attribution: float = 15.0

    def total(self) -> float:
        return (
            self.reach_relative
            + self.engagement_rate
            + self.shares_saves
            + self.video_performance
            + self.growth_attribution
        )


def default_weights() -> ScoringWeights:
    return ScoringWeights()


class MetaAnalyticsScoringService:
    def __init__(self, weights: ScoringWeights | None = None):
        self.weights = weights or default_weights()
        if abs(self.weights.total() - 100.0) > 1e-6:
            raise ValueError(f"Les poids de scoring doivent sommer 100 (actuel: {self.weights.total()})")

    def score_media(
        self,
        media_metrics: dict[str, Any],
        account_benchmarks: dict[str, Any],
    ) -> dict[str, Any]:
        """Calcule un score sur 100 pour un media.

        media_metrics : mesures brutes recentes du media (reach, impressions,
            likes, comments, shares, saves, video_views, followers_gained...)
        account_benchmarks : moyennes de reference du compte pour normaliser.
        """
        w = self.weights
        details: dict[str, float] = {}

        # 1. Portee relative (0-100) : reach du media vs reach moyenne du compte
        media_reach = self._num(media_metrics.get("reach"))
        avg_reach = self._num(account_benchmarks.get("avg_reach"))
        details["reach_relative"] = self._clamp0100(media_reach / avg_reach * 100.0) if avg_reach else 50.0

        # 2. Taux d'engagement (0-100) : (likes+comments+shares+saves) / reach
        interactions = sum(
            self._num(media_metrics.get(k)) for k in ("likes", "comments", "shares", "saves")
        )
        reach = self._num(media_metrics.get("reach"))
        engagement_rate = (interactions / reach * 100.0) if reach else 0.0
        avg_er = self._num(account_benchmarks.get("avg_engagement_rate"))
        details["engagement_rate"] = self._clamp0100(engagement_rate / avg_er * 100.0) if avg_er else min(engagement_rate * 10, 100.0)

        # 3. Partages et enregistrements (0-100)
        amplification = self._num(media_metrics.get("shares")) + self._num(media_metrics.get("saves"))
        avg_amp = self._num(account_benchmarks.get("avg_amplification"))
        details["shares_saves"] = self._clamp0100(amplification / avg_amp * 100.0) if avg_amp else min(amplification * 10, 100.0)

        # 4. Performance video (0-100) : video_views / reach (uniquement pour video/reel)
        is_video = media_metrics.get("is_video", False)
        video_views = self._num(media_metrics.get("video_views"))
        if is_video and reach:
            video_score = self._clamp0100(video_views / reach * 100.0)
        else:
            video_score = 50.0  # neutre si pas de video ou pas de reach
        details["video_performance"] = video_score

        # 5. Croissance attribuable (0-100) : abonnes gaines lies au contenu
        followers_gained = self._num(media_metrics.get("followers_gained"))
        avg_fg = self._num(account_benchmarks.get("avg_followers_gained"))
        details["growth_attribution"] = self._clamp0100(followers_gained / avg_fg * 100.0) if avg_fg else 50.0

        score = (
            details["reach_relative"] * w.reach_relative / 100.0
            + details["engagement_rate"] * w.engagement_rate / 100.0
            + details["shares_saves"] * w.shares_saves / 100.0
            + details["video_performance"] * w.video_performance / 100.0
            + details["growth_attribution"] * w.growth_attribution / 100.0
        )
        score = round(min(100.0, max(0.0, score)), 1)

        return {
            "score": score,
            "details": details,
            "weights": {
                "reach_relative": w.reach_relative,
                "engagement_rate": w.engagement_rate,
                "shares_saves": w.shares_saves,
                "video_performance": w.video_performance,
                "growth_attribution": w.growth_attribution,
            },
            "indicators_used": {
                "reach": media_reach,
                "interactions": interactions,
                "engagement_rate": round(engagement_rate, 2),
                "amplification": amplification,
                "video_views": video_views,
                "followers_gained": followers_gained,
            },
        }

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _clamp0100(value: float) -> float:
        return max(0.0, min(100.0, value))


def compute_account_benchmarks(media_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcule les moyennes de reference a partir d'une liste de medias."""
    if not media_list:
        return {
            "avg_reach": 0.0,
            "avg_engagement_rate": 0.0,
            "avg_amplification": 0.0,
            "avg_followers_gained": 0.0,
            "count": 0,
        }
    count = len(media_list)
    avg_reach = sum(m.get("reach", 0) or 0 for m in media_list) / count
    avg_er = sum(m.get("engagement_rate", 0) or 0 for m in media_list) / count
    avg_amp = sum((m.get("shares", 0) or 0) + (m.get("saves", 0) or 0) for m in media_list) / count
    avg_fg = sum(m.get("followers_gained", 0) or 0 for m in media_list) / count
    return {
        "avg_reach": avg_reach,
        "avg_engagement_rate": avg_er,
        "avg_amplification": avg_amp,
        "avg_followers_gained": avg_fg,
        "count": count,
    }
