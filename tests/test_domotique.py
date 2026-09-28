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
    assert len(profiles) >= 3
    for profile in profiles:
        assert profile["phases"], "chaque profil doit avoir des phases"
        assert profile["is_system"] is True
        for phase in profile["phases"]:
            assert phase["exit_condition"] in {"time", "weight", "manual"}


@pytest.mark.asyncio
async def test_domotique_config_update_and_connection_test(client, admin_headers, domo_seed):
    updated = await client.put(
        "/domotique/config",
        headers=admin_headers,
        json={"base_url": "http://127.0.0.1:1", "poll_interval_s": 45},
    )
    assert updated.status_code == 200
    assert updated.json()["base_url"] == "http://127.0.0.1:1"
    assert updated.json()["poll_interval_s"] == 45

    tested = await client.post("/domotique/config/test", headers=admin_headers)
    assert tested.status_code == 200
    assert tested.json()["ok"] is False

    fetched = await client.get("/domotique/config", headers=admin_headers)
    assert fetched.json()["base_url"] == "http://127.0.0.1:1"
    assert fetched.json()["config"]["temp_max"] is not None


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

    async def fake_fetch_state(base_url, timeout=2.0):
        return dict(fake_state)

    sent_commands = []

    async def fake_send_command(base_url, index, state, timeout=2.0):
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
