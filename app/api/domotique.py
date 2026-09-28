"""API du module Domotique (sechoir a saucisson)."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
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
    OutputMode,
)
from app.schemas.domotique import (
    DomotiqueConfigResponse,
    DomotiqueConfigTestRequest,
    DomotiqueConfigUpdate,
    DomotiqueCurrentCycleResponse,
    DomotiqueCycleCreate,
    DomotiqueCycleListResponse,
    DomotiqueCycleResponse,
    DomotiqueDeviceStatusResponse,
    DomotiqueEventListResponse,
    DomotiqueEventResponse,
    DomotiqueHistoryPoint,
    DomotiqueHistoryResponse,
    DomotiqueOutputSeriesResponse,
    DomotiqueManualRequest,
    DomotiqueManualResponse,
    DomotiqueOutputResponse,
    DomotiqueProfileListResponse,
    DomotiqueProfileResponse,
    DomotiqueProfileUpsert,
    DomotiqueSensorResponse,
    DomotiqueTestConnectionResponse,
)
from app.services.domotique import cycles as cycles_service
from app.services.domotique import raspberry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domotique", tags=["domotique"])

_DEFAULT_DEVICE_CODE = "sechoir-saucisson"

_PERIODS = {
    "24h": timedelta(days=1),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
}


async def _get_device(db: AsyncSession, code: str) -> DomotiqueDevice:
    device = (
        await db.execute(select(DomotiqueDevice).where(DomotiqueDevice.code == code))
    ).scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositif domotique introuvable")
    return device


def _cycle_payload(cycle: DomotiqueCycle | None, profile: DomotiqueProfile | None = None) -> DomotiqueCurrentCycleResponse | None:
    if cycle is None:
        return None
    phase_name = None
    phase_order = None
    if profile and cycle.current_phase_id:
        phase = next((p for p in profile.phases if p.id == cycle.current_phase_id), None)
        if phase:
            phase_name = phase.name
            phase_order = phase.order
    return DomotiqueCurrentCycleResponse(
        id=cycle.id,
        profile_id=cycle.profile_id,
        profile_name=profile.name if profile else None,
        name=cycle.name,
        product=cycle.product,
        casing_size=cycle.casing_size,
        status=cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status),
        current_phase_id=cycle.current_phase_id,
        current_phase_name=phase_name,
        current_phase_order=phase_order,
        phase_started_at=cycle.phase_started_at,
        started_at=cycle.started_at,
        ended_at=cycle.ended_at,
        initial_weight=cycle.initial_weight,
        current_weight=cycle.current_weight,
        target_weight_loss_pct=cycle.target_weight_loss_pct,
        weight_loss_pct=cycle.weight_loss_pct,
        manual_outputs=cycle.manual_outputs,
        phases_total=len(profile.phases) if profile else 0,
    )


async def _active_cycle(db: AsyncSession, device: DomotiqueDevice) -> DomotiqueCycle | None:
    return await cycles_service.get_active_cycle(db, device.id)


# --------------------------------------------------------------------------- #
# Etat / historique
# --------------------------------------------------------------------------- #

@router.get("/status", response_model=DomotiqueDeviceStatusResponse)
async def get_status(
    code: str = Query(default=_DEFAULT_DEVICE_CODE),
    current_user=Depends(require_permission("domotique.view")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, code)
    sensors = (
        await db.execute(
            select(DomotiqueSensor)
            .where(DomotiqueSensor.device_id == device.id)
            .order_by(DomotiqueSensor.id)
        )
    ).scalars().all()
    outputs = (
        await db.execute(
            select(DomotiqueOutput)
            .where(DomotiqueOutput.device_id == device.id)
            .order_by(DomotiqueOutput.index)
        )
    ).scalars().all()
    cycle = await _active_cycle(db, device)
    profile = None
    if cycle:
        profile = await db.get(DomotiqueProfile, cycle.profile_id)

    from app.services.domotique.engine import (  # volontairement local
        _as_utc,
        _corrected_humidity,
        _now,
    )

    stale = False
    last_seen = _as_utc(device.last_seen)
    if last_seen is None:
        stale = True
    else:
        stale = (_now() - last_seen).total_seconds() > max(
            int(device.poll_interval_s) * 3, 90
        )

    sensor_payloads = []
    phase = None
    if cycle and profile:
        phase = next(
            (p for p in profile.phases if p.id == cycle.current_phase_id), None
        )
    corrected_humidity = None
    if phase is not None and phase.target_temperature is not None:
        temp_value = next(
            (s.current_value for s in sensors if s.key == "temperature"), None
        )
        hum_value = next(
            (s.current_value for s in sensors if s.key == "humidity"), None
        )
        corrected_humidity = _corrected_humidity(
            temp_value, hum_value, phase.target_temperature
        )
    for sensor in sensors:
        payload = DomotiqueSensorResponse.model_validate(sensor)
        if sensor.key == "humidity":
            payload.corrected_value = corrected_humidity
        sensor_payloads.append(payload)

    return DomotiqueDeviceStatusResponse(
        code=device.code,
        name=device.name,
        kind=device.kind,
        status=device.status.value if hasattr(device.status, "value") else str(device.status),
        last_seen=device.last_seen,
        last_error=device.last_error,
        base_url=device.base_url,
        poll_interval_s=device.poll_interval_s,
        stale=stale,
        sensors=sensor_payloads,
        outputs=[DomotiqueOutputResponse.model_validate(o) for o in outputs],
        cycle=_cycle_payload(cycle, profile),
        config=device.config_json or {},
    )


@router.get("/history", response_model=DomotiqueHistoryResponse)
async def get_history(
    period: str = Query(default="24h"),
    code: str = Query(default=_DEFAULT_DEVICE_CODE),
    current_user=Depends(require_permission("domotique.view")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, code)
    now = datetime.now(timezone.utc)

    target_temperature = None
    target_humidity = None
    if period == "cycle":
        cycle = await _active_cycle(db, device)
        if cycle and cycle.started_at:
            start = cycle.started_at
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        else:
            start = now - timedelta(days=7)
        if cycle:
            profile = await db.get(DomotiqueProfile, cycle.profile_id)
            phase = next(
                (p for p in profile.phases if p.id == cycle.current_phase_id), None
            ) if profile else None
            if phase:
                target_temperature = phase.target_temperature
                target_humidity = phase.target_humidity
    elif period in _PERIODS:
        start = now - _PERIODS[period]
    else:
        raise HTTPException(status_code=422, detail="Période invalide (24h, 3d, 7d, cycle)")

    sensors = (
        await db.execute(
            select(DomotiqueSensor).where(DomotiqueSensor.device_id == device.id)
        )
    ).scalars().all()
    active_cycle = await _active_cycle(db, device)
    if active_cycle and period != "cycle":
        profile = await db.get(DomotiqueProfile, active_cycle.profile_id)
        phase = next(
            (p for p in profile.phases if p.id == active_cycle.current_phase_id), None
        ) if profile else None
        if phase:
            target_temperature = target_temperature or phase.target_temperature
            target_humidity = target_humidity or phase.target_humidity

    # Serie de temperature utilisee pour corriger l'humidite de la
    # temperature du capteur (les releves T/HR partagent recorded_at).
    from app.services.domotique.engine import _corrected_humidity  # volontairement local

    humidity_temp_by_at: dict[datetime, float] = {}
    if target_temperature is not None:
        temp_sensor = next(
            (s for s in sensors if s.key == "temperature" and s.enabled), None
        )
        if temp_sensor is not None:
            temp_rows = (
                await db.execute(
                    select(
                        DomotiqueSensorReading.recorded_at,
                        DomotiqueSensorReading.value,
                    ).where(
                        DomotiqueSensorReading.sensor_id == temp_sensor.id,
                        DomotiqueSensorReading.recorded_at >= start,
                    )
                )
            ).all()
            humidity_temp_by_at = {row[0]: row[1] for row in temp_rows}

    series: dict[str, list[DomotiqueHistoryPoint]] = {}
    stats: dict[str, dict[str, float]] = {}
    for sensor in sensors:
        if not sensor.enabled:
            continue
        rows = (
            await db.execute(
                select(DomotiqueSensorReading.value, DomotiqueSensorReading.recorded_at)
                .where(
                    DomotiqueSensorReading.sensor_id == sensor.id,
                    DomotiqueSensorReading.recorded_at >= start,
                )
                .order_by(DomotiqueSensorReading.recorded_at)
            )
        ).all()
        if not rows:
            continue
        points = [DomotiqueHistoryPoint(t=row[1], v=row[0]) for row in rows]
        if sensor.key == "humidity" and humidity_temp_by_at:
            for point in points:
                temp_value = humidity_temp_by_at.get(point.t)
                if temp_value is None:
                    continue
                corrected = _corrected_humidity(temp_value, point.v, target_temperature)
                if corrected is not None:
                    point.v = round(corrected, 2)
        values = [p.v for p in points]
        trend = None
        if len(values) >= 2:
            half = max(1, len(values) // 4)
            first = sum(values[:half]) / len(values[:half])
            last = sum(values[-half:]) / len(values[-half:])
            trend = round(last - first, 3)
        series[sensor.key] = points
        stats[sensor.key] = {"min": min(values), "max": max(values), "trend": trend}

    # Etats de sortie : reconstruits depuis les events de commande
    # (automatique et manuelle), avec l'etat a l'entree de la periode et
    # prolongation jusqu'a l'etat courant.
    from app.services.domotique.engine import _as_utc  # volontairement local

    start_aware = (
        start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
    )
    output_rows = (
        await db.execute(
            select(DomotiqueOutput)
            .where(DomotiqueOutput.device_id == device.id)
            .order_by(DomotiqueOutput.index)
        )
    ).scalars().all()
    command_events = (
        await db.execute(
            select(DomotiqueEvent)
            .where(
                DomotiqueEvent.device_id == device.id,
                DomotiqueEvent.type.in_(["command", "manual_command"]),
                DomotiqueEvent.created_at < now,
            )
            .order_by(DomotiqueEvent.created_at)
        )
    ).scalars().all()

    output_series: list[DomotiqueOutputSeriesResponse] = []
    for output in output_rows:
        points: list[DomotiqueHistoryPoint] = []
        initial_value: float | None = None
        last_value: float | None = None
        for event in command_events:
            meta = event.metadata_json or {}
            if meta.get("index") != output.index or "state" not in meta:
                continue
            event_at = _as_utc(event.created_at)
            if event_at is None:
                continue
            value = 1.0 if meta["state"] else 0.0
            if event_at < start_aware:
                initial_value = value
                last_value = value
                continue
            points.append(DomotiqueHistoryPoint(t=event_at, v=value))
            last_value = value
        if initial_value is not None:
            points.insert(0, DomotiqueHistoryPoint(t=start_aware, v=initial_value))
        if output.state is not None:
            current_value = 1.0 if output.state else 0.0
            if last_value is None:
                if initial_value is None:
                    continue
            elif last_value != current_value:
                points.append(DomotiqueHistoryPoint(t=now, v=current_value))
        if not points:
            continue
        output_series.append(
            DomotiqueOutputSeriesResponse(
                index=output.index,
                name=output.name,
                role=output.role,
                points=points,
            )
        )

    return DomotiqueHistoryResponse(
        period=period,
        start=start,
        end=now,
        min_sample_s=int(device.poll_interval_s),
        series=series,
        outputs=output_series,
        target_temperature=target_temperature,
        target_humidity=target_humidity,
        min={k: v["min"] for k, v in stats.items()},
        max={k: v["max"] for k, v in stats.items()},
        trend={k: v["trend"] for k, v in stats.items()},
    )


@router.get("/events", response_model=DomotiqueEventListResponse)
async def list_events(
    limit: int = Query(default=50, ge=1, le=200),
    code: str = Query(default=_DEFAULT_DEVICE_CODE),
    current_user=Depends(require_permission("domotique.view")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, code)
    rows = (
        await db.execute(
            select(DomotiqueEvent)
            .where(DomotiqueEvent.device_id == device.id)
            .order_by(desc(DomotiqueEvent.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return DomotiqueEventListResponse(
        events=[
            DomotiqueEventResponse(
                id=e.id,
                device_id=e.device_id,
                cycle_id=e.cycle_id,
                type=e.type,
                message=e.message,
                metadata=e.metadata_json or {},
                created_at=e.created_at,
            )
            for e in rows
        ],
        total=len(rows),
    )


# --------------------------------------------------------------------------- #
# Cycles
# --------------------------------------------------------------------------- #

def _cycle_full_payload(cycle: DomotiqueCycle, profile: DomotiqueProfile | None) -> DomotiqueCycleResponse:
    base = _cycle_payload(cycle, profile)
    labels = {
        "preparing": "Préparation",
        "running": "En cours",
        "paused": "Pause",
        "completed": "Terminé",
        "stopped": "Arrêté",
        "error": "Erreur",
    }
    status = cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status)
    return DomotiqueCycleResponse(
        **base.model_dump(),
        profile_code=profile.code if profile else None,
        status_label=labels.get(status, status),
        created_at=cycle.created_at,
    )


@router.get("/cycle", response_model=DomotiqueCycleResponse | None)
async def get_cycle(
    code: str = Query(default=_DEFAULT_DEVICE_CODE),
    current_user=Depends(require_permission("domotique.view")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, code)
    cycle = await cycles_service.get_active_cycle(db, device.id)
    if not cycle:
        cycle = await cycles_service.get_last_cycle(db, device.id)
    if not cycle:
        return None
    profile = await db.get(DomotiqueProfile, cycle.profile_id)
    return _cycle_full_payload(cycle, profile)


@router.get("/cycles", response_model=DomotiqueCycleListResponse)
async def list_cycles(
    limit: int = Query(default=20, ge=1, le=100),
    code: str = Query(default=_DEFAULT_DEVICE_CODE),
    current_user=Depends(require_permission("domotique.view")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, code)
    rows = (
        await db.execute(
            select(DomotiqueCycle)
            .where(DomotiqueCycle.device_id == device.id)
            .order_by(desc(DomotiqueCycle.created_at))
            .limit(limit)
        )
    ).scalars().all()
    payloads = []
    for cycle in rows:
        profile = await db.get(DomotiqueProfile, cycle.profile_id)
        payloads.append(_cycle_full_payload(cycle, profile))
    return DomotiqueCycleListResponse(cycles=payloads, total=len(payloads))


@router.post("/cycle", response_model=DomotiqueCycleResponse, status_code=201)
async def create_cycle(
    payload: DomotiqueCycleCreate,
    current_user=Depends(require_permission("domotique.control")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, payload.device_code)
    try:
        cycle = await cycles_service.create_cycle(db, device, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    profile = await db.get(DomotiqueProfile, cycle.profile_id)
    return _cycle_full_payload(cycle, profile)


async def _cycle_action(
    db: AsyncSession,
    action: str,
    cycle_id: int | None,
    code: str,
) -> tuple[DomotiqueCycle, DomotiqueProfile]:
    device = await _get_device(db, code)
    if cycle_id:
        cycle = await db.get(DomotiqueCycle, cycle_id)
        if not cycle or cycle.device_id != device.id:
            raise HTTPException(status_code=404, detail="Cycle introuvable")
    else:
        cycle = await cycles_service.get_active_cycle(db, device.id)
        if not cycle:
            raise HTTPException(status_code=409, detail="Aucun cycle actif")
    try:
        if action == "start":
            await cycles_service.start_cycle(db, device, cycle)
        elif action == "pause":
            await cycles_service.pause_cycle(db, device, cycle)
        elif action == "stop":
            await cycles_service.stop_cycle(db, device, cycle)
        elif action == "advance":
            await cycles_service.advance_phase(db, device, cycle)
        else:  # pragma: no cover
            raise ValueError(action)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    await db.refresh(cycle)
    profile = await db.get(DomotiqueProfile, cycle.profile_id)
    return cycle, profile


class CycleActionRequest(BaseModel):
    """Corps optionnel des actions sur un cycle (l'actif est pris par defaut)."""

    cycle_id: int | None = None
    code: str = _DEFAULT_DEVICE_CODE


@router.post("/cycle/start", response_model=DomotiqueCycleResponse)
async def start_cycle(
    payload: CycleActionRequest = CycleActionRequest(),
    current_user=Depends(require_permission("domotique.control")),
    db: AsyncSession = Depends(get_db),
):
    cycle, profile = await _cycle_action(db, "start", payload.cycle_id, payload.code)
    return _cycle_full_payload(cycle, profile)


@router.post("/cycle/pause", response_model=DomotiqueCycleResponse)
async def pause_cycle(
    payload: CycleActionRequest = CycleActionRequest(),
    current_user=Depends(require_permission("domotique.control")),
    db: AsyncSession = Depends(get_db),
):
    cycle, profile = await _cycle_action(db, "pause", payload.cycle_id, payload.code)
    return _cycle_full_payload(cycle, profile)


@router.post("/cycle/stop", response_model=DomotiqueCycleResponse)
async def stop_cycle(
    payload: CycleActionRequest = CycleActionRequest(),
    current_user=Depends(require_permission("domotique.control")),
    db: AsyncSession = Depends(get_db),
):
    cycle, profile = await _cycle_action(db, "stop", payload.cycle_id, payload.code)
    return _cycle_full_payload(cycle, profile)


@router.post("/cycle/advance", response_model=DomotiqueCycleResponse)
async def advance_cycle_phase(
    payload: CycleActionRequest = CycleActionRequest(),
    current_user=Depends(require_permission("domotique.control")),
    db: AsyncSession = Depends(get_db),
):
    cycle, profile = await _cycle_action(db, "advance", payload.cycle_id, payload.code)
    return _cycle_full_payload(cycle, profile)


# --------------------------------------------------------------------------- #
# Equipements (sorties)
# --------------------------------------------------------------------------- #

@router.post("/manual", response_model=DomotiqueManualResponse)
async def manual_command(
    payload: DomotiqueManualRequest,
    current_user=Depends(require_permission("domotique.control")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, _DEFAULT_DEVICE_CODE)
    try:
        output = await cycles_service.manual_command(
            db, device, payload.output_index, payload.state
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except raspberry.RaspberryError as exc:
        raise HTTPException(status_code=502, detail=f"Raspberry injoignable : {exc}")
    await db.commit()
    return DomotiqueManualResponse(
        ok=True,
        output_index=output.index,
        state=output.state,
        message=f"Sortie {output.index + 1} → {'ON' if output.state else 'OFF'}",
    )


@router.post("/outputs/{index}/mode", response_model=DomotiqueOutputResponse)
async def set_output_mode(
    index: int,
    payload: dict,
    current_user=Depends(require_permission("domotique.control")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, _DEFAULT_DEVICE_CODE)
    mode = payload.get("mode")
    try:
        output = await cycles_service.set_output_mode(db, device, index, mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    await db.refresh(output)
    return DomotiqueOutputResponse.model_validate(output)


class DomotiqueOutputUpdate(BaseModel):
    name: str | None = None
    role: str | None = None


_OUTPUT_ROLES_ALLOWED = {"heater", "cooler", "fan", "humidifier", "dehumidifier", "other"}


@router.put("/outputs/{output_id}", response_model=DomotiqueOutputResponse)
async def update_output(
    output_id: int,
    payload: DomotiqueOutputUpdate,
    current_user=Depends(require_permission("domotique.configure")),
    db: AsyncSession = Depends(get_db),
):
    output = await db.get(DomotiqueOutput, output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Sortie introuvable")
    if payload.name is not None and payload.name.strip():
        output.name = payload.name.strip()[:100]
    if payload.role is not None:
        if payload.role not in _OUTPUT_ROLES_ALLOWED:
            raise HTTPException(status_code=422, detail="Rôle invalide")
        output.role = payload.role
    await db.commit()
    await db.refresh(output)
    return DomotiqueOutputResponse.model_validate(output)


class DomotiqueSensorUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None


@router.put("/sensors/{sensor_id}", response_model=DomotiqueSensorResponse)
async def update_sensor(
    sensor_id: int,
    payload: DomotiqueSensorUpdate,
    current_user=Depends(require_permission("domotique.configure")),
    db: AsyncSession = Depends(get_db),
):
    sensor = await db.get(DomotiqueSensor, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Capteur introuvable")
    if payload.name is not None and payload.name.strip():
        sensor.name = payload.name.strip()[:100]
    if payload.enabled is not None:
        sensor.enabled = payload.enabled
    await db.commit()
    await db.refresh(sensor)
    return DomotiqueSensorResponse.model_validate(sensor)


# --------------------------------------------------------------------------- #
# Profils
# --------------------------------------------------------------------------- #

def _profile_payload(profile: DomotiqueProfile) -> DomotiqueProfileResponse:
    return DomotiqueProfileResponse.model_validate(profile)


@router.get("/profiles", response_model=DomotiqueProfileListResponse)
async def list_profiles(
    current_user=Depends(require_permission("domotique.view")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(DomotiqueProfile).order_by(DomotiqueProfile.is_system.desc(), DomotiqueProfile.name)
        )
    ).scalars().all()
    return DomotiqueProfileListResponse(
        profiles=[_profile_payload(p) for p in rows], total=len(rows)
    )


def _apply_profile_payload(profile: DomotiqueProfile, payload: DomotiqueProfileUpsert) -> None:
    profile.code = payload.code
    profile.name = payload.name
    profile.description = payload.description
    profile.target_weight_loss_pct = payload.target_weight_loss_pct
    profile.weight_loss_min_pct = payload.weight_loss_min_pct
    profile.weight_loss_max_pct = payload.weight_loss_max_pct


@router.post("/profiles", response_model=DomotiqueProfileResponse, status_code=201)
async def create_profile(
    payload: DomotiqueProfileUpsert,
    current_user=Depends(require_permission("domotique.configure")),
    db: AsyncSession = Depends(get_db),
):
    exists = (
        await db.execute(select(DomotiqueProfile).where(DomotiqueProfile.code == payload.code))
    ).scalars().first()
    if exists:
        raise HTTPException(status_code=409, detail="Ce code de profil existe déjà")
    profile = DomotiqueProfile(is_system=False)
    _apply_profile_payload(profile, payload)
    db.add(profile)
    await db.flush()
    for phase in payload.phases:
        db.add(DomotiquePhase(profile_id=profile.id, **phase.model_dump()))
    await db.commit()
    await db.refresh(profile)
    return _profile_payload(profile)


@router.put("/profiles/{profile_id}", response_model=DomotiqueProfileResponse)
async def update_profile(
    profile_id: int,
    payload: DomotiqueProfileUpsert,
    current_user=Depends(require_permission("domotique.configure")),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(DomotiqueProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    duplicate = (
        await db.execute(
            select(DomotiqueProfile).where(
                DomotiqueProfile.code == payload.code,
                DomotiqueProfile.id != profile.id,
            )
        )
    ).scalars().first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Ce code de profil existe déjà")
    in_use = (
        await db.execute(
            select(DomotiqueCycle.id)
            .where(
                DomotiqueCycle.profile_id == profile.id,
                DomotiqueCycle.status.in_(
                    [CycleStatus.PREPARING, CycleStatus.RUNNING, CycleStatus.PAUSED]
                ),
            )
            .limit(1)
        )
    ).scalars().first()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="Profil utilisé par un cycle actif : modification refusée",
        )
    _apply_profile_payload(profile, payload)
    for existing in list(profile.phases):
        await db.delete(existing)
    await db.flush()
    for phase in payload.phases:
        db.add(DomotiquePhase(profile_id=profile.id, **phase.model_dump()))
    await db.commit()
    await db.refresh(profile)
    return _profile_payload(profile)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: int,
    current_user=Depends(require_permission("domotique.configure")),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(DomotiqueProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    if profile.is_system:
        raise HTTPException(status_code=409, detail="Les profils système ne sont pas supprimables")
    used = (
        await db.execute(
            select(DomotiqueCycle.id).where(DomotiqueCycle.profile_id == profile.id).limit(1)
        )
    ).scalars().first()
    if used:
        raise HTTPException(status_code=409, detail="Profil utilisé par un cycle existant")
    await db.delete(profile)
    await db.commit()


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

@router.get("/config", response_model=DomotiqueConfigResponse)
async def get_config(
    code: str = Query(default=_DEFAULT_DEVICE_CODE),
    current_user=Depends(require_permission("domotique.configure")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, code)
    outputs = (
        await db.execute(
            select(DomotiqueOutput)
            .where(DomotiqueOutput.device_id == device.id)
            .order_by(DomotiqueOutput.index)
        )
    ).scalars().all()
    sensors = (
        await db.execute(
            select(DomotiqueSensor)
            .where(DomotiqueSensor.device_id == device.id)
            .order_by(DomotiqueSensor.id)
        )
    ).scalars().all()
    raw_config = dict(device.config_json or {})
    api_user = raw_config.get("api_user")
    has_password = bool(raw_config.get("api_password"))
    safe_config = {
        key: value
        for key, value in raw_config.items()
        if key not in ("api_user", "api_password")
    }
    return DomotiqueConfigResponse(
        code=device.code,
        base_url=device.base_url,
        poll_interval_s=device.poll_interval_s,
        api_user=api_user,
        has_api_password=has_password,
        config=safe_config,
        outputs=outputs,
        sensors=sensors,
    )


@router.put("/config", response_model=DomotiqueConfigResponse)
async def update_config(
    payload: DomotiqueConfigUpdate,
    code: str = Query(default=_DEFAULT_DEVICE_CODE),
    current_user=Depends(require_permission("domotique.configure")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, code)
    if payload.base_url is not None:
        base = payload.base_url.strip()
        if base and not base.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=422, detail="L'adresse doit commencer par http:// ou https://"
            )
        device.base_url = base.rstrip("/") or None
    if payload.poll_interval_s is not None:
        device.poll_interval_s = payload.poll_interval_s
    config = dict(device.config_json or {})
    for field in ("temp_min", "temp_max", "hum_min", "hum_max", "alert_cooldown_min", "retention_days", "obsolete_after_s", "cooler_min_off_s", "cooler_min_on_s", "alarm_temp_delta", "alarm_hum_delta", "comm_timeout_s"):
        value = getattr(payload, field)
        if value is not None:
            config[field] = value
    if payload.api_user is not None:
        user = payload.api_user.strip()
        if not user:
            config.pop("api_user", None)
            config.pop("api_password", None)
        else:
            config["api_user"] = user
            if payload.api_password is not None:
                if payload.api_password:
                    config["api_password"] = payload.api_password
                else:
                    config.pop("api_password", None)
    elif payload.api_password:
        config["api_password"] = payload.api_password
    device.config_json = config
    await db.commit()
    await db.refresh(device)
    return await get_config(code=code, current_user=current_user, db=db)


@router.post("/config/test", response_model=DomotiqueTestConnectionResponse)
async def test_connection(
    payload: DomotiqueConfigTestRequest | None = None,
    code: str = Query(default=_DEFAULT_DEVICE_CODE),
    current_user=Depends(require_permission("domotique.configure")),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(db, code)
    saved = dict(device.config_json or {})
    base_url = device.base_url
    auth = raspberry.credentials_from_config(saved)
    if payload is not None:
        if payload.base_url is not None and payload.base_url.strip():
            base_url = payload.base_url.strip()
            if not base_url.startswith(("http://", "https://")):
                return DomotiqueTestConnectionResponse(
                    ok=False, message="L'adresse doit commencer par http:// ou https://"
                )
        if payload.api_user is not None or payload.api_password is not None:
            user = payload.api_user if payload.api_user is not None else (saved.get("api_user") or "")
            password = (
                payload.api_password
                if payload.api_password is not None
                else (saved.get("api_password") or "")
            )
            auth = (user, password) if user and password else None
    if not base_url:
        return DomotiqueTestConnectionResponse(
            ok=False, message="Adresse du Raspberry non configurée"
        )
    try:
        result = await raspberry.test_connection(base_url, auth=auth)
    except raspberry.RaspberryError as exc:
        return DomotiqueTestConnectionResponse(
            ok=False, message=f"Échec de la connexion : {exc}"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("[DOMOTIQUE] Test connexion en echec", exc_info=True)
        return DomotiqueTestConnectionResponse(
            ok=False, message=f"Erreur inattendue : {exc}"
        )
    return DomotiqueTestConnectionResponse(
        ok=True,
        message=f"Connexion réussie ({result['latency_ms']} ms)",
        latency_ms=result["latency_ms"],
        state=result.get("state"),
    )
