"""Moteur domotique : polling Raspberry, regulation, cycles, alertes.

Boucle appelée par le lifespan (`_domotique_loop` dans app/main.py).
Le Raspberry reste une passerelle pure : toute la logique métier
(phases, transitions, régulation, alertes) vit ici, côté ForgeAI.

Reprise après redémarrage : l'état d'un cycle vit en base, la boucle
retrouve le cycle actif et reprend le suivi sans le redémarrer.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domotique import (
    DomotiqueCycle,
    DomotiqueDevice,
    DomotiqueEvent,
    DomotiqueOutput,
    DomotiquePhase,
    DomotiqueProfile,
    DomotiqueSensor,
    DomotiqueSensorReading,
    CycleStatus,
    ExitCondition,
    OutputMode,
)
from app.models.user import User
from app.services.domotique import raspberry
from app.services.domotique.raspberry import RaspberryError
from app.services.notification import NotificationService

logger = logging.getLogger(__name__)

_LOOP_INTERVAL_S = 10
_NOTIFICATION_CATEGORY = "system"
_NOTIFICATION_URL = "/domotique"


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _device_config(device: DomotiqueDevice) -> dict[str, Any]:
    config = dict(device.config_json or {})
    for key, default in (
        ("temp_min", 5.0),
        ("temp_max", 30.0),
        ("hum_min", 40.0),
        ("hum_max", 99.0),
        ("alert_cooldown_min", 30),
        ("retention_days", 90),
        ("obsolete_after_s", 90),
    ):
        config.setdefault(key, default)
    return config


async def _last_event_of_type(
    db: AsyncSession, device_id: int, event_types: list[str]
) -> DomotiqueEvent | None:
    return (
        await db.execute(
            select(DomotiqueEvent)
            .where(
                DomotiqueEvent.device_id == device_id,
                DomotiqueEvent.type.in_(event_types),
            )
            .order_by(DomotiqueEvent.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


async def _add_event(
    db: AsyncSession,
    device: DomotiqueDevice,
    event_type: str,
    message: str,
    cycle: DomotiqueCycle | None = None,
    metadata: dict[str, Any] | None = None,
) -> DomotiqueEvent:
    event = DomotiqueEvent(
        device_id=device.id,
        cycle_id=cycle.id if cycle else None,
        type=event_type,
        message=message,
        metadata_json=metadata or {},
    )
    db.add(event)
    await db.flush()
    return event


async def _users_with_domotique_view(db: AsyncSession) -> list[int]:
    # Reutilise RBACService (roles directs + groupes) pour rester coherent
    # avec le mecanisme de permissions existant.
    from app.services.rbac import RBACService

    rbac = RBACService(db)
    user_ids = (await db.execute(select(User.id).where(User.is_active.is_(True)))).scalars().all()
    allowed: list[int] = []
    for user_id in user_ids:
        user = await db.get(User, user_id)
        if user is None:
            continue
        try:
            permissions = await rbac.get_user_permissions(user)
        except Exception:  # pragma: no cover
            continue
        if "domotique.view" in permissions or "*" in permissions:
            allowed.append(user_id)
    return allowed


async def _notify_users(
    db: AsyncSession,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Notification (stockee + push) a tous les utilisateurs habilites."""
    try:
        user_ids = await _users_with_domotique_view(db)
    except Exception:  # pragma: no cover - requete RBAC best-effort
        logger.warning("[DOMOTIQUE] Impossible de lister les destinataires", exc_info=True)
        return
    payload = {"url": _NOTIFICATION_URL, **(data or {})}
    for user_id in user_ids:
        try:
            await NotificationService(db).send(
                user_id=user_id,
                title=title,
                message=message,
                category=_NOTIFICATION_CATEGORY,
                data=payload,
            )
        except Exception:  # pragma: no cover - push best-effort
            logger.warning(
                "[DOMOTIQUE] Echec notification user=%s", user_id, exc_info=True
            )


async def _maybe_notify(
    db: AsyncSession,
    device: DomotiqueDevice,
    event_types: list[str],
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Notification avec cooldown (anti-spam) fonde sur le dernier event du type."""
    config = _device_config(device)
    cooldown = timedelta(minutes=int(config["alert_cooldown_min"]))
    last = await _last_event_of_type(db, device.id, event_types)
    if last is not None:
        last_at = _as_utc(last.created_at)
        if last_at and _now() - last_at < cooldown:
            return
    await _notify_users(db, title, message, data)


# --------------------------------------------------------------------------- #
# Capteurs / sorties
# --------------------------------------------------------------------------- #

async def _persist_sensor_values(
    db: AsyncSession,
    device: DomotiqueDevice,
    state: dict[str, Any],
) -> dict[str, DomotiqueSensor]:
    sensors = {
        s.key: s
        for s in (
            await db.execute(
                select(DomotiqueSensor).where(DomotiqueSensor.device_id == device.id)
            )
        ).scalars().all()
    }
    now = _now()
    values = {
        "temperature": state.get("temperature"),
        "humidity": state.get("humidity"),
        "weight": state.get("weight"),
    }
    min_sample = max(int(device.poll_interval_s), 5)
    for key, sensor in sensors.items():
        if not sensor.enabled:
            continue
        value = values.get(key)
        if value is None:
            continue
        sensor.current_value = float(value)
        sensor.current_at = now
        last_reading = (
            await db.execute(
                select(DomotiqueSensorReading.recorded_at)
                .where(DomotiqueSensorReading.sensor_id == sensor.id)
                .order_by(DomotiqueSensorReading.recorded_at.desc())
                .limit(1)
            )
        ).scalars().first()
        last_at = _as_utc(last_reading)
        if last_at is None or (now - last_at).total_seconds() >= min_sample:
            db.add(
                DomotiqueSensorReading(sensor_id=sensor.id, value=float(value))
            )
    return sensors


async def _sync_output_states(db: AsyncSession, device: DomotiqueDevice, states: list[bool]) -> list[DomotiqueOutput]:
    outputs = (
        await db.execute(
            select(DomotiqueOutput)
            .where(DomotiqueOutput.device_id == device.id)
            .order_by(DomotiqueOutput.index)
        )
    ).scalars().all()
    for output in outputs:
        if 0 <= output.index < len(states):
            output.state = bool(states[output.index])
    return outputs


# --------------------------------------------------------------------------- #
# Regulation (envoi des consignes aux sorties automatiques)
# --------------------------------------------------------------------------- #

def _desired_states(
    phase: DomotiquePhase,
    temperature: float | None,
    humidity: float | None,
    outputs: list[DomotiqueOutput],
) -> dict[int, bool]:
    """Calcule l'etat desire (auto) pour chaque sortie en mode automatique.

    Seules les roles dotées d'une regle sont pilotees automatiquement :
    heater / cooler / humidifier / dehumidifier. Les roles fan et other
    restent en pilotage manuel (aucune regle inventee).
    """
    desired: dict[int, bool] = {}
    tol_t = phase.tolerance_temperature if phase.tolerance_temperature is not None else 1.0
    tol_h = phase.tolerance_humidity if phase.tolerance_humidity is not None else 2.0
    target_t = phase.target_temperature
    target_h = phase.target_humidity

    for output in outputs:
        if output.mode != OutputMode.AUTO or output.role == "other":
            continue
        if output.role == "heater" and target_t is not None and temperature is not None:
            if temperature < target_t - tol_t / 2:
                desired[output.index] = True
            elif temperature >= target_t:
                desired[output.index] = False
        elif output.role == "cooler" and target_t is not None and temperature is not None:
            if temperature > target_t + tol_t / 2:
                desired[output.index] = True
            elif temperature <= target_t:
                desired[output.index] = False
        elif output.role == "humidifier" and target_h is not None and humidity is not None:
            if humidity < target_h - tol_h / 2:
                desired[output.index] = True
            elif humidity >= target_h:
                desired[output.index] = False
        elif output.role == "dehumidifier" and target_h is not None and humidity is not None:
            if humidity > target_h + tol_h / 2:
                desired[output.index] = True
            elif humidity <= target_h:
                desired[output.index] = False
    return desired


async def _apply_desired_states(
    db: AsyncSession,
    device: DomotiqueDevice,
    desired: dict[int, bool],
    cycle: DomotiqueCycle | None,
) -> None:
    if not desired or not device.base_url:
        return
    outputs = {
        o.index: o
        for o in (
            await db.execute(
                select(DomotiqueOutput).where(DomotiqueOutput.device_id == device.id)
            )
        ).scalars().all()
    }
    for index, state in desired.items():
        output = outputs.get(index)
        if output is None or output.state == state:
            continue
        try:
            await raspberry.send_command(device.base_url, index, state)
        except RaspberryError as exc:
            await _add_event(
                db,
                device,
                "command_error",
                f"Échec de commande de la sortie {index + 1} : {exc}",
                cycle=cycle,
                metadata={"index": index, "state": state},
            )
            continue
        output.state = state
        await _add_event(
            db,
            device,
            "command",
            f"Sortie {index + 1} ({output.name}) → {'ON' if state else 'OFF'} (auto)",
            cycle=cycle,
            metadata={"index": index, "state": state, "mode": "auto"},
        )


async def _all_auto_outputs_off(
    db: AsyncSession, device: DomotiqueDevice, cycle: DomotiqueCycle | None
) -> None:
    outputs = (
        await db.execute(
            select(DomotiqueOutput).where(
                DomotiqueOutput.device_id == device.id,
                DomotiqueOutput.mode == OutputMode.AUTO,
            )
        )
    ).scalars().all()
    desired = {o.index: False for o in outputs if o.state}
    await _apply_desired_states(db, device, desired, cycle)


# --------------------------------------------------------------------------- #
# Cycle : transitions de phase
# --------------------------------------------------------------------------- #

def _phase_progress(cycle: DomotiqueCycle, phase: DomotiquePhase) -> dict[str, Any]:
    started = _as_utc(cycle.phase_started_at)
    elapsed_h = None
    if started:
        elapsed_h = (_now() - started).total_seconds() / 3600.0
    loss = cycle.weight_loss_pct
    return {
        "elapsed_hours": round(elapsed_h, 2) if elapsed_h is not None else None,
        "weight_loss_pct": loss,
    }


def _phase_exit_reached(cycle: DomotiqueCycle, phase: DomotiquePhase) -> bool:
    progress = _phase_progress(cycle, phase)
    if phase.exit_condition == ExitCondition.TIME:
        if phase.max_duration_hours is None:
            return False
        elapsed = progress["elapsed_hours"]
        return elapsed is not None and elapsed >= phase.max_duration_hours
    if phase.exit_condition == ExitCondition.WEIGHT:
        if phase.weight_loss_target_pct is None:
            return False
        loss = progress["weight_loss_pct"]
        return loss is not None and loss >= phase.weight_loss_target_pct
    return False  # MANUAL


async def _advance_phase(
    db: AsyncSession,
    device: DomotiqueDevice,
    cycle: DomotiqueCycle,
    profile_phases: list[DomotiquePhase],
) -> None:
    current_order = 0
    if cycle.current_phase_id:
        current = next((p for p in profile_phases if p.id == cycle.current_phase_id), None)
        if current:
            current_order = current.order
    next_phase = next((p for p in profile_phases if p.order > current_order), None)
    now = _now()

    if next_phase is None:
        # Fin de cycle : derniere phase terminee.
        cycle.status = CycleStatus.COMPLETED
        cycle.ended_at = now
        cycle.current_phase_id = None
        cycle.phase_started_at = None
        loss_text = (
            f" Perte de poids : {cycle.weight_loss_pct:.1f} %."
            if cycle.weight_loss_pct is not None
            else ""
        )
        await _add_event(
            db,
            device,
            "cycle_completed",
            f"Cycle terminé ({cycle.profile.name if cycle.profile else 'profil'}).{loss_text}",
            cycle=cycle,
        )
        await _all_auto_outputs_off(db, device, cycle)
        await _notify_users(
            db,
            "Fin de cycle — Séchoir à saucisson",
            f"Le cycle du séchoir est terminé.{loss_text}",
            data={"cycle_id": cycle.id},
        )
        return

    cycle.current_phase_id = next_phase.id
    cycle.phase_started_at = now
    await _add_event(
        db,
        device,
        "phase_change",
        f"Passage à la phase {next_phase.name}",
        cycle=cycle,
        metadata={"phase_id": next_phase.id, "order": next_phase.order},
    )
    await _notify_users(
        db,
        "Nouvelle phase — Séchoir à saucisson",
        f"Le séchoir est passé en phase {next_phase.name} "
        f"({next_phase.target_temperature} °C / {next_phase.target_humidity} % HR).",
        data={"cycle_id": cycle.id},
    )


# --------------------------------------------------------------------------- #
# Alertes de securite / capteurs / communication
# --------------------------------------------------------------------------- #

async def _check_safety(
    db: AsyncSession,
    device: DomotiqueDevice,
    cycle: DomotiqueCycle | None,
    sensors: dict[str, DomotiqueSensor],
) -> None:
    config = _device_config(device)
    checks = [
        ("alert_temperature", sensors.get("temperature"), config["temp_min"], config["temp_max"], "°C"),
        ("alert_humidity", sensors.get("humidity"), config["hum_min"], config["hum_max"], "% HR"),
    ]
    for event_type, sensor, minimum, maximum, unit in checks:
        if sensor is None or not sensor.enabled or sensor.current_value is None:
            continue
        value = sensor.current_value
        if minimum <= value <= maximum:
            continue
        bounds = f"{minimum:g} et {maximum:g}"
        message = f"{sensor.name} hors limites de sécurité : {value:g} {unit} (plage {bounds})."
        await _add_event(
            db,
            device,
            event_type,
            message,
            cycle=cycle,
            metadata={"value": value, "min": minimum, "max": maximum},
        )
        await _maybe_notify(
            db,
            device,
            [event_type],
            f"Alerte séchoir — {sensor.name}",
            message,
            data={"cycle_id": cycle.id if cycle else None},
        )


async def _check_phase_ranges(
    db: AsyncSession,
    device: DomotiqueDevice,
    cycle: DomotiqueCycle,
    phase: DomotiquePhase,
    sensors: dict[str, DomotiqueSensor],
) -> None:
    """Journalise l'entree/sortie de la plage de consigne de la phase."""
    checks = [
        ("out_of_range_temperature", sensors.get("temperature"), phase.target_temperature, phase.tolerance_temperature, "°C"),
        ("out_of_range_humidity", sensors.get("humidity"), phase.target_humidity, phase.tolerance_humidity, "% HR"),
    ]
    for event_type, sensor, target, tolerance, unit in checks:
        if sensor is None or not sensor.enabled or target is None or sensor.current_value is None:
            continue
        tol = tolerance if tolerance is not None else (1.0 if unit == "°C" else 2.0)
        value = sensor.current_value
        out = abs(value - target) > tol
        baseline_types = [event_type, event_type.replace("out_of_range", "in_range")]
        last = await _last_event_of_type(db, device.id, baseline_types)
        already_out = last is not None and last.type == event_type
        if out and not already_out:
            message = (
                f"{sensor.name} hors plage de consigne : {value:g} {unit} "
                f"(cible {target:g} ± {tol:g})."
            )
            await _add_event(
                db,
                device,
                event_type,
                message,
                cycle=cycle,
                metadata={"value": value, "target": target, "tolerance": tol},
            )
            await _maybe_notify(
                db,
                device,
                [event_type],
                f"Séchoir — {sensor.name} hors plage",
                message,
                data={"cycle_id": cycle.id},
            )
        elif not out and already_out:
            await _add_event(
                db,
                device,
                event_type.replace("out_of_range", "in_range"),
                f"{sensor.name} de retour dans la plage ({value:g} {unit}).",
                cycle=cycle,
                metadata={"value": value, "target": target},
            )


async def _check_sensor_staleness(
    db: AsyncSession,
    device: DomotiqueDevice,
    sensors: dict[str, DomotiqueSensor],
) -> None:
    config = _device_config(device)
    max_age = timedelta(seconds=int(config["obsolete_after_s"]))
    now = _now()
    for sensor in sensors.values():
        if not sensor.enabled:
            continue
        current_at = _as_utc(sensor.current_at)
        if current_at is None or (now - current_at) <= max_age:
            continue
        age_s = int((now - current_at).total_seconds())
        await _add_event(
            db,
            device,
            "sensor_stale",
            f"Le capteur {sensor.name} ne fournit plus de données depuis {age_s} s.",
            metadata={"sensor": sensor.key, "age_s": age_s},
        )
        await _maybe_notify(
            db,
            device,
            ["sensor_stale"],
            "Séchoir — capteur silencieux",
            f"Le capteur {sensor.name} ne fournit plus de données depuis {age_s} s.",
        )


async def _check_communication(
    db: AsyncSession,
    device: DomotiqueDevice,
    ok: bool,
    error: str | None,
) -> None:
    previous = device.status
    config = _device_config(device)
    stale_after = timedelta(seconds=int(config["obsolete_after_s"]))

    if ok:
        device.last_seen = _now()
        device.last_error = None
        if previous != "online":
            device.status = "online"
            await _add_event(db, device, "comm_connect", "Raspberry connecté.")
            if previous in ("offline", "error"):
                await _notify_users(
                    db,
                    "Séchoir — Raspberry reconnecté",
                    f"Le Raspberry du séchoir ({device.name}) est de nouveau joignable.",
                )
        return

    device.last_error = error or "Erreur de communication"
    last_seen = _as_utc(device.last_seen)
    if last_seen is None or (_now() - last_seen) > stale_after:
        device.status = "offline"
        if previous != "offline":
            await _add_event(
                db, device, "comm_disconnect",
                f"Raspberry hors ligne : {device.last_error}",
            )
            await _maybe_notify(
                db,
                device,
                ["comm_disconnect"],
                "Séchoir — Raspberry injoignable",
                f"Le Raspberry du séchoir ne répond plus depuis "
                f"{int((_now() - (last_seen or _now())).total_seconds())} s.",
            )
    else:
        device.status = "error"


# --------------------------------------------------------------------------- #
# Polling principal d'un device
# --------------------------------------------------------------------------- #

async def poll_device(db: AsyncSession, device: DomotiqueDevice) -> None:
    cycle = (
        await db.execute(
            select(DomotiqueCycle)
            .where(
                DomotiqueCycle.device_id == device.id,
                DomotiqueCycle.status.in_([CycleStatus.RUNNING, CycleStatus.PAUSED]),
            )
            .order_by(DomotiqueCycle.created_at.desc())
            .limit(1)
        )
    ).scalars().first()

    state: dict[str, Any] | None = None
    comm_error: str | None = None
    if not device.base_url:
        device.status = "unknown"
        device.last_error = "Adresse du Raspberry non configurée"
        await db.commit()
        return
    try:
        state = await raspberry.fetch_state(device.base_url)
    except RaspberryError as exc:
        comm_error = str(exc)

    await _check_communication(db, device, ok=state is not None, error=comm_error)

    sensors: dict[str, DomotiqueSensor] = {}
    if state is not None:
        sensors = await _persist_sensor_values(db, device, state)
        await _sync_output_states(db, device, state["outputs"])

    # Cycle : poids + phases + regulation (uniquement en cours de cycle actif)
    if cycle is not None and cycle.status == CycleStatus.RUNNING and state is not None:
        if state.get("weight") is not None and cycle.initial_weight:
            cycle.current_weight = state["weight"]

        profile = await db.get(DomotiqueProfile, cycle.profile_id)
        phases = sorted(profile.phases, key=lambda p: p.order) if profile else []
        current_phase = next((p for p in phases if p.id == cycle.current_phase_id), None)

        if current_phase is not None:
            if cycle.phase_started_at is None:
                cycle.phase_started_at = _now()
            await _check_phase_ranges(db, device, cycle, current_phase, sensors)
            if _phase_exit_reached(cycle, current_phase):
                await _advance_phase(db, device, cycle, phases)
                current_phase = next(
                    (p for p in phases if p.id == cycle.current_phase_id), None
                )
            if (
                current_phase is not None
                and cycle.status == CycleStatus.RUNNING
                and not cycle.manual_outputs
            ):
                desired = _desired_states(
                    current_phase,
                    state.get("temperature"),
                    state.get("humidity"),
                    [
                        o
                        for o in (
                            await db.execute(
                                select(DomotiqueOutput).where(
                                    DomotiqueOutput.device_id == device.id
                                )
                            )
                        ).scalars().all()
                    ],
                )
                await _apply_desired_states(db, device, desired, cycle)

    if state is not None:
        await _check_safety(db, device, cycle, sensors)
        await _check_sensor_staleness(db, device, sensors)

    # Rétention : purge des mesures hors fenetre.
    config = _device_config(device)
    cutoff = _now() - timedelta(days=int(config["retention_days"]))
    await db.execute(
        delete(DomotiqueSensorReading).where(DomotiqueSensorReading.recorded_at < cutoff)
    )

    await db.commit()


async def run_poll_cycle(db: AsyncSession) -> None:
    devices = (await db.execute(select(DomotiqueDevice))).scalars().all()
    for device in devices:
        try:
            await poll_device(db, device)
        except Exception:  # pragma: no cover - un device en echec n'arrete pas la boucle
            logger.warning(
                "[DOMOTIQUE] Polling en echec device=%s", device.code, exc_info=True
            )
            await db.rollback()


async def domotique_loop() -> None:
    """Boucle de fond (lifespan) : polling + moteur domotique."""
    from app.db.session import get_db

    while True:
        try:
            async for db in get_db():
                await run_poll_cycle(db)
                break
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover
            logger.warning("[DOMOTIQUE] Boucle en echec: %s", exc)
        await asyncio.sleep(_LOOP_INTERVAL_S)
