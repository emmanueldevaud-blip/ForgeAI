"""Gestion des cycles du sechoir : creation, demarrage, pause, arret, avance."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domotique import (
    DomotiqueCycle,
    DomotiqueDevice,
    DomotiqueEvent,
    DomotiqueOutput,
    DomotiquePhase,
    DomotiqueProfile,
    DomotiqueSensor,
    CycleStatus,
    OutputMode,
)
from app.schemas.domotique import DomotiqueCycleCreate
from app.services.domotique import engine, raspberry
from app.services.domotique.raspberry import RaspberryError

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = (CycleStatus.RUNNING, CycleStatus.PAUSED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_active_cycle(db: AsyncSession, device_id: int) -> DomotiqueCycle | None:
    return (
        await db.execute(
            select(DomotiqueCycle)
            .where(
                DomotiqueCycle.device_id == device_id,
                DomotiqueCycle.status.in_(_ACTIVE_STATUSES),
            )
            .order_by(DomotiqueCycle.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


async def get_last_cycle(db: AsyncSession, device_id: int) -> DomotiqueCycle | None:
    return (
        await db.execute(
            select(DomotiqueCycle)
            .where(DomotiqueCycle.device_id == device_id)
            .order_by(DomotiqueCycle.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


async def create_cycle(
    db: AsyncSession, device: DomotiqueDevice, payload: DomotiqueCycleCreate
) -> DomotiqueCycle:
    if await get_active_cycle(db, device.id):
        raise ValueError("Un cycle est déjà en cours sur ce dispositif.")
    profile = await db.get(DomotiqueProfile, payload.profile_id)
    if not profile:
        raise ValueError("Profil de cycle introuvable.")
    if not profile.phases:
        raise ValueError("Le profil sélectionné ne contient aucune phase.")

    first_phase = sorted(profile.phases, key=lambda p: p.order)[0]
    started_at = None
    if payload.started_at is not None:
        started_at = (
            payload.started_at
            if payload.started_at.tzinfo
            else payload.started_at.replace(tzinfo=timezone.utc)
        )
    initial_weight = payload.initial_weight
    if initial_weight is None:
        weight_sensor = (
            await db.execute(
                select(DomotiqueSensor).where(
                    DomotiqueSensor.device_id == device.id,
                    DomotiqueSensor.key == "weight",
                )
            )
        ).scalars().first()
        if weight_sensor and weight_sensor.enabled and weight_sensor.current_value:
            initial_weight = weight_sensor.current_value

    cycle = DomotiqueCycle(
        device_id=device.id,
        profile_id=profile.id,
        name=payload.name or f"{profile.name} — {payload.product or 'produit'}",
        product=payload.product,
        casing_size=payload.casing_size,
        status=CycleStatus.PREPARING,
        current_phase_id=first_phase.id,
        started_at=started_at,
        phase_started_at=started_at,
        initial_weight=initial_weight,
        target_weight_loss_pct=(
            payload.target_weight_loss_pct
            if payload.target_weight_loss_pct is not None
            else profile.target_weight_loss_pct
        ),
    )
    db.add(cycle)
    await db.flush()
    await engine._add_event(
        db,
        device,
        "cycle_created",
        f"Cycle créé (profil {profile.name}"
        + (f", poids initial {initial_weight:g} g" if initial_weight else "")
        + ").",
        cycle=cycle,
        metadata={"profile_code": profile.code},
    )
    if payload.start_now:
        await start_cycle(db, device, cycle)
    await db.commit()
    await db.refresh(cycle)
    return cycle


async def start_cycle(
    db: AsyncSession, device: DomotiqueDevice, cycle: DomotiqueCycle
) -> None:
    if cycle.status == CycleStatus.RUNNING:
        raise ValueError("Le cycle est déjà en cours.")
    now = _now()
    resumed = cycle.status == CycleStatus.PAUSED
    if resumed and cycle.paused_at is not None:
        # Le temps de pause n'est pas impute a la phase en cours.
        paused_at = cycle.paused_at
        if paused_at.tzinfo is None:
            paused_at = paused_at.replace(tzinfo=timezone.utc)
        paused_seconds = (now - paused_at).total_seconds()
        if cycle.phase_started_at is not None:
            from datetime import timedelta

            cycle.phase_started_at = cycle.phase_started_at + timedelta(
                seconds=paused_seconds
            )
        cycle.paused_at = None
    cycle.status = CycleStatus.RUNNING
    if cycle.started_at is None:
        cycle.started_at = now
    if cycle.phase_started_at is None:
        cycle.phase_started_at = now

    if not cycle.current_phase_id:
        profile = await db.get(DomotiqueProfile, cycle.profile_id)
        first_phase = sorted(profile.phases, key=lambda p: p.order)[0]
        cycle.current_phase_id = first_phase.id
        cycle.phase_started_at = now

    if resumed:
        await engine._add_event(db, device, "cycle_resumed", "Reprise du cycle.", cycle=cycle)
        await engine._notify_users(
            db,
            "La Cave — cycle repris",
            f"Le cycle de la cave a repris (phase {await _phase_name(db, cycle)}).",
            data={"cycle_id": cycle.id},
        )
    else:
        await engine._add_event(
            db, device, "cycle_started", "Cycle démarré.", cycle=cycle
        )
        await engine._notify_users(
            db,
            "La Cave — cycle démarré",
            f"Un cycle de séchage a démarré (phase {await _phase_name(db, cycle)}).",
            data={"cycle_id": cycle.id},
        )


async def _phase_name(db: AsyncSession, cycle: DomotiqueCycle) -> str:
    phase = await db.get(DomotiquePhase, cycle.current_phase_id) if cycle.current_phase_id else None
    return phase.name if phase else "—"


async def pause_cycle(
    db: AsyncSession, device: DomotiqueDevice, cycle: DomotiqueCycle
) -> None:
    if cycle.status != CycleStatus.RUNNING:
        raise ValueError("Seul un cycle en cours peut être mis en pause.")
    cycle.status = CycleStatus.PAUSED
    cycle.paused_at = _now()
    await engine._add_event(db, device, "cycle_paused", "Cycle mis en pause.", cycle=cycle)


async def stop_cycle(
    db: AsyncSession, device: DomotiqueDevice, cycle: DomotiqueCycle
) -> None:
    if cycle.status not in _ACTIVE_STATUSES:
        raise ValueError("Aucun cycle actif à arrêter.")
    cycle.status = CycleStatus.STOPPED
    cycle.ended_at = _now()
    cycle.paused_at = None
    await engine._add_event(db, device, "cycle_stopped", "Cycle arrêté.", cycle=cycle)
    await engine._all_auto_outputs_off(db, device, cycle)
    await engine._notify_users(
        db,
        "La Cave — cycle arrêté",
        "Le cycle de la cave a été arrêté."
        + (
            f" Perte de poids : {cycle.weight_loss_pct:.1f} %."
            if cycle.weight_loss_pct is not None
            else ""
        ),
        data={"cycle_id": cycle.id},
    )


async def advance_phase(
    db: AsyncSession, device: DomotiqueDevice, cycle: DomotiqueCycle
) -> None:
    if cycle.status != CycleStatus.RUNNING:
        raise ValueError("Seul un cycle en cours peut changer de phase.")
    profile = await db.get(DomotiqueProfile, cycle.profile_id)
    phases = sorted(profile.phases, key=lambda p: p.order)
    await engine._advance_phase(db, device, cycle, phases)


async def set_output_mode(
    db: AsyncSession, device: DomotiqueDevice, index: int, mode: str
) -> DomotiqueOutput:
    output = (
        await db.execute(
            select(DomotiqueOutput).where(
                DomotiqueOutput.device_id == device.id, DomotiqueOutput.index == index
            )
        )
    ).scalars().first()
    if not output:
        raise ValueError("Sortie introuvable.")
    if mode not in (OutputMode.AUTO, OutputMode.MANUAL):
        raise ValueError("Mode invalide (auto | manual).")
    if output.mode == mode:
        return output
    output.mode = mode
    cycle = await get_active_cycle(db, device.id)
    await engine._add_event(
        db,
        device,
        "output_mode",
        f"Sortie {index + 1} ({output.name}) → mode {mode}.",
        cycle=cycle,
        metadata={"index": index, "mode": mode},
    )
    return output


async def manual_command(
    db: AsyncSession, device: DomotiqueDevice, index: int, state: bool
) -> DomotiqueOutput:
    output = (
        await db.execute(
            select(DomotiqueOutput).where(
                DomotiqueOutput.device_id == device.id, DomotiqueOutput.index == index
            )
        )
    ).scalars().first()
    if not output:
        raise ValueError("Sortie introuvable.")
    if output.mode != OutputMode.MANUAL:
        raise ValueError(
            "Sortie en mode automatique : basculez-la en manuel avant de la commander."
        )
    if not device.base_url:
        raise ValueError("Adresse du Raspberry non configurée.")
    await raspberry.send_command(
        device.base_url,
        index,
        state,
        auth=raspberry.credentials_from_config(device.config_json),
    )
    output.state = state
    cycle = await get_active_cycle(db, device.id)
    await engine._add_event(
        db,
        device,
        "manual_command",
        f"Commande manuelle : sortie {index + 1} ({output.name}) → "
        f"{'ON' if state else 'OFF'}.",
        cycle=cycle,
        metadata={"index": index, "state": state, "mode": "manual"},
    )
    return output
