"""Seed idempotent du module Domotique.

Cree au premier demarrage (si absents) :
  - le device « sechoir-saucisson » (Raspberry Pi passerelle) ;
  - ses capteurs (temperature, humidité I2C ; balance optionnelle desactivee) ;
  - ses 8 sorties GPIO configurables ;
  - les profils de cycle par defaut (§ profils fournis par le client).

Aucune valeur n'est criblee dans le code applicatif : tout est editable
depuis l'interface de configuration.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domotique import (
    DomotiqueDevice,
    DomotiqueOutput,
    DomotiquePhase,
    DomotiqueProfile,
    DomotiqueSensor,
    ExitCondition,
)

SECHOIR_CODE = "sechoir-saucisson"

DEFAULT_DEVICE_CONFIG: dict = {
    "temp_min": 5.0,
    "temp_max": 30.0,
    "hum_min": 40.0,
    "hum_max": 99.0,
    "alert_cooldown_min": 30,
    "retention_days": 90,
    "obsolete_after_s": 90,
}

_SENSORS = [
    # key, name, unit, enabled
    ("temperature", "Température", "°C", True),
    ("humidity", "Humidité", "% HR", True),
    ("weight", "Poids", "g", False),  # balance : activee si le Raspberry la fournit
]

_OUTPUT_ROLES = ["other"] * 8

# --------------------------------------------------------------------------- #
# Profils par defaut
# --------------------------------------------------------------------------- #

DEFAULT_PROFILES: list[dict] = [
    {
        "code": "sechage-classique",
        "name": "Séchage classique",
        "description": (
            "Cycle à 4 phases : étuvage, ressuyage, séchage (3 à 6 semaines) "
            "puis affinage. Durées et cibles modifiables."
        ),
        "target_weight_loss_pct": None,
        "weight_loss_min_pct": None,
        "weight_loss_max_pct": None,
        "phases": [
            {
                "order": 1,
                "name": "Étuvage",
                "target_temperature": 23.0,
                "target_humidity": 92.0,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 3.0,
                "min_duration_hours": 24.0,
                "max_duration_hours": 48.0,
                "weight_loss_target_pct": None,
                "exit_condition": ExitCondition.TIME,
            },
            {
                "order": 2,
                "name": "Ressuyage",
                "target_temperature": 19.0,
                "target_humidity": 82.0,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 3.0,
                "min_duration_hours": 24.0,
                "max_duration_hours": 48.0,
                "weight_loss_target_pct": None,
                "exit_condition": ExitCondition.TIME,
            },
            {
                "order": 3,
                "name": "Séchage",
                "target_temperature": 14.0,
                "target_humidity": 80.0,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 2.0,
                "min_duration_hours": 720.0,   # 3 semaines
                "max_duration_hours": 1008.0,  # 6 semaines
                "weight_loss_target_pct": None,
                "exit_condition": ExitCondition.TIME,
            },
            {
                "order": 4,
                "name": "Affinage",
                "target_temperature": 12.0,
                "target_humidity": 76.5,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 1.5,
                "min_duration_hours": None,
                "max_duration_hours": None,
                "weight_loss_target_pct": None,
                "exit_condition": ExitCondition.MANUAL,
            },
        ],
    },
    {
        "code": "alternatif-perte-poids",
        "name": "Alternatif — perte de poids",
        "description": (
            "3 phases (14 °C/88 % puis 13 °C/84 % puis 12 °C/78 %) ; "
            "fin de cycle pilotée par la perte de poids (objectif 38 %, plage 35 à 40 %)."
        ),
        "target_weight_loss_pct": 38.0,
        "weight_loss_min_pct": 35.0,
        "weight_loss_max_pct": 40.0,
        "phases": [
            {
                "order": 1,
                "name": "Phase 1",
                "target_temperature": 14.0,
                "target_humidity": 88.0,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 2.0,
                "min_duration_hours": 72.0,
                "max_duration_hours": 72.0,
                "weight_loss_target_pct": None,
                "exit_condition": ExitCondition.TIME,
            },
            {
                "order": 2,
                "name": "Phase 2",
                "target_temperature": 13.0,
                "target_humidity": 84.0,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 2.0,
                "min_duration_hours": 168.0,
                "max_duration_hours": 168.0,
                "weight_loss_target_pct": None,
                "exit_condition": ExitCondition.TIME,
            },
            {
                "order": 3,
                "name": "Phase 3 — jusqu'à objectif",
                "target_temperature": 12.0,
                "target_humidity": 78.0,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 2.0,
                "min_duration_hours": None,
                "max_duration_hours": None,
                "weight_loss_target_pct": 38.0,
                "exit_condition": ExitCondition.WEIGHT,
            },
        ],
    },
    {
        "code": "boyau-40mm",
        "name": "Boyau 40 mm",
        "description": (
            "Séchage à 14 °C / 80 % HR puis affinage vers 76-77 % HR. "
            "Durée pilotée par la perte de poids (objectif 38 %, plage 35 à 40 %) : "
            "renseigner le seuil de passage dans les phases si transition automatique souhaitée."
        ),
        "target_weight_loss_pct": 38.0,
        "weight_loss_min_pct": 35.0,
        "weight_loss_max_pct": 40.0,
        "phases": [
            {
                "order": 1,
                "name": "Séchage (HR 80 %)",
                "target_temperature": 14.0,
                "target_humidity": 80.0,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 2.0,
                "min_duration_hours": None,
                "max_duration_hours": None,
                "weight_loss_target_pct": None,
                "exit_condition": ExitCondition.WEIGHT,
            },
            {
                "order": 2,
                "name": "Descente HR (76-77 %)",
                "target_temperature": 14.0,
                "target_humidity": 76.5,
                "tolerance_temperature": 1.0,
                "tolerance_humidity": 1.5,
                "min_duration_hours": None,
                "max_duration_hours": None,
                "weight_loss_target_pct": 38.0,
                "exit_condition": ExitCondition.WEIGHT,
            },
        ],
    },
]


async def seed_domotique(db: AsyncSession) -> None:
    """Cree le device sechoir + capteurs + sorties + profils s'ils manquent."""
    device = (
        await db.execute(select(DomotiqueDevice).where(DomotiqueDevice.code == SECHOIR_CODE))
    ).scalar_one_or_none()
    if not device:
        device = DomotiqueDevice(
            code=SECHOIR_CODE,
            name="Séchoir à saucisson",
            kind="dryer",
            base_url=None,
            poll_interval_s=30,
            config_json=dict(DEFAULT_DEVICE_CONFIG),
        )
        db.add(device)
        await db.flush()

    existing_sensor_keys = {
        s.key
        for s in (
            await db.execute(
                select(DomotiqueSensor).where(DomotiqueSensor.device_id == device.id)
            )
        ).scalars().all()
    }
    for key, name, unit, enabled in _SENSORS:
        if key not in existing_sensor_keys:
            db.add(
                DomotiqueSensor(
                    device_id=device.id, key=key, name=name, unit=unit, enabled=enabled
                )
            )

    existing_output_indexes = {
        o.index
        for o in (
            await db.execute(
                select(DomotiqueOutput.index).where(DomotiqueOutput.device_id == device.id)
            )
        ).scalars().all()
    }
    for index in range(8):
        if index not in existing_output_indexes:
            db.add(
                DomotiqueOutput(
                    device_id=device.id,
                    index=index,
                    name=f"Sortie {index + 1}",
                    role=_OUTPUT_ROLES[index],
                )
            )

    existing_profile_codes = set(
        (await db.execute(select(DomotiqueProfile.code))).scalars().all()
    )
    for profile_data in DEFAULT_PROFILES:
        if profile_data["code"] in existing_profile_codes:
            continue
        phases = profile_data.pop("phases")
        profile = DomotiqueProfile(**profile_data, is_system=True)
        db.add(profile)
        await db.flush()
        for phase_data in phases:
            db.add(DomotiquePhase(profile_id=profile.id, **phase_data))
        profile_data["phases"] = phases  # restore pour un eventuel rejeu

    await db.commit()
