"""Service d'insights Instagram (compte professionnel) via Meta Graph API.

Toutes les metrics sont recuperees depuis l'API reelle. Une metrique
indisponible est signalee avec le statut 'unavailable' (jamais remplacee par
zero). L'echec d'Instagram ne doit pas bloquer Facebook (collecte independante).
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select as sa_select

from app.models.meta_analytics import (
    MetaAnalyticsAccount,
    MetaAnalyticsMedia,
)
from app.services.meta_analytics.meta_client import MetaGraphClient, MetaGraphError, build_client
from app.services.meta_analytics.normalizer import upsert_audience, upsert_account_metric, upsert_snapshot

logger = logging.getLogger(__name__)

INSTAGRAM_ACCOUNT_METRICS = [
    "follower_count",
    "reach",
]

INSTAGRAM_MEDIA_METRICS_COMMON = ["reach", "likes", "comments", "shares", "saved", "views"]
# Les stories n'exposent pas les metriques d'engagement / likes / comments / saves.
INSTAGRAM_MEDIA_METRICS_STORY = ["reach", "shares", "views"]

# Metriques Meta renommees depuis l'ancienne generation : on conserve le nom
# historique attendu par le scoring, l'API et le frontend.
MEDIA_METRIC_STORAGE_NAMES = {
    "saved": "saves",
    "views": "video_views",
}

INSTAGRAM_ACCOUNT_FIELDS = "id,username,name,followers_count,follows_count,media_count"
INSTAGRAM_MEDIA_FIELDS = "id,media_type,media_url,permalink,caption,timestamp,like_count,comments_count"


class InstagramInsightsService:
    def __init__(self, db):
        self.db = db

    async def _ensure_account(self, client: MetaGraphClient, connection: dict[str, str]) -> MetaAnalyticsAccount:
        ig_user_id = connection["instagram_user_id"]
        if not ig_user_id:
            raise MetaGraphError("Aucun compte Instagram associe au jeton Meta.", status=403)

        me = await client.get(f"{ig_user_id}", {"fields": INSTAGRAM_ACCOUNT_FIELDS})
        account_name = me.get("name") or me.get("username") or "Instagram"

        result = await self.db.execute(
            sa_select(MetaAnalyticsAccount).where(
                MetaAnalyticsAccount.platform == "instagram",
                MetaAnalyticsAccount.platform_account_id == ig_user_id,
            )
        )
        account = result.scalar_one_or_none()
        if account is None:
            account = MetaAnalyticsAccount(
                platform="instagram",
                platform_account_id=ig_user_id,
                account_name=account_name,
                username=me.get("username"),
                account_type="business",
                business_portfolio_id=connection.get("client_business_id") or None,
            )
            self.db.add(account)
            await self.db.flush()
        else:
            account.account_name = account_name
            account.username = me.get("username") or account.username
            account.business_portfolio_id = connection.get("client_business_id") or account.business_portfolio_id
            account.is_active = True
        await self.db.commit()
        return account

    async def collect_account_metrics(self, client: MetaGraphClient, account: MetaAnalyticsAccount, period: str = "day") -> dict[str, Any]:
        since = (date.today() - timedelta(days=30)).isoformat()
        until = date.today().isoformat()
        results: dict[str, Any] = {"account": account.platform_account_id, "metrics": {}, "errors": []}

        try:
            me = await client.get(f"{account.platform_account_id}", {"fields": INSTAGRAM_ACCOUNT_FIELDS})
            basic = {
                "followers_count": me.get("followers_count"),
                "follows_count": me.get("follows_count"),
                "media_count": me.get("media_count"),
            }
            for name, value in basic.items():
                status = "available" if value is not None else "unavailable"
                results["metrics"][name] = {"value": value, "status": status}
                await upsert_snapshot(self.db, account, None, name, value, status, period=period)
                await upsert_account_metric(self.db, account, name, value, status, period=period)
        except MetaGraphError as exc:
            logger.warning("Instagram metriques de base echec: %s", exc)
            results["errors"].append(f"metriques_base: {exc}")

        try:
            insights = await client.get_insights(
                account.platform_account_id,
                INSTAGRAM_ACCOUNT_METRICS,
                period=period,
                since=since,
                until=until,
            )
            for item in insights.get("data") or []:
                name = item.get("name")
                values = item.get("values") or []
                if not values:
                    continue
                latest = values[-1]
                value = latest.get("value")
                end_time = latest.get("end_time")
                status = "available" if value is not None else "unavailable"
                results["metrics"][name] = {"value": value, "status": status, "values": values}
                period_start = period_end = None
                if end_time:
                    try:
                        period_end = date.fromisoformat(end_time[:10])
                        period_start = period_end
                    except ValueError:
                        pass
                await upsert_snapshot(self.db, account, None, name, value, status, period=period, period_start=period_start, period_end=period_end)
                await upsert_account_metric(self.db, account, name, value, status, period=period)
        except MetaGraphError as exc:
            logger.warning("Instagram insights echec: %s", exc)
            results["errors"].append(f"insights: {exc}")

        try:
            results["audience"] = await self._collect_audience(client, account)
        except MetaGraphError as exc:
            logger.warning("Instagram audience echec: %s", exc)
            results["errors"].append(f"audience: {exc}")

        return results

    async def _collect_audience(self, client: MetaGraphClient, account: MetaAnalyticsAccount) -> dict[str, Any]:
        audience: dict[str, Any] = {}
        try:
            data = await client.get_insights(
                account.platform_account_id,
                ["follower_count", "reach"],
                period="day",
            )
            for item in data.get("data") or []:
                name = item.get("name")
                values = item.get("values") or []
                if not values:
                    continue
                latest = values[-1]
                await upsert_audience(self.db, account, "insight", name, latest.get("value"), "available")
        except MetaGraphError:
            pass
        return audience

    async def collect_media(self, client: MetaGraphClient, account: MetaAnalyticsAccount, limit: int = 50) -> dict[str, Any]:
        results: dict[str, Any] = {"media": [], "errors": [], "warnings": []}
        try:
            media_list = await client.get_paginated(
                f"{account.platform_account_id}/media",
                {"fields": INSTAGRAM_MEDIA_FIELDS},
                limit=limit,
            )
        except MetaGraphError as exc:
            logger.warning("Instagram liste medias echec: %s", exc)
            results["errors"].append(f"medias: {exc}")
            return results

        for item in media_list:
            media_id = item.get("id")
            if not media_id:
                continue
            media_type = item.get("media_type")
            published_at = None
            if item.get("timestamp"):
                try:
                    published_at = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                except ValueError:
                    pass

            result = await self.db.execute(
                sa_select(MetaAnalyticsMedia).where(
                    MetaAnalyticsMedia.account_id == account.id,
                    MetaAnalyticsMedia.media_id == media_id,
                )
            )
            media = result.scalar_one_or_none()
            if media is None:
                media = MetaAnalyticsMedia(
                    account_id=account.id,
                    media_id=media_id,
                    media_type=media_type,
                    media_url=item.get("media_url"),
                    permalink=item.get("permalink"),
                    caption=item.get("caption"),
                    published_at=published_at,
                )
                self.db.add(media)
                await self.db.flush()
            else:
                media.media_type = media_type
                media.media_url = item.get("media_url") or media.media_url
                media.permalink = item.get("permalink") or media.permalink
                media.caption = item.get("caption") or media.caption
                if published_at:
                    media.published_at = published_at
                media.collected_at = datetime.now(timezone.utc)
            await self.db.commit()

            media_metrics = (
                list(INSTAGRAM_MEDIA_METRICS_STORY)
                if media_type == "STORY"
                else list(INSTAGRAM_MEDIA_METRICS_COMMON)
            )
            try:
                insights = await client.get_insights(media_id, media_metrics, period="lifetime")
                for item in insights.get("data") or []:
                    name = MEDIA_METRIC_STORAGE_NAMES.get(item.get("name"), item.get("name"))
                    values = item.get("values") or []
                    if not values:
                        continue
                    latest = values[-1]
                    value = latest.get("value")
                    status = "available" if value is not None else "unavailable"
                    await upsert_snapshot(self.db, account, media.id, name, value, status, period="lifetime")
            except MetaGraphError as exc:
                # Insights non disponibles pour ce media (ex. publie avant la
                # connexion du compte) : avertissement non bloquant.
                logger.warning("Instagram insights media %s indisponibles: %s", media_id, exc)
                results.setdefault("warnings", []).append(f"media_{media_id}: {exc}")

            results["media"].append({
                "id": media.id,
                "media_id": media_id,
                "media_type": media_type,
                "permalink": media.permalink,
                "published_at": media.published_at.isoformat() if media.published_at else None,
            })

        return results
