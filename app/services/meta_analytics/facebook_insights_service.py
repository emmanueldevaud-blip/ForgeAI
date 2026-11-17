"""Service d'insights Facebook (Page professionnelle) via Meta Graph API.

La Page Facebook est identifiee automatiquement depuis /me/accounts (pages
assignees au jeton System User). Un token Instagram ne donne PAS automatiquement
acces aux statistiques Facebook : la collecte tente /me/accounts et degrade
gracieusement si la permission ou la tache Page est manquante.

La collecte Facebook est independante d'Instagram : un echec d'un cote ne
bloque pas l'autre.
"""

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select as sa_select

from app.models.meta_analytics import (
    MetaAnalyticsAccount,
    MetaAnalyticsMedia,
)
from app.services.meta_analytics.meta_client import MetaGraphClient, MetaGraphError
from app.services.meta_analytics.normalizer import upsert_account_metric, upsert_snapshot
from app.core.config import get_settings

logger = logging.getLogger(__name__)

PAGE_FIELDS = "id,name,username,access_token,fan_count,website,instagram_business_account,link"
PAGE_INSIGHT_METRICS = [
    "page_video_views",
    "page_post_engagements",
    "page_views_total",
    "page_actions_post_reactions_like_total",
]
PAGE_POST_FIELDS = "id,message,created_time,permalink,type,likes.summary(true),comments.summary(true),shares"


class FacebookInsightsService:
    def __init__(self, db):
        self.db = db

    async def _ensure_account_from_page(self, client: MetaGraphClient, page: dict[str, Any]) -> MetaAnalyticsAccount:
        page_id = str(page.get("id"))
        result = await self.db.execute(
            sa_select(MetaAnalyticsAccount).where(
                MetaAnalyticsAccount.platform == "facebook",
                MetaAnalyticsAccount.platform_account_id == page_id,
            )
        )
        account = result.scalar_one_or_none()
        if account is None:
            account = MetaAnalyticsAccount(
                platform="facebook",
                platform_account_id=page_id,
                account_name=page.get("name") or "Page Facebook",
                username=page.get("username"),
                account_type="page",
                page_id=page_id,
            )
            self.db.add(account)
            await self.db.flush()
        else:
            account.account_name = page.get("name") or account.account_name
            account.username = page.get("username") or account.username
            account.page_id = page_id
            account.is_active = True
        await self.db.commit()
        return account

    async def list_accessible_pages(self, client: MetaGraphClient) -> list[dict[str, Any]]:
        try:
            data = await client.get_paginated("/me/accounts", {"fields": PAGE_FIELDS}, limit=100)
        except MetaGraphError as exc:
            logger.warning("Facebook /me/accounts echec: %s", exc)
            return []
        return data or []

    async def collect_page_metrics(self, client: MetaGraphClient, account: MetaAnalyticsAccount, page_token: str | None) -> dict[str, Any]:
        results: dict[str, Any] = {"page": account.platform_account_id, "metrics": {}, "errors": []}
        token_to_use = page_token or client.access_token

        original_token = client.access_token
        client.access_token = token_to_use
        try:
            try:
                page_data = await client.get(account.platform_account_id, {"fields": PAGE_FIELDS})
                if page_data.get("username"):
                    account.username = page_data.get("username")
                if page_data.get("name"):
                    account.account_name = page_data.get("name") or account.account_name
                basic = {
                    "page_fans": page_data.get("fan_count"),
                    "page_views_total": page_data.get("page_views_total"),
                    "website_clicks": page_data.get("website_clicks"),
                }
                for name, value in basic.items():
                    status = "available" if value is not None else "unavailable"
                    results["metrics"][name] = {"value": value, "status": status}
                    await upsert_snapshot(self.db, account, None, name, value, status, period="total")
                    await upsert_account_metric(self.db, account, name, value, status, period="total")
            except MetaGraphError as exc:
                logger.warning("Facebook metriques de base page echec: %s", exc)
                results["errors"].append(f"page_base: {exc}")

            since = (date.today() - timedelta(days=30)).isoformat()
            until = date.today().isoformat()
            try:
                insights = await client.get_insights(
                    account.platform_account_id,
                    PAGE_INSIGHT_METRICS,
                    period="day",
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
                    results["metrics"][name] = {"value": value, "status": status}
                    period_start = period_end = None
                    if end_time:
                        try:
                            period_end = date.fromisoformat(end_time[:10])
                            period_start = period_end
                        except ValueError:
                            pass
                    await upsert_snapshot(self.db, account, None, name, value, status, period="day", period_start=period_start, period_end=period_end)
                    await upsert_account_metric(self.db, account, name, value, status, period="day")
            except MetaGraphError as exc:
                logger.warning("Facebook insights page echec: %s", exc)
                results["errors"].append(f"insights: {exc}")

            try:
                results["posts"] = await self.collect_page_posts(client, account)
            except MetaGraphError as exc:
                logger.warning("Facebook publications page echec: %s", exc)
                results["errors"].append(f"posts: {exc}")
        finally:
            client.access_token = original_token

        return results

    async def collect_page_posts(self, client: MetaGraphClient, account: MetaAnalyticsAccount, limit: int = 50) -> list[dict[str, Any]]:
        try:
            posts = await client.get_paginated(
                f"{account.platform_account_id}/posts",
                {"fields": PAGE_POST_FIELDS},
                limit=limit,
            )
        except MetaGraphError as exc:
            logger.warning("Facebook liste publications echec: %s", exc)
            return []

        result_list = []
        for item in posts or []:
            post_id = item.get("id")
            if not post_id:
                continue
            created_at = None
            if item.get("created_time"):
                try:
                    created_at = date.fromisoformat(item["created_time"][:10])
                except ValueError:
                    pass

            db_result = await self.db.execute(
                sa_select(MetaAnalyticsMedia).where(
                    MetaAnalyticsMedia.account_id == account.id,
                    MetaAnalyticsMedia.media_id == post_id,
                )
            )
            media = db_result.scalar_one_or_none()
            likes = (item.get("likes") or {}).get("summary", {}).get("total_count")
            comments = (item.get("comments") or {}).get("summary", {}).get("total_count")
            shares = item.get("shares", {}).get("count") if isinstance(item.get("shares"), dict) else None

            if media is None:
                media = MetaAnalyticsMedia(
                    account_id=account.id,
                    media_id=post_id,
                    media_type=(item.get("type") or "POST").upper(),
                    permalink=item.get("permalink"),
                    caption=item.get("message"),
                    published_at=created_at,
                )
                self.db.add(media)
                await self.db.flush()
            else:
                media.caption = item.get("message") or media.caption
                media.permalink = item.get("permalink") or media.permalink
            await self.db.commit()

            for name, value in (("likes", likes), ("comments", comments), ("shares", shares)):
                status = "available" if value is not None else "unavailable"
                await upsert_snapshot(self.db, account, media.id, name, value, status, period="total")
                await upsert_account_metric(self.db, account, f"post_{name}", value, status, period="total")

            result_list.append({
                "id": media.id,
                "media_id": post_id,
                "type": media.media_type,
                "permalink": media.permalink,
                "created_at": created_at.isoformat() if created_at else None,
                "likes": likes,
                "comments": comments,
                "shares": shares,
            })

        return result_list
