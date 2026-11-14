"""Package Meta Analytics & Intelligence (Community Manager IA)."""

from app.services.meta_analytics.collector_service import MetaCollectorService
from app.services.meta_analytics.facebook_insights_service import FacebookInsightsService
from app.services.meta_analytics.instagram_insights_service import InstagramInsightsService
from app.services.meta_analytics.normalizer import upsert_account_metric, upsert_audience, upsert_snapshot
from app.services.meta_analytics.report_service import MetaAnalyticsReportService
from app.services.meta_analytics.scheduler import meta_sync_loop, run_meta_sync_once
from app.services.meta_analytics.scoring_service import MetaAnalyticsScoringService, ScoringWeights, compute_account_benchmarks
from app.services.meta_analytics.ai_service import MetaAnalyticsAIService, build_editorial_score_summary

__all__ = [
    "MetaCollectorService",
    "InstagramInsightsService",
    "FacebookInsightsService",
    "MetaAnalyticsAIService",
    "MetaAnalyticsScoringService",
    "MetaAnalyticsReportService",
    "ScoringWeights",
    "compute_account_benchmarks",
    "build_editorial_score_summary",
    "upsert_snapshot",
    "upsert_account_metric",
    "upsert_audience",
    "meta_sync_loop",
    "run_meta_sync_once",
]
