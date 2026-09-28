import pytest

from app.services.domotique import cycles as cycles_service
from app.services.domotique import engine as domotique_engine
from app.services.domotique.seed import SECHOIR_CODE, seed_domotique


@pytest.fixture
async def domo_seed(db_session):
    await seed_domotique(db_session)
    return db_session


@pytest.mark.asyncio
async def test_domotique_requires_permission(client, auth_headers, domo_seed):
    response = await client.get("/domotique/status", headers=auth_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_domotique_status_seed_and_outputs(client, admin_headers, domo_seed):
    response = await client.get("/domotique/status", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == SECHOIR_CODE
    assert payload["last_seen"] is None
    assert len(payload["outputs"]) == 8
    sensor_keys = {sensor["key"] for sensor in payload["sensors"]}
    assert {"temperature", "humidity"}.issubset(sensor_keys)
    assert payload["cycle"] is None


@pytest.mark.asyncio
async def test_domotique_profiles_seeded(client, admin_headers, domo_seed):
    response = await client.get("/domotique/profiles", headers=admin_headers)

    assert response.status_code == 200
    profiles = response.json()["profiles"]
    assert len(profiles) >= 1
    codes = {p["code"] for p in profiles}
    assert "sechage-classique" in codes
    for profile in profiles:
        assert profile["phases"], "chaque profil doit avoir des phases"
        assert profile["is_system"] is False, "profil éditable (plus de profil système)"
        for phase in profile["phases"]:
            assert phase["exit_condition"] in {"time", "weight", "manual"}


@pytest.mark.asyncio
async def test_domotique_config_update_and_connection_test(client, admin_headers, domo_seed):
    updated = await client.put(
        "/domotique/config",
        headers=admin_headers,
        json={
            "base_url": "http://127.0.0.1:1",
            "poll_interval_s": 45,
            "cooler_min_off_s": 240,
            "cooler_min_on_s": 90,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["base_url"] == "http://127.0.0.1:1"
    assert updated.json()["poll_interval_s"] == 45
    assert updated.json()["config"]["cooler_min_off_s"] == 240
    assert updated.json()["config"]["cooler_min_on_s"] == 90

    tested = await client.post("/domotique/config/test", headers=admin_headers)
    assert tested.status_code == 200
    assert tested.json()["ok"] is False

    fetched = await client.get("/domotique/config", headers=admin_headers)
    assert fetched.json()["base_url"] == "http://127.0.0.1:1"
    assert fetched.json()["config"]["temp_max"] is not None


@pytest.mark.asyncio
async def test_domotique_config_credentials_hidden(client, admin_headers, domo_seed):
    updated = await client.put(
        "/domotique/config",
        headers=admin_headers,
        json={"api_user": "forgeai", "api_password": "secret-test"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["api_user"] == "forgeai"
    assert body["has_api_password"] is True
    assert "api_password" not in body
    assert "api_password" not in body["config"]

    fetched = (await client.get("/domotique/config", headers=admin_headers)).json()
    assert fetched["api_user"] == "forgeai"
    assert fetched["has_api_password"] is True
    assert "api_password" not in fetched
    assert "api_password" not in fetched["config"]

    cleared = await client.put(
        "/domotique/config", headers=admin_headers, json={"api_user": ""}
    )
    assert cleared.status_code == 200
    assert cleared.json()["api_user"] is None
    assert cleared.json()["has_api_password"] is False


@pytest.mark.asyncio
async def test_domotique_cycle_flow(client, admin_headers, domo_seed):
    empty = await client.get("/domotique/cycle", headers=admin_headers)
    assert empty.status_code == 200

    profiles = (await client.get("/domotique/profiles", headers=admin_headers)).json()["profiles"]
    profile_id = profiles[0]["id"]
    phases_count = len(profiles[0]["phases"])

    created = await client.post(
        "/domotique/cycle",
        headers=admin_headers,
        json={
            "profile_id": profile_id,
            "device_code": SECHOIR_CODE,
            "product": "Saucisson sec",
            "casing_size": "40 mm",
            "initial_weight": 1000,
            "start_now": True,
        },
    )
    assert created.status_code == 201
    cycle_id = created.json()["id"]
    assert created.json()["status"] == "running"
    assert phases_count >= 1

    status = (await client.get("/domotique/status", headers=admin_headers)).json()
    assert status["cycle"] is not None
    assert status["cycle"]["id"] == cycle_id

    paused = await client.post("/domotique/cycle/pause", headers=admin_headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = await client.post("/domotique/cycle/start", headers=admin_headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"

    if phases_count > 1:
        advanced = await client.post("/domotique/cycle/advance", headers=admin_headers)
        assert advanced.status_code == 200
        assert advanced.json()["current_phase_id"] != created.json()["current_phase_id"]

    stopped = await client.post("/domotique/cycle/stop", headers=admin_headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"

    events = (await client.get("/domotique/events", headers=admin_headers)).json()["events"]
    assert events, "le cycle doit être journalisé"


@pytest.mark.asyncio
async def test_domotique_output_update_and_manual_mode(client, admin_headers, domo_seed):
    status = (await client.get("/domotique/status", headers=admin_headers)).json()
    output = status["outputs"][0]

    updated = await client.put(
        f"/domotique/outputs/{output['id']}",
        headers=admin_headers,
        json={"name": "Chauffage arrière", "role": "heater"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Chauffage arrière"
    assert updated.json()["role"] == "heater"

    bad_role = await client.put(
        f"/domotique/outputs/{output['id']}",
        headers=admin_headers,
        json={"role": "inconnu"},
    )
    assert bad_role.status_code == 422

    manual = await client.post(
        "/domotique/outputs/0/mode",
        headers=admin_headers,
        json={"mode": "manual"},
    )
    assert manual.status_code == 200
    assert manual.json()["mode"] == "manual"

    command = await client.post(
        "/domotique/manual",
        headers=admin_headers,
        json={"output_index": 0, "state": True},
    )
    assert command.status_code == 409, "adresse du Raspberry non configurée dans les tests"


@pytest.mark.asyncio
async def test_domotique_motor_regulation_with_fake_pi(domo_seed, monkeypatch):
    db = domo_seed

    fake_state = {
        "temperature": 8.0,
        "humidity": 90.0,
        "weight": 950.0,
        "outputs": [False] * 8,
        "timestamp": None,
    }

    async def fake_fetch_state(base_url, timeout=2.0, auth=None):
        return dict(fake_state)

    sent_commands = []

    async def fake_send_command(base_url, index, state, timeout=2.0, auth=None):
        sent_commands.append((index, state))
        fake_state["outputs"][index] = state

    monkeypatch.setattr(domotique_engine.raspberry, "fetch_state", fake_fetch_state)
    monkeypatch.setattr(domotique_engine.raspberry, "send_command", fake_send_command)

    from sqlalchemy import select

    from app.models.domotique import DomotiqueDevice, DomotiqueOutput
    from app.schemas.domotique import DomotiqueCycleCreate

    from app.models.domotique import DomotiqueProfile

    device = (await db.execute(select(DomotiqueDevice))).scalars().first()
    assert device is not None
    device.base_url = "http://fake-raspberry.local"

    outputs = (await db.execute(select(DomotiqueOutput).where(DomotiqueOutput.device_id == device.id))).scalars().all()
    heater = outputs[0]
    heater.role = "heater"
    heater.mode = "auto"
    await db.commit()

    profile = (await db.execute(select(DomotiqueProfile).order_by(DomotiqueProfile.id))).scalars().first()
    await cycles_service.create_cycle(
        db, device, DomotiqueCycleCreate(profile_id=profile.id, start_now=True)
    )

    await domotique_engine.poll_device(db, device)

    await db.refresh(heater)
    assert (heater.index, True) in sent_commands, "le chauffage doit s'activer sous la consigne"
    assert heater.state is True

    fake_state["temperature"] = 40.0
    await domotique_engine.poll_device(db, device)

    await db.refresh(heater)
    assert (heater.index, False) in sent_commands, "le chauffage doit s'éteindre au-dessus de la consigne"
    assert heater.state is False


def test_cooler_anti_short_cycle():
    from datetime import datetime, timedelta, timezone

    from app.models.domotique import DomotiqueOutput

    now = datetime.now(timezone.utc)

    def make_output(role: str, state: bool, seconds_ago: int) -> DomotiqueOutput:
        output = DomotiqueOutput(index=1, name="Groupe froid", role=role, mode="auto", state=state)
        output.updated_at = now - timedelta(seconds=seconds_ago)
        return output

    ok = domotique_engine._cooler_delay_ok
    cooler_on = make_output("cooler", True, 30)
    assert ok(cooler_on, False, now, 180, 120) is False, "arrêt interdit avant 120 s de marche"
    assert ok(cooler_on, True, now, 180, 120) is True, "pas de transition → aucune contrainte"
    assert ok(make_output("cooler", True, 200), False, now, 180, 120) is True, "marche suffisante → arrêt ok"

    cooler_off = make_output("cooler", False, 30)
    assert ok(cooler_off, True, now, 180, 120) is False, "démarrage interdit avant 180 s d'arrêt"
    assert ok(make_output("cooler", False, 200), True, now, 180, 120) is True, "délai respecté → démarrage ok"

    assert ok(make_output("heater", True, 0), False, now, 180, 120) is True, "le chauffage n'est pas concerné"


@pytest.mark.asyncio
async def test_profile_edit_blocked_only_by_active_cycle(client, admin_headers, domo_seed):
    profiles = (await client.get("/domotique/profiles", headers=admin_headers)).json()["profiles"]
    profile = next(p for p in profiles if p["code"] == "sechage-classique")
    payload = {
        "code": profile["code"],
        "name": profile["name"],
        "description": profile.get("description"),
        "target_weight_loss_pct": profile.get("target_weight_loss_pct"),
        "weight_loss_min_pct": profile.get("weight_loss_min_pct"),
        "weight_loss_max_pct": profile.get("weight_loss_max_pct"),
        "phases": profile["phases"],
    }

    created = await client.post(
        "/domotique/cycle",
        headers=admin_headers,
        json={"profile_id": profile["id"], "start_now": True},
    )
    assert created.status_code == 201

    refused = await client.put(
        f"/domotique/profiles/{profile['id']}", headers=admin_headers, json=payload
    )
    assert refused.status_code == 409

    stopped = await client.post(
        "/domotique/cycle/stop",
        headers=admin_headers,
        json={"cycle_id": created.json()["id"]},
    )
    assert stopped.status_code == 200

    updated = await client.put(
        f"/domotique/profiles/{profile['id']}",
        headers=admin_headers,
        json={**payload, "description": "profil modifiable"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "profil modifiable"


def test_corrected_humidity_compensates_sensor_temperature():
    corrected = domotique_engine._corrected_humidity

    assert corrected(13.0, 85.0, 13.0) == 85.0, "meme temperature -> pas de correction"
    assert corrected(None, 85.0, 13.0) == 85.0
    assert corrected(14.0, None, 13.0) is None
    assert corrected(14.0, 85.0, None) == 85.0

    colder_reference = corrected(14.0, 85.0, 13.0)
    assert colder_reference is not None and colder_reference > 85.0, (
        "capteur plus chaud que la consigne -> HR corrigee plus haute"
    )
    warmer_reference = corrected(12.0, 85.0, 13.0)
    assert warmer_reference is not None and warmer_reference < 85.0, (
        "capteur plus froid que la consigne -> HR corrigee plus basse"
    )
    assert 0.0 <= (colder_reference or 0) <= 100.0


def test_desired_states_use_corrected_humidity():
    from app.models.domotique import DomotiqueOutput, DomotiquePhase, OutputMode

    phase = DomotiquePhase(
        profile_id=1,
        order=1,
        name="Séchage",
        target_temperature=13.0,
        target_humidity=84.0,
        tolerance_temperature=1.0,
        tolerance_humidity=2.0,
        exit_condition="time",
    )
    outputs = [
        DomotiqueOutput(index=2, name="Humidificateur", role="humidifier", mode=OutputMode.AUTO),
        DomotiqueOutput(index=3, name="Déshumidificateur", role="dehumidifier", mode=OutputMode.AUTO),
    ]

    desired = domotique_engine._desired_states(phase, 14.0, 82.5, outputs)
    assert desired.get(3) is True, "HR corrigee (~88 %) au-dessus de la cible -> déshumidificateur ON"
    assert desired.get(2) is not True, (
        "sans correction la valeur brute (82,5 %) aurait lancé l'humidificateur"
    )


@pytest.mark.asyncio
async def test_status_exposes_corrected_humidity(client, admin_headers, domo_seed, db_session):
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.domotique import DomotiqueSensor, DomotiqueSensorReading

    sensors = {
        s.key: s for s in (await db_session.execute(select(DomotiqueSensor))).scalars().all()
    }
    sensors["temperature"].current_value = 14.0
    sensors["humidity"].current_value = 85.0
    recorded_at = datetime.now(timezone.utc)
    db_session.add(
        DomotiqueSensorReading(
            sensor_id=sensors["temperature"].id, value=14.0, recorded_at=recorded_at
        )
    )
    db_session.add(
        DomotiqueSensorReading(
            sensor_id=sensors["humidity"].id, value=85.0, recorded_at=recorded_at
        )
    )
    await db_session.commit()

    status = (await client.get("/domotique/status", headers=admin_headers)).json()
    hum = next(s for s in status["sensors"] if s["key"] == "humidity")
    assert hum["current_value"] == 85.0
    assert hum["corrected_value"] is None, "hors cycle -> aucune reference de temperature"

    profiles = (await client.get("/domotique/profiles", headers=admin_headers)).json()["profiles"]
    created = await client.post(
        "/domotique/cycle",
        headers=admin_headers,
        json={"profile_id": profiles[0]["id"], "start_now": True},
    )
    assert created.status_code == 201

    status = (await client.get("/domotique/status", headers=admin_headers)).json()
    hum = next(s for s in status["sensors"] if s["key"] == "humidity")
    assert hum["corrected_value"] is not None, "en cycle -> valeur corrigee fournie"
    assert abs(hum["corrected_value"] - hum["current_value"]) > 1.0, (
        "capteur a 14 °C sous une cible a 23 °C -> ecart de correction net"
    )

    history = (await client.get("/domotique/history?period=24h", headers=admin_headers)).json()
    points = history["series"].get("humidity") or []
    assert points, "l'historique hum reste fourni"
    expected = domotique_engine._corrected_humidity(14.0, 85.0, 23.0)
    assert expected is not None
    assert abs(points[-1]["v"] - expected) < 0.1, "la serie hum est corrigee de la temperature"
    assert abs(points[-1]["v"] - 85.0) > 1.0


@pytest.mark.asyncio
async def test_history_includes_output_states(client, admin_headers, domo_seed, db_session):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.domotique import DomotiqueDevice, DomotiqueEvent

    device = (await db_session.execute(select(DomotiqueDevice))).scalars().first()
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add(
        DomotiqueEvent(
            device_id=device.id,
            type="command",
            message="Sortie 2 (Groupe froid) → ON (auto)",
            metadata_json={"index": 1, "state": True, "mode": "auto"},
            created_at=base,
        )
    )
    db_session.add(
        DomotiqueEvent(
            device_id=device.id,
            type="command",
            message="Sortie 2 (Groupe froid) → OFF (auto)",
            metadata_json={"index": 1, "state": False, "mode": "auto"},
            created_at=base + timedelta(minutes=10),
        )
    )
    await db_session.commit()

    history = (await client.get("/domotique/history?period=24h", headers=admin_headers)).json()
    series = {s["index"]: s for s in history["outputs"]}
    assert 1 in series, "la sortie pilotee a un historique"
    assert series[1]["points"], "les transitions sont fournies"
    values = [p["v"] for p in series[1]["points"]]
    assert values[0] == 1.0 and values[1] == 0.0, "transitions ON puis OFF"
    assert history["outputs"][0]["name"]


@pytest.mark.asyncio
async def test_alarm_notifications_on_drift_and_disconnect(domo_seed, db_session, admin_user):
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.models.domotique import (
        DomotiqueDevice,
        DomotiqueProfile,
        DomotiqueSensor,
    )
    from app.models.notification import Notification
    from app.schemas.domotique import DomotiqueCycleCreate

    db = domo_seed
    device = (await db.execute(select(DomotiqueDevice))).scalars().first()
    device.base_url = "http://fake-raspberry.local"
    profile = (await db.execute(select(DomotiqueProfile).order_by(DomotiqueProfile.id))).scalars().first()

    sensors = {
        s.key: s
        for s in (await db.execute(select(DomotiqueSensor))).scalars().all()
    }
    sensors["temperature"].current_value = 25.0  # phase Étuvage : 23 °C ± 1
    sensors["humidity"].current_value = 50.0  # 92 % HR ± 3
    await db.commit()

    cycle = await cycles_service.create_cycle(
        db, device, DomotiqueCycleCreate(profile_id=profile.id, start_now=True)
    )
    phase = next(p for p in profile.phases if p.id == cycle.current_phase_id)
    assert phase is not None

    async def notif_count() -> int:
        return (await db.execute(select(func.count(Notification.id)))).scalar_one()

    async def notif_titles() -> list[str]:
        rows = (await db.execute(select(Notification.title))).scalars().all()
        return list(rows)

    # 1) Alarme de decalage +/- consigne (temperature et humidite)
    before = await notif_count()
    await domotique_engine._check_phase_ranges(db, device, cycle, phase, sensors)
    await db.commit()
    assert await notif_count() > before, "le decalage hors consigne doit notifier"
    titles = await notif_titles()
    assert any("hors plage" in title for title in titles), titles

    # 2) Anti-spam : une deuxieme alarme du meme type reste dans le cooldown
    before = await notif_count()
    recent = await domotique_engine._add_event(
        db, device, "out_of_range_temperature", "alarme repetee", cycle=cycle
    )
    await domotique_engine._maybe_notify(
        db,
        device,
        ["out_of_range_temperature"],
        "La Cave — Température hors plage",
        "alarme repetee",
        exclude_event_id=recent.id,
    )
    await db.commit()
    assert await notif_count() == before, "le cooldown anti-spam doit s'appliquer"

    # 3) Alarme de deconnexion
    device.status = "online"
    device.last_seen = domotique_engine._now() - timedelta(minutes=5)
    await db.commit()
    before = await notif_count()
    await domotique_engine._check_communication(db, device, ok=False, error="timeout")
    await db.commit()
    assert await notif_count() > before, "la deconnexion doit notifier"
    titles = await notif_titles()
    assert any("injoignable" in title for title in titles), titles
