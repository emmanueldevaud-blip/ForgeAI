"""Service de collecte Meta Analytics : synchronisation incrémentale.

Orchestre Instagram et Facebook de maniere independante : l'echec de l'une
des plateformes ne bloque pas l'autre. Historise les resultats dans
meta_analytics_sync_runs et gere la pagination, les limites API et les tokens
expires/insuffisants.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select as sa_select

from app.models.meta_analytics import MetaAnalyticsAccount, MetaAnalyticsSyncRun
from app.services.meta_analytics.facebook_insights_service import FacebookInsightsService
from app.services.meta_analytics.instagram_insights_service import InstagramInsightsService
from app.services.meta_analytics.meta_client import MetaGraphClient, MetaGraphError, build_client

logger = logging.getLogger(__name__)


class MetaCollectorService:
    """Collecteur principal : collecte Instagram et Facebook separément."""

    def __init__(self, db):
        self.db = db

    async def sync_all(self, media_limit: int = 50) -> dict[str, Any]:
        """Collecte Instagram et Facebook. Retourne un rapport par plateforme."""
        report: dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "platforms": {},
            "overall_status": "completed",
            "errors": [],
        }

        # Protection multi-worker : verifier qu'aucune synchro n'est deja en cours
        from sqlalchemy import select as sa_select
        in_progress = await self.db.execute(
            sa_select(MetaAnalyticsSyncRun)
            .where(MetaAnalyticsSyncRun.status == "started")
            .where(MetaAnalyticsSyncRun.finished_at.is_(None))
            .limit(1)
        )
        if in_progress.scalar_one_or_none():
            report["overall_status"] = "skipped"
            report["errors"].append("Une synchronisation est deja en cours (protection multi-worker)")
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            return report

        try:
            client, connection = await build_client(self.db)
        except MetaGraphError as exc:
            logger.warning("Configuration Meta indisponible: %s", exc)
            report["overall_status"] = "failed"
            report["errors"].append(str(exc))
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            return report

        try:
            # ---------- Instagram ----------
            ig_report = await self._sync_platform(
                client, connection, "instagram",
                InstagramInsightsService(self.db),
                media_limit,
            )
            report["platforms"]["instagram"] = ig_report
            if ig_report["status"] == "failed":
                report["overall_status"] = "partial"
                report["errors"].extend(ig_report.get("errors", []))

            # ---------- Facebook ----------
            fb_report = await self._sync_facebook(client, connection, media_limit)
            report["platforms"]["facebook"] = fb_report
            if fb_report["status"] == "failed":
                report["overall_status"] = "partial"
                report["errors"].extend(fb_report.get("errors", []))

            if report["overall_status"] == "completed" and ig_report["status"] == "failed" and fb_report["status"] == "failed":
                report["overall_status"] = "failed"

        finally:
            await client.aclose()

        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        return report

    async def _sync_platform(self, client, connection, platform, service, media_limit) -> dict[str, Any]:
        run = MetaAnalyticsSyncRun(
            platform=platform,
            status="started",
            accounts_processed=0,
            metrics_collected=0,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        result: dict[str, Any] = {"platform": platform, "status": "started", "accounts": [], "errors": []}
        try:
            account = await service._ensure_account(client, connection)
            run.account_id = account.id
            await self.db.commit()

            # Metriques de compte
            metrics = await service.collect_account_metrics(client, account)
            account.last_sync_at = datetime.now(timezone.utc)
            await self.db.commit()

            # Medias
            media = await service.collect_media(client, account, limit=media_limit)
            await self.db.commit()

            run.accounts_processed = 1
            run.metrics_collected = len(metrics.get("metrics", {})) + len(media.get("media", []))
            run.status = "completed" if not metrics.get("errors") and not media.get("errors") else "partial"
            run.finished_at = datetime.now(timezone.utc)
            run.details_json = {
                "metrics": metrics.get("metrics"),
                "errors": metrics.get("errors") + media.get("errors", []),
            }
            await self.db.commit()

            result["status"] = run.status
            result["accounts"] = [{
                "id": account.id,
                "platform_account_id": account.platform_account_id,
                "account_name": account.account_name,
                "username": account.username,
                "metrics": metrics.get("metrics"),
                "errors": metrics.get("errors"),
            }]
            result["media"] = media.get("media", [])
            result["errors"] = metrics.get("errors", []) + media.get("errors", [])

        except MetaGraphError as exc:
            logger.warning("Collecte %s echec: %s", platform, exc)
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(exc)
            await self.db.commit()
            result["status"] = "failed"
            result["errors"].append(str(exc))
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Collecte %s erreur inattendue", platform)
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(exc)
            await self.db.commit()
            result["status"] = "failed"
            result["errors"].append(f"erreur inattendue: {exc}")

        return result

    async def _sync_facebook(self, client, connection, media_limit) -> dict[str, Any]:
        run = MetaAnalyticsSyncRun(
            platform="facebook",
            status="started",
            accounts_processed=0,
            metrics_collected=0,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        result: dict[str, Any] = {"platform": "facebook", "status": "started", "pages": [], "errors": []}
        try:
            service = FacebookInsightsService(self.db)
            pages = await service.list_accessible_pages(client)
            if not pages:
                run.status = "completed"
                run.finished_at = datetime.now(timezone.utc)
                run.details_json = {"note": "Aucune page Facebook accessible via le jeton configure"}
                await self.db.commit()
                result["status"] = "completed"
                result["errors"].append("Aucune page Facebook accessible (verifiez les permissions/pages assignees)")
                return result

            total_metrics = 0
            for page in pages:
                page_id = str(page.get("id"))
                page_token = page.get("access_token")
                try:
                    account = await service._ensure_account_from_page(client, page)
                    run.account_id = account.id
                    await self.db.commit()

                    page_report = await service.collect_page_metrics(client, account, page_token)
                    account.last_sync_at = datetime.now(timezone.utc)
                    await self.db.commit()

                    total_metrics += len(page_report.get("metrics", {})) + len(page_report.get("posts", []))
                    result["pages"].append({
                        "id": account.id,
                        "page_id": page_id,
                        "page_name": page.get("name"),
                        "metrics": page_report.get("metrics"),
                        "posts": page_report.get("posts"),
                        "errors": page_report.get("errors"),
                    })
                    result["errors"].extend(page_report.get("errors", []))
                except MetaGraphError as exc:
                    logger.warning("Facebook page %s echec: %s", page_id, exc)
                    result["errors"].append(f"page_{page_id}: {exc}")
                except Exception as exc:  # pylint: disable=broad-except
                    logger.exception("Facebook page %s erreur inattendue", page_id)
                    result["errors"].append(f"page_{page_id}: {exc}")

            run.accounts_processed = len(pages)
            run.metrics_collected = total_metrics
            run.status = "completed" if not result["errors"] else "partial"
            run.finished_at = datetime.now(timezone.utc)
            run.details_json = {"pages": [p["page_id"] for p in result["pages"]], "errors": result["errors"]}
            await self.db.commit()
            result["status"] = run.status

        except MetaGraphError as exc:
            logger.warning("Collecte Facebook echec: %s", exc)
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(exc)
            await self.db.commit()
            result["status"] = "failed"
            result["errors"].append(str(exc))
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Collecte Facebook erreur inattendue")
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(exc)
            await self.db.commit()
            result["status"] = "failed"
            result["errors"].append(f"erreur inattendue: {exc}")

        return result
