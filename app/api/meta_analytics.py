"""Routes API Meta Analytics & Intelligence (Community Manager IA).

Prefixe : /sport/analytics/meta

Toutes les routes respectent le RBAC et les conventions API existantes.
Les tokens restent cotes serveur ; aucun secret n'est expose.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select as sa_select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_enabled, require_permission
from app.models.meta_analytics import (
    MetaAnalyticsAccount,
    MetaAnalyticsAccountMetrics,
    MetaAnalyticsAudience,
    MetaAnalyticsMedia,
    MetaAnalyticsSnapshot,
    MetaAnalyticsSyncRun,
    MetaAnalyticsAIAnalysis,
    MetaAnalyticsRecommendation,
)
from app.models.sport import CommunityManagerStrategy, EditorialCalendarEntry
from app.models.user import User
from app.services.meta_analytics import (
    MetaAnalyticsScoringService,
    MetaAnalyticsReportService,
    build_editorial_score_summary,
    run_meta_sync_once,
)
from app.services.meta_analytics.meta_client import MetaGraphError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sport/analytics/meta",
    tags=["meta-analytics"],
    dependencies=[Depends(require_module_enabled("community_manager"))],
)


def _parse_date(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide (YYYY-MM-DD)")


def _status_payload(status: str, data: Any = None, message: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status}
    if data is not None:
        payload["data"] = data
    if message:
        payload["message"] = message
    return payload


# ------------------------------------------------------------------ #
# Dependances
# ------------------------------------------------------------------ #
async def get_current_user_meta_view(current_user: User = Depends(require_permission("meta_analytics.view"))) -> User:
    return current_user


async def get_current_user_meta_sync(current_user: User = Depends(require_permission("meta_analytics.sync"))) -> User:
    return current_user


async def get_current_user_meta_analyze(current_user: User = Depends(require_permission("meta_analytics.analyze"))) -> User:
    return current_user


async def get_current_user_meta_reports(current_user: User = Depends(require_permission("meta_analytics.reports"))) -> User:
    return current_user


# ------------------------------------------------------------------ #
# Vue d'ensemble
# ------------------------------------------------------------------ #
@router.get("/overview")
async def overview(
    period: str = Query("30", description="7, 30 ou 90 jours"),
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    days = {"7": 7, "30": 30, "90": 90}.get(period, 30)
    end = date.today()
    start = end - timedelta(days=days - 1)

    result = await db.execute(sa_select(MetaAnalyticsAccount))
    accounts = result.scalars().all()

    overview_data: dict[str, Any] = {
        "periode": {"debut": start.isoformat(), "fin": end.isoformat(), "jours": days},
        "comptes": [],
        "instagram": None,
        "facebook": None,
        "date_derniere_synchronisation": None,
        "donnees_disponibles": False,
    }

    last_sync_dt = None
    for account in accounts:
        metrics_result = await db.execute(
            sa_select(MetaAnalyticsAccountMetrics).where(
                MetaAnalyticsAccountMetrics.account_id == account.id,
            )
        )
        metrics = {
            m.metric_name: {
                "valeur": m.metric_value,
                "statut": m.metric_status,
                "periode": m.period,
            }
            for m in metrics_result.scalars().all()
        }
        entry = {
            "platform": account.platform,
            "platform_account_id": account.platform_account_id,
            "account_name": account.account_name,
            "username": account.username,
            "metrics": metrics,
        }
        overview_data["comptes"].append(entry)
        if account.last_sync_at:
            if last_sync_dt is None or account.last_sync_at > last_sync_dt:
                last_sync_dt = account.last_sync_at
        if any(m["statut"] == "available" for m in metrics.values()):
            overview_data["donnees_disponibles"] = True
        if account.platform == "instagram":
            overview_data["instagram"] = entry
        elif account.platform == "facebook":
            overview_data["facebook"] = entry

    if last_sync_dt:
        overview_data["date_derniere_synchronisation"] = last_sync_dt.isoformat()

    if not accounts:
        overview_data["message"] = "Aucun compte Meta configure. Connectez Instagram/Facebook depuis la configuration Meta."

    return _status_payload("available" if overview_data["donnees_disponibles"] else "unavailable", overview_data)


# ------------------------------------------------------------------ #
# Instagram
# ------------------------------------------------------------------ #
@router.get("/instagram/account")
async def instagram_account(
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa_select(MetaAnalyticsAccount).where(MetaAnalyticsAccount.platform == "instagram")
    )
    account = result.scalar_one_or_none()
    if not account:
        return _status_payload("unavailable", {"message": "Aucun compte Instagram configure."})

    metrics_result = await db.execute(
        sa_select(MetaAnalyticsAccountMetrics).where(MetaAnalyticsAccountMetrics.account_id == account.id)
    )
    metrics = {
        m.metric_name: {"valeur": m.metric_value, "statut": m.metric_status, "periode": m.period}
        for m in metrics_result.scalars().all()
    }

    # Dernier snapshot followers_count pour l'evolution
    snap_result = await db.execute(
        sa_select(MetaAnalyticsSnapshot)
        .where(
            MetaAnalyticsSnapshot.account_id == account.id,
            MetaAnalyticsSnapshot.metric_name == "follower_count",
        )
        .order_by(desc(MetaAnalyticsSnapshot.collected_at))
        .limit(1)
    )
    # NOTE: filtre compte via join simplifie ci-après
    _ = snap_result

    return _status_payload(
        "available" if any(m["statut"] == "available" for m in metrics.values()) else "unavailable",
        {
            "platform": "instagram",
            "platform_account_id": account.platform_account_id,
            "account_name": account.account_name,
            "username": account.username,
            "business_portfolio_id": account.business_portfolio_id,
            "metrics": metrics,
            "derniere_synchro": account.last_sync_at.isoformat() if account.last_sync_at else None,
        },
    )


@router.get("/instagram/media")
async def instagram_media(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa_select(MetaAnalyticsAccount).where(MetaAnalyticsAccount.platform == "instagram")
    )
    account = result.scalar_one_or_none()
    if not account:
        return _status_payload("unavailable", {"message": "Aucun compte Instagram configure."})

    media_result = await db.execute(
        sa_select(MetaAnalyticsMedia)
        .where(MetaAnalyticsMedia.account_id == account.id)
        .order_by(desc(MetaAnalyticsMedia.collected_at))
        .limit(limit)
    )
    medias = []
    for media in media_result.scalars().all():
        snap_result = await db.execute(
            sa_select(MetaAnalyticsSnapshot).where(MetaAnalyticsSnapshot.media_id == media.id)
        )
        metrics = {
            s.metric_name: {"valeur": s.metric_value, "statut": s.metric_status, "periode": s.period}
            for s in snap_result.scalars().all()
        }
        medias.append({
            "id": media.id,
            "media_id": media.media_id,
            "media_type": media.media_type,
            "permalink": media.permalink,
            "caption": media.caption,
            "published_at": media.published_at.isoformat() if media.published_at else None,
            "metrics": metrics,
        })

    return _status_payload(
        "available" if medias else "unavailable",
        {"medias": medias, "total": len(medias)},
    )


@router.get("/instagram/media/{media_id}")
async def instagram_media_detail(
    media_id: int,
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(sa_select(MetaAnalyticsMedia).where(MetaAnalyticsMedia.id == media_id))
    media = result.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media introuvable")

    snap_result = await db.execute(
        sa_select(MetaAnalyticsSnapshot).where(MetaAnalyticsSnapshot.media_id == media.id)
    )
    metrics = {
        s.metric_name: {"valeur": s.metric_value, "statut": s.metric_status, "periode": s.period}
        for s in snap_result.scalars().all()
    }

    return _status_payload(
        "available",
        {
            "id": media.id,
            "media_id": media.media_id,
            "media_type": media.media_type,
            "permalink": media.permalink,
            "caption": media.caption,
            "published_at": media.published_at.isoformat() if media.published_at else None,
            "metrics": metrics,
        },
    )


# ------------------------------------------------------------------ #
# Facebook
# ------------------------------------------------------------------ #
@router.get("/facebook/page")
async def facebook_page(
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa_select(MetaAnalyticsAccount).where(MetaAnalyticsAccount.platform == "facebook")
    )
    accounts = result.scalars().all()
    pages = []
    for account in accounts:
        metrics_result = await db.execute(
            sa_select(MetaAnalyticsAccountMetrics).where(MetaAnalyticsAccountMetrics.account_id == account.id)
        )
        metrics = {
            m.metric_name: {"valeur": m.metric_value, "statut": m.metric_status, "periode": m.period}
            for m in metrics_result.scalars().all()
        }
        pages.append({
            "id": account.id,
            "page_id": account.platform_account_id,
            "page_name": account.account_name,
            "instagram_account_id": account.instagram_account_id,
            "metrics": metrics,
            "derniere_synchro": account.last_sync_at.isoformat() if account.last_sync_at else None,
        })

    return _status_payload(
        "available" if pages else "unavailable",
        {"pages": pages, "total": len(pages)},
    )


@router.get("/facebook/posts")
async def facebook_posts(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(sa_select(MetaAnalyticsAccount).where(MetaAnalyticsAccount.platform == "facebook"))
    accounts = result.scalars().all()
    posts = []
    for account in accounts:
        media_result = await db.execute(
            sa_select(MetaAnalyticsMedia)
            .where(MetaAnalyticsMedia.account_id == account.id)
            .order_by(desc(MetaAnalyticsMedia.collected_at))
            .limit(limit)
        )
        for media in media_result.scalars().all():
            snap_result = await db.execute(
                sa_select(MetaAnalyticsSnapshot).where(MetaAnalyticsSnapshot.media_id == media.id)
            )
            metrics = {
                s.metric_name: {"valeur": s.metric_value, "statut": s.metric_status, "periode": s.period}
                for s in snap_result.scalars().all()
            }
            posts.append({
                "id": media.id,
                "media_id": media.media_id,
                "page_id": account.platform_account_id,
                "page_name": account.account_name,
                "type": media.media_type,
                "permalink": media.permalink,
                "caption": media.caption,
                "created_at": media.published_at.isoformat() if media.published_at else None,
                "metrics": metrics,
            })

    return _status_payload(
        "available" if posts else "unavailable",
        {"posts": posts, "total": len(posts)},
    )


# ------------------------------------------------------------------ #
# Performance editoriale (scoring)
# ------------------------------------------------------------------ #
@router.get("/performance")
async def performance(
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(sa_select(MetaAnalyticsAccount).where(MetaAnalyticsAccount.platform == "instagram"))
    account = result.scalar_one_or_none()
    if not account:
        return _status_payload("unavailable", {"message": "Aucun compte Instagram configure."})

    media_result = await db.execute(
        sa_select(MetaAnalyticsMedia)
        .where(MetaAnalyticsMedia.account_id == account.id)
        .order_by(desc(MetaAnalyticsMedia.collected_at))
    )
    media_list = []
    for media in media_result.scalars().all():
        snap_result = await db.execute(
            sa_select(MetaAnalyticsSnapshot).where(MetaAnalyticsSnapshot.media_id == media.id)
        )
        metrics = {}
        for s in snap_result.scalars().all():
            if s.metric_status == "available" and s.metric_value is not None:
                metrics[s.metric_name] = s.metric_value
        if metrics:
            reach = metrics.get("reach") or 0
            interactions = sum(metrics.get(k, 0) or 0 for k in ("likes", "comments", "shares", "saves"))
            engagement_rate = (interactions / reach * 100.0) if reach else 0.0
            media_list.append({
                "media_id": media.media_id,
                "media_type": media.media_type,
                "permalink": media.permalink,
                "reach": metrics.get("reach"),
                "likes": metrics.get("likes"),
                "comments": metrics.get("comments"),
                "shares": metrics.get("shares"),
                "saves": metrics.get("saves"),
                "video_views": metrics.get("video_views"),
                "followers_gained": metrics.get("followers_gained"),
                "engagement_rate": round(engagement_rate, 2),
                "is_video": media.media_type in ("VIDEO", "REELS"),
            })

    scorer = MetaAnalyticsScoringService()
    from app.services.meta_analytics.scoring_service import compute_account_benchmarks

    benchmarks = compute_account_benchmarks(media_list)
    scored = []
    for m in media_list:
        res = scorer.score_media(m, benchmarks)
        scored.append({
            "media_id": m["media_id"],
            "media_type": m["media_type"],
            "permalink": m["permalink"],
            "score": res["score"],
            "details": res["details"],
            "indicators": res["indicators_used"],
        })
    scored.sort(key=lambda x: x["score"], reverse=True)

    return _status_payload(
        "available" if scored else "unavailable",
        {
            "benchmarks": benchmarks,
            "medias": scored,
            "meilleur_score": scored[0] if scored else None,
            "ponderation": {
                "portee_relative": 20,
                "taux_engagement": 20,
                "partages_enregistrements": 25,
                "performance_video": 20,
                "croissance_attribuable": 15,
            },
        },
    )


# ------------------------------------------------------------------ #
# Audience
# ------------------------------------------------------------------ #
@router.get("/audience")
async def audience(
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(sa_select(MetaAnalyticsAccount))
    accounts = result.scalars().all()
    data = {"instagram": {}, "facebook": {}, "disponible": False}
    for account in accounts:
        aud_result = await db.execute(
            sa_select(MetaAnalyticsAudience).where(MetaAnalyticsAudience.account_id == account.id)
        )
        audience = [
            {
                "dimension": a.dimension,
                "valeur": a.dimension_value,
                "metrique": a.metric_value,
                "statut": a.metric_status,
            }
            for a in aud_result.scalars().all()
        ]
        if audience:
            data["disponible"] = True
            if account.platform == "instagram":
                data["instagram"] = audience
            elif account.platform == "facebook":
                data["facebook"] = audience
    return _status_payload("available" if data["disponible"] else "unavailable", data)


# ------------------------------------------------------------------ #
# Historique
# ------------------------------------------------------------------ #
@router.get("/history")
async def history(
    metric: str = Query("follower_count"),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    start = date.today() - timedelta(days=days)
    result = await db.execute(sa_select(MetaAnalyticsAccount))
    accounts = result.scalars().all()
    series = []
    for account in accounts:
        snap_result = await db.execute(
            sa_select(MetaAnalyticsSnapshot)
            .where(
                MetaAnalyticsSnapshot.account_id == account.id,
                MetaAnalyticsSnapshot.metric_name == metric,
                MetaAnalyticsSnapshot.collected_at >= datetime(start.year, start.month, start.day),
                MetaAnalyticsSnapshot.metric_status == "available",
            )
            .order_by(MetaAnalyticsSnapshot.collected_at.asc())
        )
        points = [
            {"date": s.collected_at.isoformat(), "valeur": s.metric_value}
            for s in snap_result.scalars().all()
        ]
        if points:
            series.append({"compte": account.platform_account_id, "platform": account.platform, "points": points})

    return _status_payload(
        "available" if series else "unavailable",
        {"metric": metric, "jours": days, "series": series},
    )


# ------------------------------------------------------------------ #
# Synchronisation
# ------------------------------------------------------------------ #
@router.post("/sync")
async def sync(
    background: bool = Query(False, description="Lancer en arriere-plan"),
    current_user: User = Depends(get_current_user_meta_sync),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await run_meta_sync_once()
    except MetaGraphError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Synchro Meta echec")
        raise HTTPException(status_code=502, detail=f"Synchro impossible: {exc}") from exc
    return _status_payload(result.get("overall_status", "completed"), result)


@router.get("/sync/status")
async def sync_status(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_meta_view),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa_select(MetaAnalyticsSyncRun)
        .order_by(desc(MetaAnalyticsSyncRun.started_at))
        .limit(limit)
    )
    runs = []
    for run in result.scalars().all():
        runs.append({
            "id": run.id,
            "platform": run.platform,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "accounts_processed": run.accounts_processed,
            "metrics_collected": run.metrics_collected,
            "error_message": run.error_message,
        })
    return _status_payload("available", {"sync_runs": runs})


# ------------------------------------------------------------------ #
# Intelligence artificielle
# ------------------------------------------------------------------ #
@router.post("/ai/analyze")
async def ai_analyze(
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    current_user: User = Depends(get_current_user_meta_analyze),
    db: AsyncSession = Depends(get_db),
):
    ps = _parse_date(period_start, date.today() - timedelta(days=30))
    pe = _parse_date(period_end, date.today())

    from app.services.meta_analytics.instagram_insights_service import InstagramInsightsService
    from app.services.meta_analytics.facebook_insights_service import FacebookInsightsService
    from app.services.meta_analytics.meta_client import build_client, MetaGraphError

    try:
        client, connection = await build_client(db)
    except MetaGraphError as exc:
        return _status_payload("unavailable", {"erreur": str(exc)})

    try:
        ig_service = InstagramInsightsService(db)
        ig_account = await ig_service._ensure_account(client, connection)
        ig_data = await ig_service.collect_account_metrics(client, ig_account)
        ig_media = await ig_service.collect_media(client, ig_account, limit=30)
        await client.aclose()
    except MetaGraphError as exc:
        logger.warning("IA analyse Instagram indisponible: %s", exc)
        ig_data = {"erreur": str(exc)}
        ig_media = {"media": []}
        try:
            await client.aclose()
        except Exception:
            pass

    media_performance = []
    for m in ig_media.get("media", []):
        media_performance.append({
            "media_id": m["media_id"],
            "media_type": m["media_type"],
            "permalink": m["permalink"],
            "reach": None,
            "likes": None,
            "comments": None,
            "shares": None,
            "saves": None,
        })

    from app.services.meta_analytics.ai_service import MetaAnalyticsAIService

    ai_service = MetaAnalyticsAIService(db)
    analysis = await ai_service.analyze_performance(ps, pe, ig_data, {}, media_performance)

    # Persister l'analyse
    from app.models.meta_analytics import MetaAnalyticsAIAnalysis
    analysis_row = MetaAnalyticsAIAnalysis(
        period_start=ps,
        period_end=pe,
        analysis_type="performance",
        summary=analysis.get("bilan", "Analyse disponible"),
        findings_json=analysis,
        confidence=analysis.get("note_methode", {}).get("confiance") if isinstance(analysis.get("note_methode"), dict) else None,
    )
    db.add(analysis_row)
    await db.commit()
    await db.refresh(analysis_row)

    return _status_payload(
        "available" if analysis.get("disponible") else "unavailable",
        {"analyse": analysis, "analyse_id": analysis_row.id},
    )


@router.get("/ai/recommendations")
async def ai_recommendations(
    current_user: User = Depends(get_current_user_meta_analyze),
    db: AsyncSession = Depends(get_db),
):
    from app.services.meta_analytics.ai_service import MetaAnalyticsAIService

    ai_service = MetaAnalyticsAIService(db)

    # Recuperer les medias recents pour calculer des recommandations
    result = await db.execute(
        sa_select(MetaAnalyticsAccount).where(MetaAnalyticsAccount.platform == "instagram")
    )
    account = result.scalar_one_or_none()
    recommendations = []

    if account:
        media_result = await db.execute(
            sa_select(MetaAnalyticsMedia)
            .where(MetaAnalyticsMedia.account_id == account.id)
            .order_by(desc(MetaAnalyticsMedia.collected_at))
            .limit(30)
        )
        media_list = []
        for media in media_result.scalars().all():
            snap_result = await db.execute(
                sa_select(MetaAnalyticsSnapshot).where(MetaAnalyticsSnapshot.media_id == media.id)
            )
            metrics = {}
            for s in snap_result.scalars().all():
                if s.metric_status == "available" and s.metric_value is not None:
                    metrics[s.metric_name] = s.metric_value
            if metrics:
                media_list.append({
                    "media_id": media.media_id,
                    "media_type": media.media_type,
                    "permalink": media.permalink,
                    "reach": metrics.get("reach"),
                    "likes": metrics.get("likes"),
                    "comments": metrics.get("comments"),
                    "shares": metrics.get("shares"),
                    "saves": metrics.get("saves"),
                    "video_views": metrics.get("video_views"),
                    "followers_gained": metrics.get("followers_gained"),
                    "is_video": media.media_type in ("VIDEO", "REELS"),
                })

        # Calculer le taux d'engagement pour chaque media
        from app.services.meta_analytics.scoring_service import compute_account_benchmarks
        benchmarks = compute_account_benchmarks(media_list)
        for m in media_list:
            reach = m.get("reach") or 0
            interactions = sum(m.get(k, 0) or 0 for k in ("likes", "comments", "shares", "saves"))
            m["engagement_rate"] = (interactions / reach * 100.0) if reach else 0.0

        # Generer des recommandations IA
        from datetime import date, timedelta
        today = date.today()
        period_start = today - timedelta(days=30)
        analysis = await ai_service.analyze_performance(period_start, today, {}, {}, media_list)
        recommendations = await ai_service.generate_recommendations(period_start, today, analysis)

    # Recuperer aussi les recommandations stockees en DB
    result = await db.execute(
        sa_select(MetaAnalyticsRecommendation)
        .order_by(desc(MetaAnalyticsRecommendation.created_at))
        .limit(50)
    )
    stored = []
    for rec in result.scalars().all():
        stored.append({
            "id": rec.id,
            "type": rec.recommendation_type,
            "titre": rec.title,
            "description": rec.description,
            "justification": rec.rationale,
            "indicateurs": rec.indicators_json,
            "confiance": rec.confidence,
            "statut": rec.status,
            "action": rec.action,
            "lie_au_calendrier": rec.linked_entry_id,
            "lie_a_la_publication": rec.linked_publication_id,
            "cree_le": rec.created_at.isoformat() if rec.created_at else None,
            "decide_le": rec.decided_at.isoformat() if rec.decided_at else None,
        })

    return _status_payload("available", {"recommandations": recommendations or stored})


@router.post("/recommendations/{recommendation_id}/to-calendar")
async def recommendation_to_calendar(
    recommendation_id: int,
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
    db: AsyncSession = Depends(get_db),
):
    """Transforme une recommandation IA en entree de calendrier editorial."""
    result = await db.execute(
        sa_select(MetaAnalyticsRecommendation).where(MetaAnalyticsRecommendation.id == recommendation_id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommandation introuvable")

    # Resoudre la strategie de l'utilisateur
    from app.models.sport import SportAthlete

    athlete_result = await db.execute(
        sa_select(SportAthlete).where(SportAthlete.user_id == current_user.id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if not athlete:
        raise HTTPException(status_code=400, detail="Aucun athlete associe a l'utilisateur")

    strategy_result = await db.execute(
        sa_select(CommunityManagerStrategy).where(CommunityManagerStrategy.athlete_id == athlete.id)
    )
    strategy = strategy_result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=400, detail="Strategie editoriale non configuree")

    from datetime import date as _date
    entry = EditorialCalendarEntry(
        strategy_id=strategy.id,
        date=_date.today(),
        topic=rec.title,
        theme=None,
        objective=None,
        notes=f"Recommandation IA Meta Analytics: {rec.rationale or rec.description}",
        hashtags=None,
        status="brouillon",
        content_type="manuel",
        source="meta_analytics",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    # Marquer la recommandation comme implementee liee au calendrier
    rec.status = "implemented"
    rec.action = "calendar"
    rec.linked_entry_id = entry.id
    rec.decided_at = datetime.now(timezone.utc)
    await db.commit()

    return _status_payload(
        "implemented",
        {
            "recommendation_id": rec.id,
            "calendar_entry_id": entry.id,
            "topic": entry.topic,
            "status": entry.status,
        },
    )


# ------------------------------------------------------------------ #
# Rapports
# ------------------------------------------------------------------ #
@router.post("/reports/generate")
async def reports_generate(
    format: str = Query("pdf", description="pdf ou csv"),
    period_start: str = Query(None),
    period_end: str = Query(None),
    current_user: User = Depends(get_current_user_meta_reports),
    db: AsyncSession = Depends(get_db),
):
    ps = _parse_date(period_start, date.today() - timedelta(days=30))
    pe = _parse_date(period_end, date.today())

    report_service = MetaAnalyticsReportService(db)
    report_data = await report_service.gather_report_data(ps, pe)

    if format == "csv":
        content = report_service.export_csv(report_data)
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="meta_analytics_{ps}_{pe}.csv"'},
        )

    if format == "pdf":
        content = report_service.export_pdf(report_data)
        return StreamingResponse(
            iter([content]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="meta_analytics_{ps}_{pe}.pdf"'},
        )

    raise HTTPException(status_code=400, detail="Format non supporte (pdf ou csv)")


@router.get("/health")
async def meta_analytics_health():
    return {"status": "ok", "module": "meta_analytics"}
