"""Normalisation et persistance des metriques Meta Analytics.

Fournit des helpers d'upsert utilises par les collecteurs Instagram et Facebook.
Une metrique indisponible est stockee avec metric_status='unavailable' et
metric_value=None (jamais convertie en zero).
"""

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meta_analytics import (
    MetaAnalyticsAccount,
    MetaAnalyticsAccountMetrics,
    MetaAnalyticsAudience,
    MetaAnalyticsSnapshot,
)


async def upsert_snapshot(
    db: AsyncSession,
    account: MetaAnalyticsAccount,
    media_id: int | None,
    metric_name: str,
    value: Any,
    status: str,
    period: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    api_version: str | None = None,
    source_api: str | None = "graph.facebook.com",
) -> None:
    result = await db.execute(
        sa_select(MetaAnalyticsSnapshot).where(
            MetaAnalyticsSnapshot.account_id == account.id,
            MetaAnalyticsSnapshot.media_id == media_id,
            MetaAnalyticsSnapshot.metric_name == metric_name,
            MetaAnalyticsSnapshot.period == period,
        ).order_by(MetaAnalyticsSnapshot.collected_at.desc()).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        db.add(MetaAnalyticsSnapshot(
            account_id=account.id,
            media_id=media_id,
            platform=account.platform,
            metric_name=metric_name,
            metric_value=value,
            metric_status=status,
            period=period,
            period_start=period_start,
            period_end=period_end,
            api_version=api_version,
            source_api=source_api,
        ))
    else:
        existing.metric_value = value
        existing.metric_status = status
        existing.collected_at = datetime.now(timezone.utc)
        existing.api_version = api_version or existing.api_version
    await db.commit()


async def upsert_account_metric(
    db: AsyncSession,
    account: MetaAnalyticsAccount,
    metric_name: str,
    value: Any,
    status: str,
    period: str | None = None,
) -> None:
    result = await db.execute(
        sa_select(MetaAnalyticsAccountMetrics).where(
            MetaAnalyticsAccountMetrics.account_id == account.id,
            MetaAnalyticsAccountMetrics.metric_name == metric_name,
            MetaAnalyticsAccountMetrics.period == period,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        db.add(MetaAnalyticsAccountMetrics(
            account_id=account.id,
            metric_name=metric_name,
            metric_value=value,
            metric_status=status,
            period=period,
        ))
    else:
        existing.metric_value = value
        existing.metric_status = status
    await db.commit()


async def upsert_audience(
    db: AsyncSession,
    account: MetaAnalyticsAccount,
    dimension: str,
    dimension_value: str,
    value: Any,
    status: str,
) -> None:
    result = await db.execute(
        sa_select(MetaAnalyticsAudience).where(
            MetaAnalyticsAudience.account_id == account.id,
            MetaAnalyticsAudience.dimension == dimension,
            MetaAnalyticsAudience.dimension_value == dimension_value,
        ).order_by(MetaAnalyticsAudience.collected_at.desc()).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        db.add(MetaAnalyticsAudience(
            account_id=account.id,
            dimension=dimension,
            dimension_value=dimension_value,
            metric_value=value,
            metric_status=status,
        ))
    else:
        existing.metric_value = value
        existing.metric_status = status
    await db.commit()
