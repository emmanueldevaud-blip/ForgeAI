"""Événements métier qui réveillent l'Agent Sport.

Un événement (nouvel objectif, synchronisation Garmin réussie, changement de
récupération, séance réalisée ou échouée, donnée anormale) se traduit en un
réveil de l'agent via l'architecture de triggers **existante** : la même
fonction ``run_agent_trigger``, le même drapeau ``SPORT_AGENT_ENABLED`` et le
même cooldown par athlète/déclencheur. Aucun second système d'agent n'est
créé.

Idempotence :
* cooldown ``AGENT_TRIGGER_COOLDOWN_MINUTES`` appliqué dans ``run_agent_trigger``
  pour tout déclencheur de ``EVENT_TRIGGERS`` ;
* marquage dans ``result_json`` des recommandations concernées
  (``training_completed_emitted_at`` / ``missed_emitted_at``) pour n'émettre
  qu'une fois un événement qui porte sur une recommandation donnée ;
* les événements santé ne sont émis que si la donnée la plus récente date
  d'aujourd'hui ou d'hier (une donnée ancienne ne réveille jamais l'agent).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sport import SportActivity, SportAthlete, SportRecommendation
from app.models.user import User
from app.services.sport_agent.triggers import agent_enabled, run_agent_trigger

logger = logging.getLogger(__name__)

# Nombre maximal de réveils consécutifs générés par une même synchronisation.
MAX_EVENTS_PER_SYNC = 3
# Seuils de détection « changement de récupération » (règles simples).
RECOVERY_READINESS_DELTA = 15
RECOVERY_SLEEP_DELTA_MINUTES = 90
ACTIVITY_EVENT_MAX_AGE_DAYS = 7
HEALTH_FRESH_DAYS = 2


def _aware(value: datetime | None) -> datetime | None:
    """Les colonnes SQLite/MySQL sont stockées sans fuseau : on force UTC."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Réveils
# --------------------------------------------------------------------------- #


async def emit_agent_event(
    db: AsyncSession,
    user: User,
    athlete_id: int,
    trigger: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Réveil immédiat sur la session fournie (cycle planifié, endpoints)."""
    return await run_agent_trigger(db, user, trigger, payload=payload)


async def _event_worker(
    user_id: int,
    athlete_id: int,
    trigger: str,
    payload: dict[str, Any] | None,
) -> None:
    from app.db.session import get_db_context

    try:
        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if user is None or not user.is_active:
                logger.info("[SPORT-AGENT] event=skipped trigger=%s reason=user_inactif", trigger)
                return
            outcome = await run_agent_trigger(db, user, trigger, payload=payload)
            logger.info(
                "[SPORT-AGENT] event=emitted trigger=%s status=%s execution=%s",
                trigger,
                outcome.get("status"),
                outcome.get("execution_id"),
            )
    except Exception:
        logger.exception("[SPORT-AGENT] event=emit_failed trigger=%s", trigger)


async def schedule_agent_event(
    user_id: int,
    athlete_id: int,
    trigger: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Réveil différé avec session propre : à passer à ``BackgroundTasks``.

    Coroutine (et non fonction synchrone) : Starlette exécute les tâches de
    fond synchrones dans un threadpool, où aucun event loop n'est courant.
    """
    if not agent_enabled():
        return
    await _event_worker(user_id, athlete_id, trigger, payload)


async def schedule_post_sync_events(user_id: int, athlete_id: int, imported_count: int) -> None:
    """Après une synchronisation Garmin : évalue puis émet les événements."""
    if not agent_enabled():
        return
    await _post_sync_worker(user_id, athlete_id, imported_count)


def fire_post_sync_events(user_id: int, athlete_id: int, imported_count: int) -> None:
    """Version « fire-and-forget » pour un appelant déjà dans l'event loop
    (scheduler de synchronisation Garmin)."""
    if not agent_enabled():
        return
    _spawn(_post_sync_worker(user_id, athlete_id, imported_count))


def _spawn(coro: Awaitable[Any]) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


_BACKGROUND_TASKS: set[asyncio.Task] = set()


async def _post_sync_worker(user_id: int, athlete_id: int, imported_count: int) -> None:
    from app.db.session import get_db_context

    try:
        async with get_db_context() as db:
            user = await db.get(User, user_id)
            athlete = await db.get(SportAthlete, athlete_id)
            if user is None or athlete is None or not user.is_active:
                return
            events = await collect_post_sync_events(db, user, athlete, imported_count)
            for trigger, payload in events[:MAX_EVENTS_PER_SYNC]:
                outcome = await run_agent_trigger(db, user, trigger, payload=payload)
                logger.info(
                    "[SPORT-AGENT] event=post_sync trigger=%s status=%s imported=%d",
                    trigger,
                    outcome.get("status"),
                    imported_count,
                )
            if events:
                await db.commit()
    except Exception:
        logger.exception("[SPORT-AGENT] event=post_sync_failed athlete=%s", athlete_id)


# --------------------------------------------------------------------------- #
# Évaluation (règles déterministes, sans nouvelle infrastructure)
# --------------------------------------------------------------------------- #


async def collect_post_sync_events(
    db: AsyncSession,
    user: User,
    athlete: SportAthlete,
    imported_count: int,
) -> list[tuple[str, dict[str, Any]]]:
    """Événements à émettre à l'issue d'une synchronisation Garmin."""
    events: list[tuple[str, dict[str, Any]]] = []
    if imported_count > 0:
        events.append(("garmin_sync", {"imported_count": imported_count}))

    health_events = await _health_events(db, user)
    events.extend(health_events)

    training_event = await _training_completed_event(db, athlete)
    if training_event is not None:
        events.append(training_event)
    return events


async def _health_events(db: AsyncSession, user: User) -> list[tuple[str, dict[str, Any]]]:
    """Changement de récupération ou valeur anormale sur les données fraîches."""
    from app.services.sport import SportService

    try:
        health = await SportService(db, user).health(7)
        series = health.get("series") or {}
    except Exception:
        logger.warning("[SPORT-AGENT] event=health_eval_failed", exc_info=True)
        return []

    today = datetime.now(timezone.utc).date()
    readiness = [
        item
        for item in (series.get("readiness") or [])
        if isinstance(item, dict) and item.get("score") is not None
    ]
    sleep = [
        item
        for item in (series.get("sleep") or [])
        if isinstance(item, dict) and item.get("total_minutes") is not None
    ]
    if not readiness and not sleep:
        return []

    def _fresh(items: list[dict[str, Any]]) -> bool:
        try:
            latest_day = datetime.fromisoformat(str(items[-1].get("date"))).date()
        except (TypeError, ValueError):
            return False
        return (today - latest_day) < timedelta(days=HEALTH_FRESH_DAYS)

    events: list[tuple[str, dict[str, Any]]] = []

    if len(readiness) >= 2 and _fresh(readiness):
        previous, current = readiness[-2]["score"], readiness[-1]["score"]
        delta = current - previous
        if abs(delta) >= RECOVERY_READINESS_DELTA:
            events.append((
                "recovery_change",
                {
                    "metric": "readiness_score",
                    "previous": previous,
                    "current": current,
                    "delta": delta,
                    "day": readiness[-1].get("date"),
                },
            ))

    if not events and len(sleep) >= 2 and _fresh(sleep):
        previous, current = sleep[-2]["total_minutes"], sleep[-1]["total_minutes"]
        delta = current - previous
        if abs(delta) >= RECOVERY_SLEEP_DELTA_MINUTES:
            events.append((
                "recovery_change",
                {
                    "metric": "sleep_minutes",
                    "previous": previous,
                    "current": current,
                    "delta": delta,
                    "day": sleep[-1].get("date"),
                },
            ))

    if _fresh(readiness or sleep):
        reasons: list[str] = []
        if sleep and sleep[-1]["total_minutes"] == 0:
            reasons.append("sommeil_nul")
        if readiness and readiness[-1]["score"] < 20:
            reasons.append("readiness_critique")
        if reasons:
            events.append((
                "anomaly_detected",
                {
                    "reasons": reasons,
                    "readiness_score": readiness[-1]["score"] if readiness else None,
                    "sleep_minutes": sleep[-1]["total_minutes"] if sleep else None,
                    "day": (readiness or sleep)[-1].get("date"),
                },
            ))
    return events


async def _training_completed_event(
    db: AsyncSession,
    athlete: SportAthlete,
) -> tuple[str, dict[str, Any]] | None:
    """Une séance récente couvre une recommandation d'entraînement active."""
    now = datetime.now(timezone.utc)
    activity = (
        await db.execute(
            select(SportActivity)
            .where(
                SportActivity.athlete_id == athlete.id,
                SportActivity.started_at >= now - timedelta(days=ACTIVITY_EVENT_MAX_AGE_DAYS),
            )
            .order_by(SportActivity.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if activity is None:
        return None

    started = _aware(activity.started_at)

    rows = (
        await db.execute(
            select(SportRecommendation).where(
                SportRecommendation.athlete_id == athlete.id,
                SportRecommendation.category == "training",
                SportRecommendation.status.in_(("pending", "accepted")),
            )
        )
    ).scalars().all()
    for reco in rows:
        valid_from, valid_until = _aware(reco.valid_from), _aware(reco.valid_until)
        if valid_from is not None and valid_from > started:
            continue
        if valid_until is not None and valid_until < started:
            continue
        result = dict(reco.result_json or {})
        if result.get("training_completed_emitted_at"):
            continue
        result["training_completed_emitted_at"] = now.isoformat()
        reco.result_json = result
        return (
            "training_completed",
            {
                "activity_id": activity.id,
                "recommendation_id": reco.id,
                "activity_started_at": started.isoformat(),
            },
        )
    return None


async def collect_missed_training_events(
    db: AsyncSession,
    athlete_id: int,
    now: datetime | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Recommandations d'entraînement échues encore actives → ``training_missed``.

    Chaque recommandation n'est signalée qu'une fois (marquage dans
    ``result_json``), quel que soit le nombre de passages du cycle.
    """
    now = now or datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(SportRecommendation).where(
                SportRecommendation.athlete_id == athlete_id,
                SportRecommendation.category == "training",
                SportRecommendation.status.in_(("pending", "accepted")),
            )
        )
    ).scalars().all()

    events: list[tuple[str, dict[str, Any]]] = []
    for reco in rows:
        valid_until = _aware(reco.valid_until)
        if valid_until is None or valid_until >= now:
            continue
        result = dict(reco.result_json or {})
        if result.get("missed_emitted_at"):
            continue
        result["missed_emitted_at"] = now.isoformat()
        reco.result_json = result
        events.append((
            "training_missed",
            {
                "recommendation_id": reco.id,
                "valid_until": reco.valid_until.isoformat(),
                "status": reco.status,
            },
        ))
    return events
