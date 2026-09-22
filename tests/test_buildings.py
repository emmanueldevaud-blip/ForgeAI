from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models.buildings import Building, Room, Site, UsageType, RoomType
from app.models.equipment import Equipment
from app.models.housing import Housing, Occupancy


@pytest.mark.asyncio
async def test_list_sites_empty(client, admin_headers):
    response = await client.get("/buildings/sites", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_create_site(client, admin_headers):
    response = await client.post("/buildings/sites", json={
        "name": "Site Test",
        "city": "Paris",
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["reference"].startswith("SITE-")
    assert data["name"] == "Site Test"
    assert data["city"] == "Paris"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_get_site(client, admin_headers):
    create_resp = await client.post("/buildings/sites", json={
        "name": "Get Site",
    }, headers=admin_headers)
    site_id = create_resp.json()["id"]

    response = await client.get(f"/buildings/sites/{site_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Get Site"


@pytest.mark.asyncio
async def test_update_site(client, admin_headers):
    create_resp = await client.post("/buildings/sites", json={
        "name": "Original",
    }, headers=admin_headers)
    site_id = create_resp.json()["id"]

    response = await client.patch(f"/buildings/sites/{site_id}", json={
        "name": "Updated",
    }, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"


@pytest.mark.asyncio
async def test_list_sites_with_search(client, admin_headers):
    await client.post("/buildings/sites", json={"name": "Alpha Site"}, headers=admin_headers)
    await client.post("/buildings/sites", json={"name": "Beta Site"}, headers=admin_headers)

    response = await client.get("/buildings/sites?search=Alpha", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Alpha Site"


@pytest.mark.asyncio
async def test_create_building(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "B Site"}, headers=admin_headers)
    site_id = site_resp.json()["id"]

    response = await client.post("/buildings", json={
        "name": "Building A",
        "site_id": site_id,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["reference"].startswith("BAT-")
    assert data["site_id"] == site_id


@pytest.mark.asyncio
async def test_list_buildings_by_site(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "B2"}, headers=admin_headers)
    site_id = site_resp.json()["id"]

    await client.post("/buildings", json={"name": "Bldg A", "site_id": site_id}, headers=admin_headers)
    await client.post("/buildings", json={"name": "Bldg B", "site_id": site_id}, headers=admin_headers)

    response = await client.get(f"/buildings?site_id={site_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2


@pytest.mark.asyncio
async def test_update_building(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Update Building Site"}, headers=admin_headers)
    building_resp = await client.post(
        "/buildings",
        json={"name": "Original Building", "site_id": site_resp.json()["id"]},
        headers=admin_headers,
    )

    response = await client.patch(
        f"/buildings/{building_resp.json()['id']}",
        json={"name": "Updated Building", "building_number": "B-12"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Building"
    assert response.json()["building_number"] == "B-12"


# ============================================================
# ROOMS (directly under Building)
# ============================================================

@pytest.mark.asyncio
async def test_create_room(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "R Site"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"name": "R Bldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]

    response = await client.post("/buildings/rooms", json={
        "name": "Room 101",
        "building_id": bldg_id,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Room 101"
    assert data["reference"].startswith("LOC-")
    assert data["building_id"] == bldg_id


@pytest.mark.asyncio
async def test_list_rooms_by_building(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "R2"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"name": "R Bldg 2", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]

    await client.post("/buildings/rooms", json={"name": "Room A", "building_id": bldg_id}, headers=admin_headers)
    await client.post("/buildings/rooms", json={"name": "Room B", "building_id": bldg_id}, headers=admin_headers)

    response = await client.get(f"/buildings/rooms?building_id={bldg_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2


@pytest.mark.asyncio
async def test_room_with_usage_type(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "USite"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"name": "UBldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)

    ut_resp = await client.post("/buildings/usage-types", json={"name": "Test Usage"}, headers=admin_headers)
    ut_id = ut_resp.json()["id"]

    response = await client.post("/buildings/rooms", json={
        "name": "Room with Usage",
        "building_id": bldg_resp.json()["id"],
        "usage_type_id": ut_id,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["usage_type_id"] == ut_id


@pytest.mark.asyncio
async def test_room_with_room_type(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "TSite"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"name": "TBldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)

    rt_resp = await client.post("/buildings/room-types", json={"name": "Test Room Type"}, headers=admin_headers)
    rt_id = rt_resp.json()["id"]

    response = await client.post("/buildings/rooms", json={
        "name": "Room with Type",
        "building_id": bldg_resp.json()["id"],
        "room_type_id": rt_id,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["room_type_id"] == rt_id


@pytest.mark.asyncio
async def test_update_room(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "USite2"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"name": "UBldg2", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    room_resp = await client.post("/buildings/rooms", json={"name": "Original", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)
    room_id = room_resp.json()["id"]

    ut_resp = await client.post("/buildings/usage-types", json={"name": "Updated Usage"}, headers=admin_headers)
    ut_id = ut_resp.json()["id"]

    response = await client.patch(f"/buildings/rooms/{room_id}", json={
        "name": "Updated",
        "usage_type_id": ut_id,
    }, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["usage_type_id"] == ut_id


@pytest.mark.asyncio
async def test_room_used_for_accommodation(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "HSite"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"name": "HBldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)

    response = await client.post("/buildings/rooms", json={
        "name": "Accommodation Room",
        "building_id": bldg_resp.json()["id"],
        "used_for_accommodation": True,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["used_for_accommodation"] is True


# ============================================================
# HIERARCHY TESTS
# ============================================================

@pytest.mark.asyncio
async def test_full_hierarchy(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Full Hierarchy Site"}, headers=admin_headers)
    site_id = site_resp.json()["id"]
    assert site_resp.status_code == 201

    bldg_resp = await client.post("/buildings", json={"name": "Building A", "site_id": site_id}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]
    assert bldg_resp.status_code == 201

    room_resp = await client.post("/buildings/rooms", json={"name": "Room 1", "building_id": bldg_id}, headers=admin_headers)
    assert room_resp.status_code == 201

    get_bldg = await client.get(f"/buildings/{bldg_id}", headers=admin_headers)
    assert get_bldg.status_code == 200
    bldg_data = get_bldg.json()
    assert len(bldg_data["rooms"]) == 1
    assert bldg_data["rooms"][0]["name"] == "Room 1"


@pytest.mark.asyncio
async def test_building_without_rooms(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "NR Site"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"name": "NR Bldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]

    get_bldg = await client.get(f"/buildings/{bldg_id}", headers=admin_headers)
    assert get_bldg.status_code == 200
    assert get_bldg.json()["room_count"] == 0


@pytest.mark.asyncio
async def test_multiple_buildings_in_site(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Multi Bldg Site"}, headers=admin_headers)
    site_id = site_resp.json()["id"]

    await client.post("/buildings", json={"name": "Building 1", "site_id": site_id}, headers=admin_headers)
    await client.post("/buildings", json={"name": "Building 2", "site_id": site_id}, headers=admin_headers)

    response = await client.get(f"/buildings?site_id={site_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2


@pytest.mark.asyncio
async def test_multiple_rooms_in_building(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Multi Room Site"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"name": "MR Bldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]

    await client.post("/buildings/rooms", json={"name": "Room 1", "building_id": bldg_id}, headers=admin_headers)
    await client.post("/buildings/rooms", json={"name": "Room 2", "building_id": bldg_id}, headers=admin_headers)
    await client.post("/buildings/rooms", json={"name": "Room 3", "building_id": bldg_id}, headers=admin_headers)

    response = await client.get(f"/buildings/rooms?building_id={bldg_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 3


# ============================================================
# REFERENCE TYPES
# ============================================================

@pytest.mark.asyncio
async def test_list_usage_types(client, admin_headers):
    await client.post("/buildings/usage-types", json={"name": "Bureaux"}, headers=admin_headers)
    await client.post("/buildings/usage-types", json={"name": "Logement"}, headers=admin_headers)

    response = await client.get("/buildings/usage-types", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_room_types(client, admin_headers):
    await client.post("/buildings/room-types", json={"name": "Chambre"}, headers=admin_headers)
    await client.post("/buildings/room-types", json={"name": "Cuisine"}, headers=admin_headers)

    response = await client.get("/buildings/room-types", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_create_usage_type(client, admin_headers):
    response = await client.post("/buildings/usage-types", json={
        "name": "Commercial",
    }, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["code"] == "COMMERCIAL"


@pytest.mark.asyncio
async def test_create_room_type(client, admin_headers):
    response = await client.post("/buildings/room-types", json={
        "name": "Garage",
    }, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["code"] == "GARAGE"


# ============================================================
# TOGGLE / PAGINATION / AUTH
# ============================================================

@pytest.mark.asyncio
async def test_toggle_site_active(client, admin_headers):
    create_resp = await client.post("/buildings/sites", json={"name": "Toggle"}, headers=admin_headers)
    site_id = create_resp.json()["id"]

    response = await client.patch(f"/buildings/sites/{site_id}", json={"is_active": False}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_list_sites_pagination(client, admin_headers):
    for i in range(5):
        await client.post("/buildings/sites", json={"name": f"Page Site {i}"}, headers=admin_headers)

    response = await client.get("/buildings/sites?page=1&page_size=2", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["total_pages"] == 3


@pytest.mark.asyncio
async def test_unauthenticated_access_denied(client):
    response = await client.get("/buildings/sites")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_site_not_found(client, admin_headers):
    response = await client.get("/buildings/sites/99999", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_building_not_found(client, admin_headers):
    response = await client.get("/buildings/99999", headers=admin_headers)
    assert response.status_code == 404


# ============================================================
# DELETE PROTECTIONS
# ============================================================

@pytest.mark.asyncio
async def test_delete_empty_site(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Empty Site"}, headers=admin_headers)

    response = await client.delete(f"/buildings/sites/{site_resp.json()['id']}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Site supprimé"


@pytest.mark.asyncio
async def test_cannot_delete_site_with_buildings(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Protected Site"}, headers=admin_headers)
    site_id = site_resp.json()["id"]
    await client.post("/buildings", json={"name": "Building in Site", "site_id": site_id}, headers=admin_headers)

    response = await client.delete(f"/buildings/sites/{site_id}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Impossible de supprimer le site « Protected Site » : il contient 1 bâtiment(s)."
    )


@pytest.mark.asyncio
async def test_delete_empty_building(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Empty Building Site"}, headers=admin_headers)
    building_resp = await client.post(
        "/buildings",
        json={"name": "Empty Building", "site_id": site_resp.json()["id"]},
        headers=admin_headers,
    )

    response = await client.delete(f"/buildings/{building_resp.json()['id']}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Bâtiment supprimé"


@pytest.mark.asyncio
async def test_cannot_delete_building_with_rooms(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Protected Building Site"}, headers=admin_headers)
    building_resp = await client.post(
        "/buildings",
        json={"name": "Protected Building", "site_id": site_resp.json()["id"]},
        headers=admin_headers,
    )
    building_id = building_resp.json()["id"]
    await client.post("/buildings/rooms", json={"name": "Room in Building", "building_id": building_id}, headers=admin_headers)

    response = await client.delete(f"/buildings/{building_id}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Impossible de supprimer le bâtiment « Protected Building » : il contient 1 local(aux)."
    )


@pytest.mark.asyncio
async def test_create_update_and_delete_unused_usage_type(client, admin_headers):
    create_response = await client.post("/buildings/usage-types", json={"name": "Unused Type"}, headers=admin_headers)
    usage_type_id = create_response.json()["id"]
    assert create_response.status_code == 201

    update_response = await client.patch(
        f"/buildings/usage-types/{usage_type_id}",
        json={"name": "Renamed Type"},
        headers=admin_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Renamed Type"

    delete_response = await client.delete(f"/buildings/usage-types/{usage_type_id}", headers=admin_headers)
    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_cannot_delete_usage_type_used_by_room(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Usage Type Site"}, headers=admin_headers)
    building_resp = await client.post(
        "/buildings",
        json={"name": "Usage Type Building", "site_id": site_resp.json()["id"]},
        headers=admin_headers,
    )
    usage_type_resp = await client.post("/buildings/usage-types", json={"name": "Protected Usage Type"}, headers=admin_headers)
    usage_type_id = usage_type_resp.json()["id"]
    await client.post(
        "/buildings/rooms",
        json={"name": "Typed Room", "building_id": building_resp.json()["id"], "usage_type_id": usage_type_id},
        headers=admin_headers,
    )

    response = await client.delete(f"/buildings/usage-types/{usage_type_id}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Impossible de supprimer le type d'utilisation « Protected Usage Type » : il est utilisé par 1 local(aux)."
    )


@pytest.mark.asyncio
async def test_cannot_delete_room_type_used_by_room(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Room Type Site"}, headers=admin_headers)
    building_resp = await client.post(
        "/buildings",
        json={"name": "Room Type Building", "site_id": site_resp.json()["id"]},
        headers=admin_headers,
    )
    room_type_resp = await client.post("/buildings/room-types", json={"name": "Protected Room Type"}, headers=admin_headers)
    room_type_id = room_type_resp.json()["id"]
    await client.post(
        "/buildings/rooms",
        json={"name": "Typed Room", "building_id": building_resp.json()["id"], "room_type_id": room_type_id},
        headers=admin_headers,
    )

    response = await client.delete(f"/buildings/room-types/{room_type_id}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Impossible de supprimer le type de pièce « Protected Room Type » : il est utilisé par 1 local(aux)."
    )


@pytest.mark.asyncio
async def test_delete_empty_room(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"name": "Empty Room Site"}, headers=admin_headers)
    building_resp = await client.post(
        "/buildings",
        json={"name": "Empty Room Building", "site_id": site_resp.json()["id"]},
        headers=admin_headers,
    )
    room_resp = await client.post(
        "/buildings/rooms",
        json={"name": "Empty Room", "building_id": building_resp.json()["id"]},
        headers=admin_headers,
    )
    room_id = room_resp.json()["id"]

    response = await client.delete(f"/buildings/rooms/{room_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Local supprimé"


@pytest.mark.asyncio
async def test_force_delete_room_removes_associated_data(client, admin_headers, db_session):
    site_resp = await client.post("/buildings/sites", json={"name": "Force Delete Site"}, headers=admin_headers)
    building_resp = await client.post(
        "/buildings",
        json={"name": "Force Delete Building", "site_id": site_resp.json()["id"]},
        headers=admin_headers,
    )
    room_resp = await client.post(
        "/buildings/rooms",
        json={"name": "Room With Dependencies", "building_id": building_resp.json()["id"]},
        headers=admin_headers,
    )
    room_id = room_resp.json()["id"]

    db_session.add(Equipment(reference="EQ-FORCE-DELETE", name="Equipment", room_id=room_id))
    housing = Housing(room_id=room_id)
    db_session.add(housing)
    await db_session.flush()
    db_session.add(Occupancy(
        housing_id=housing.id,
        arrival_date=datetime.now(UTC),
        departure_date=datetime.now(UTC) + timedelta(days=1),
    ))
    await db_session.commit()

    blocked = await client.delete(f"/buildings/rooms/{room_id}", headers=admin_headers)
    assert blocked.status_code == 409

    deleted = await client.delete(f"/buildings/rooms/{room_id}?force=true", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json()["message"] == "Local supprimé"


@pytest.mark.asyncio
async def test_delete_unused_room_type(client, admin_headers):
    create_resp = await client.post("/buildings/room-types", json={"name": "Unused Room Type"}, headers=admin_headers)
    assert create_resp.status_code == 201
    rt_id = create_resp.json()["id"]

    response = await client.delete(f"/buildings/room-types/{rt_id}", headers=admin_headers)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_reference_generation_avoids_collision_after_delete(client, admin_headers):
    # Create 3 sites
    resp1 = await client.post("/buildings/sites", json={"name": "Site Col 1"}, headers=admin_headers)
    resp2 = await client.post("/buildings/sites", json={"name": "Site Col 2"}, headers=admin_headers)
    resp3 = await client.post("/buildings/sites", json={"name": "Site Col 3"}, headers=admin_headers)
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp3.status_code == 201

    # Delete the second site (resp2)
    del_resp = await client.delete(f"/buildings/sites/{resp2.json()['id']}", headers=admin_headers)
    assert del_resp.status_code == 200

    # Creating a 4th site must NOT fail with reference collision
    resp4 = await client.post("/buildings/sites", json={"name": "Site Col 4"}, headers=admin_headers)
    assert resp4.status_code == 201
    assert resp4.json()["reference"] != resp3.json()["reference"]
