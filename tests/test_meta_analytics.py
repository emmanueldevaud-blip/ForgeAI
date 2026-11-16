"""Tests cibles pour Meta Analytics & Intelligence (Community Manager IA).

Sans credentials Meta reelles : verificent le RBAC, le scoring editoriale,
la normalisation et le comportement des endpoints sans configuration Meta.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.services.meta_analytics.scoring_service import (
    MetaAnalyticsScoringService,
    ScoringWeights,
    compute_account_benchmarks,
)
from app.services.meta_analytics.normalizer import upsert_snapshot
from app.models.meta_analytics import (
    MetaAnalyticsAccount,
    MetaAnalyticsSnapshot,
    MetaAnalyticsSyncRun,
)


# ------------------------------------------------------------------ #
# Scoring editoriale
# ------------------------------------------------------------------ #
def test_scoring_weights_must_sum_to_100():
    with pytest.raises(ValueError):
        MetaAnalyticsScoringService(
            ScoringWeights(reach_relative=30, engagement_rate=30, shares_saves=30, video_performance=30, growth_attribution=30)
        )


def test_scoring_media_basic():
    scorer = MetaAnalyticsScoringService()
    media = {"reach": 1000, "likes": 100, "comments": 20, "shares": 10, "saves": 5, "video_views": 500, "is_video": True, "followers_gained": 5}
    benchmarks = {"avg_reach": 500, "avg_engagement_rate": 2.0, "avg_amplification": 15, "avg_followers_gained": 2}
    result = scorer.score_media(media, benchmarks)
    assert 0 <= result["score"] <= 100
    assert result["details"]["reach_relative"] == 100.0


def test_scoring_missing_metrics_neutral():
    scorer = MetaAnalyticsScoringService()
    media = {}
    benchmarks = {"avg_reach": 0, "avg_engagement_rate": 0, "avg_amplification": 0, "avg_followers_gained": 0}
    result = scorer.score_media(media, benchmarks)
    # Portee 50 + engagement 0 + amplif 0 + video 50 + croissance 50
    assert result["score"] == 27.5


def test_compute_account_benchmarks_empty():
    b = compute_account_benchmarks([])
    assert b["count"] == 0
    assert b["avg_reach"] == 0.0


# ------------------------------------------------------------------ #
# Normalisation (indisponibilite jamais remplacee par zero)
# ------------------------------------------------------------------ #
class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    def __init__(self):
        self.added = []
        self.committed = False

    async def execute(self, stmt):
        return _FakeResult(None)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        pass

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_upsert_snapshot_unavailable_not_zero():
    db = _FakeDB()
    account = MagicMock(spec=MetaAnalyticsAccount)
    account.id = 1
    account.platform = "instagram"
    await upsert_snapshot(db, account, None, "followers_count", None, "unavailable", period="day")
    snap = db.added[0]
    assert isinstance(snap, MetaAnalyticsSnapshot)
    assert snap.metric_value is None
    assert snap.metric_status == "unavailable"
    assert snap.metric_name == "followers_count"


# ------------------------------------------------------------------ #
# Endpoints : controle d'acces et indisponibilite Meta
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_overview_requires_view_permission(client, auth_headers):
    resp = await client.get("/sport/analytics/meta/overview", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_requires_sync_permission(client, auth_headers):
    resp = await client.post("/sport/analytics/meta/sync", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_overview_unavailable_without_meta_config(client, admin_headers):
    resp = await client.get("/sport/analytics/meta/overview", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert "Aucun compte Meta configure" in body.get("data", {}).get("message", "")


@pytest.mark.asyncio
async def test_ai_analyze_requires_analyze_permission(client, auth_headers):
    today = date.today()
    start = today - timedelta(days=7)
    resp = await client.post(
        "/sport/analytics/meta/ai/analyze",
        params={"period_start": start.isoformat(), "period_end": today.isoformat()},
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reports_require_reports_permission(client, auth_headers):
    resp = await client.post("/sport/analytics/meta/reports/generate?format=csv", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recommendations_require_analyze_permission(client, auth_headers):
    resp = await client.get("/sport/analytics/meta/ai/recommendations", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rbac_permissions_seeded(admin_user, db_session):
    from app.models.rbac import PermissionModel
    result = await db_session.execute(
        select(PermissionModel).where(PermissionModel.code.like("meta_analytics.%"))
    )
    codes = {r.code for r in result.scalars().all()}
    expected = {
        "meta_analytics.view",
        "meta_analytics.sync",
        "meta_analytics.analyze",
        "meta_analytics.reports",
        "meta_analytics.configure",
    }
    assert expected.issubset(codes), codes


def test_sync_run_account_id_nullable():
    """La trace de sync est creee avant la resolution du compte Meta.

    account_id doit rester nullable : sinon chaque cycle plante sur
    (1048, "Column 'account_id' cannot be null") et toute la synchro echoue.
    """
    col = MetaAnalyticsSyncRun.__table__.c.account_id
    assert col.nullable is True

    run = MetaAnalyticsSyncRun(platform="instagram", status="started")
    assert run.account_id is None
