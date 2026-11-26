"""Régression P1-2 : annulation de la boucle de surveillance mouvement à l'arrêt du lifespan.

Le test cible uniquement la tâche ``surveillance_motion_task`` créée par
``app.main.lifespan``. Il ne vérifie pas l'absence globale de tâches pending :
d'autres tâches fire-and-forget existent hors du lifespan (notamment
``app.services.surveillance_capture.py``).
"""

import asyncio

import pytest

from app import main


@pytest.mark.asyncio
async def test_lifespan_shutdown_cancels_surveillance_motion_task(monkeypatch):
    surveillance_tasks = []

    async def fake_surveillance_loop():
        # Capture la tâche réellement créée par le lifespan (variable locale).
        surveillance_tasks.append(asyncio.current_task())
        await asyncio.sleep(3600)

    async def fake_idle_loop():
        await asyncio.sleep(3600)

    async def fake_noop(*args, **kwargs):
        return None

    class FakeDbContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    # Isole le lifespan de la base, des seeds et des autres boucles : seul le
    # comportement d'arrêt de surveillance_motion_task est sous test.
    monkeypatch.setattr(main, "init_db", fake_noop)
    monkeypatch.setattr(main, "register_dashboard_widgets", lambda: None)
    monkeypatch.setattr("app.db.session.get_db_context", lambda: FakeDbContext())
    for name in (
        "seed_default_rbac",
        "_sync_module_statuses",
        "apply_ai_settings_from_db",
        "apply_vapid_from_db",
        "seed_domotique",
    ):
        monkeypatch.setattr(main, name, fake_noop)
    monkeypatch.setattr(main, "close_db", fake_noop)
    for name in (
        "_garmin_sync_loop",
        "_ad_sync_loop",
        "_sport_analysis_loop",
        "_meta_sync_loop",
        "domotique_loop",
        "_photo_job_loop",
        "_monitoring_loop",
    ):
        monkeypatch.setattr(main, name, fake_idle_loop)
    monkeypatch.setattr(main, "_surveillance_motion_loop", fake_surveillance_loop)
    monkeypatch.setattr(main.capture_manager, "shutdown", fake_noop)

    surveillance_task = None
    try:
        async with main.lifespan(main.app):
            # Laisse les tâches créées démarrer avant de quitter le lifespan.
            await asyncio.sleep(0)
            assert len(surveillance_tasks) == 1
            surveillance_task = surveillance_tasks[0]
            assert not surveillance_task.done()

        # La tâche de surveillance doit avoir été annulée ET attendue.
        assert surveillance_task.done()
        assert surveillance_task.cancelled()
    finally:
        # Filet de sécurité si l'annulation manque (code avant correction) :
        # évite de laisser une tâche pending à la fin du test.
        for task in surveillance_tasks:
            if not task.done():
                task.cancel()
        if surveillance_tasks:
            await asyncio.gather(*surveillance_tasks, return_exceptions=True)
