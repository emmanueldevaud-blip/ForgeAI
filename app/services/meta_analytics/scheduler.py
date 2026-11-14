"""Planificateur de synchronisation automatique Meta Analytics.

S'intègre a la boucle de vie de l'application (main.py) de maniere similaire
a la synchro Garmin. L'echec de la synchro Meta ne doit jamais tuer
l'application.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.db.session import get_db
from app.services.meta_analytics.collector_service import MetaCollectorService

logger = logging.getLogger(__name__)

META_SYNC_INTERVAL_SECONDS = 4 * 60 * 60  # 4 heures par defaut


async def meta_sync_loop() -> None:
    """Boucle de synchronisation automatique periodique (toutes les 4h)."""
    while True:
        try:
            async for db in get_db():
                await MetaCollectorService(db).sync_all()
                break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Une synchro en echec ne doit jamais tuer l'application.
            logger.warning("[META-SYNC] Cycle en echec: %s", exc)
        await asyncio.sleep(META_SYNC_INTERVAL_SECONDS)


async def run_meta_sync_once() -> dict:
    """Execute une synchronisation ponctuelle (utilisee par l'API /sync)."""
    async for db in get_db():
        return await MetaCollectorService(db).sync_all()
