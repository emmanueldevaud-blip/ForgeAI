from datetime import date

import pytest


async def _setup_bureau_room(client, admin_headers):
    site = await client.post("/buildings/sites", json={"name": "Agenda Site"}, headers=admin_headers)
    building = await client.post(
        "/buildings",
        json={"name": "Agenda Bldg", "site_id": site.json()["id"]},
        headers=admin_headers,
    )
    usage = await client.post(
        "/buildings/usage-types",
        json={"name": "Bureaux"},
        headers=admin_headers,
    )
    room = await client.post(
        "/buildings/rooms",
        json={
            "name": "Bureau 1",
            "building_id": building.json()["id"],
            "usage_type_id": usage.json()["id"],
            "workstation_capacity": 4,
        },
        headers=admin_headers,
    )
    assert room.status_code == 201, room.text
    assert room.json()["workstation_capacity"] == 4
    return room.json()["id"]


@pytest.mark.asyncio
async def test_agenda_requires_permission(client, auth_headers):
    response = await client.get("/agenda/planning?view=week", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agenda_planning_and_presence_flow(client, admin_headers):
    room_id = await _setup_bureau_room(client, admin_headers)

    planning = await client.get("/agenda/planning?view=week", headers=admin_headers)
    assert planning.status_code == 200, planning.text
    data = planning.json()
    assert data["view"] == "week"
    assert any(r["id"] == room_id for r in data["rooms"])
    assert any(r["id"] == room_id for r in data["rooms"] if r.get("workstation_capacity") == 4)
    assert len(data["days"]) == 7
    today = date.today().isoformat()
    assert any(day["date"] == today for day in data["days"])

    created = await client.post(
        "/agenda/presences",
        json={
            "presence_date": today,
            "room_id": room_id,
            "is_present": True,
            "needs_workstation": True,
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    presence_id = created.json()["id"]
    assert presence_id > 0

    planning = await client.get(f"/agenda/planning?view=week&anchor={today}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == today)
    assert day["total_present"] >= 1
    assert day["total_workstations"] >= 1
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 1
    assert room_day["workstation_count"] == 1
    assert any(p["is_mine"] for p in room_day["presences"])

    external = await client.post(
        "/agenda/presences/external",
        json={
            "presence_date": today,
            "room_id": room_id,
            "external_name": "Visiteur Test",
            "needs_workstation": False,
        },
        headers=admin_headers,
    )
    assert external.status_code == 200, external.text

    planning = await client.get(f"/agenda/planning?view=week&anchor={today}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == today)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 2
    assert any(p["person_type"] == "external" for p in room_day["presences"])

    removed = await client.delete(f"/agenda/presences/{presence_id}", headers=admin_headers)
    assert removed.status_code == 204

    planning = await client.get(f"/agenda/planning?view=week&anchor={today}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == today)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 1


@pytest.mark.asyncio
async def test_agenda_month_and_quarter_views(client, admin_headers):
    await _setup_bureau_room(client, admin_headers)
    today = date.today().isoformat()

    month = await client.get(f"/agenda/planning?view=month&anchor={today}", headers=admin_headers)
    assert month.status_code == 200
    assert month.json()["view"] == "month"
    assert len(month.json()["days"]) >= 28

    quarter = await client.get(f"/agenda/planning?view=quarter&anchor={today}", headers=admin_headers)
    assert quarter.status_code == 200
    assert quarter.json()["view"] == "quarter"
    assert 80 <= len(quarter.json()["days"]) <= 92


@pytest.mark.asyncio
async def test_room_workstation_capacity_roundtrip(client, admin_headers):
    site = await client.post("/buildings/sites", json={"name": "Cap Site"}, headers=admin_headers)
    building = await client.post(
        "/buildings",
        json={"name": "Cap Bldg", "site_id": site.json()["id"]},
        headers=admin_headers,
    )
    room = await client.post(
        "/buildings/rooms",
        json={"name": "Cap Room", "building_id": building.json()["id"], "workstation_capacity": 6},
        headers=admin_headers,
    )
    assert room.status_code == 201
    assert room.json()["workstation_capacity"] == 6

    updated = await client.patch(
        f"/buildings/rooms/{room.json()['id']}",
        json={"workstation_capacity": 3},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["workstation_capacity"] == 3
