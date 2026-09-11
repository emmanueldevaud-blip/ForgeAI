import pytest
from httpx import AsyncClient

from app.models.buildings import Building, Level, Room, Site, UsageType, RoomType


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
        "reference": "SITE001",
        "name": "Site Test",
        "city": "Paris",
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["reference"] == "SITE001"
    assert data["name"] == "Site Test"
    assert data["city"] == "Paris"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_site_duplicate_reference(client, admin_headers):
    await client.post("/buildings/sites", json={
        "reference": "DUP001",
        "name": "First Site",
    }, headers=admin_headers)
    response = await client.post("/buildings/sites", json={
        "reference": "DUP001",
        "name": "Second Site",
    }, headers=admin_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_site(client, admin_headers):
    create_resp = await client.post("/buildings/sites", json={
        "reference": "SITE002",
        "name": "Get Site",
    }, headers=admin_headers)
    site_id = create_resp.json()["id"]

    response = await client.get(f"/buildings/sites/{site_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["reference"] == "SITE002"


@pytest.mark.asyncio
async def test_update_site(client, admin_headers):
    create_resp = await client.post("/buildings/sites", json={
        "reference": "SITE003",
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
    await client.post("/buildings/sites", json={"reference": "SRCH01", "name": "Alpha Site"}, headers=admin_headers)
    await client.post("/buildings/sites", json={"reference": "SRCH02", "name": "Beta Site"}, headers=admin_headers)

    response = await client.get("/buildings/sites?search=Alpha", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Alpha Site"


@pytest.mark.asyncio
async def test_create_building(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "BSITE01", "name": "B Site"}, headers=admin_headers)
    site_id = site_resp.json()["id"]

    response = await client.post("/buildings", json={
        "reference": "BLDG001",
        "name": "Building A",
        "site_id": site_id,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["reference"] == "BLDG001"
    assert data["site_id"] == site_id


@pytest.mark.asyncio
async def test_list_buildings_by_site(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "BSITE02", "name": "B2"}, headers=admin_headers)
    site_id = site_resp.json()["id"]

    await client.post("/buildings", json={"reference": "BLDG02A", "name": "Bldg A", "site_id": site_id}, headers=admin_headers)
    await client.post("/buildings", json={"reference": "BLDG02B", "name": "Bldg B", "site_id": site_id}, headers=admin_headers)

    response = await client.get(f"/buildings?site_id={site_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2


# ============================================================
# LEVELS
# ============================================================

@pytest.mark.asyncio
async def test_create_level(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "LSITE01", "name": "L Site"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "LBLDG01", "name": "L Bldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]

    response = await client.post("/buildings/levels", json={
        "reference": "LVL001",
        "name": "RDC",
        "building_id": bldg_id,
        "level_order": 0,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["reference"] == "LVL001"
    assert data["name"] == "RDC"
    assert data["building_id"] == bldg_id
    assert data["level_order"] == 0


@pytest.mark.asyncio
async def test_list_levels_by_building(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "LSITE02", "name": "L2"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "LBLDG02", "name": "L Bldg 2", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]

    await client.post("/buildings/levels", json={"reference": "LVL02A", "name": "RDC", "building_id": bldg_id, "level_order": 0}, headers=admin_headers)
    await client.post("/buildings/levels", json={"reference": "LVL02B", "name": "R+1", "building_id": bldg_id, "level_order": 1}, headers=admin_headers)

    response = await client.get(f"/buildings/levels?building_id={bldg_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2


@pytest.mark.asyncio
async def test_update_level(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "LSITE03", "name": "L3"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "LBLDG03", "name": "L Bldg 3", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    lvl_resp = await client.post("/buildings/levels", json={"reference": "LVL03", "name": "Original", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)
    lvl_id = lvl_resp.json()["id"]

    response = await client.patch(f"/buildings/levels/{lvl_id}", json={"name": "Updated"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"


@pytest.mark.asyncio
async def test_create_level_duplicate_reference(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "LSITE04", "name": "L4"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "LBLDG04", "name": "L Bldg 4", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]

    await client.post("/buildings/levels", json={"reference": "DUP_LV", "name": "First", "building_id": bldg_id}, headers=admin_headers)
    response = await client.post("/buildings/levels", json={"reference": "DUP_LV", "name": "Second", "building_id": bldg_id}, headers=admin_headers)
    assert response.status_code == 409


# ============================================================
# ROOMS (directly under Level)
# ============================================================

@pytest.mark.asyncio
async def test_create_room(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "RSITE01", "name": "R Site"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "RBLDG01", "name": "R Bldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    lvl_resp = await client.post("/buildings/levels", json={"reference": "RLVL01", "name": "RDC", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)
    lvl_id = lvl_resp.json()["id"]

    response = await client.post("/buildings/rooms", json={
        "reference": "RM001",
        "name": "Room 101",
        "level_id": lvl_id,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Room 101"
    assert data["reference"] == "RM001"
    assert data["level_id"] == lvl_id


@pytest.mark.asyncio
async def test_list_rooms_by_level(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "RSITE02", "name": "R2"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "RBLDG02", "name": "R Bldg 2", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    lvl_resp = await client.post("/buildings/levels", json={"reference": "RLVL02", "name": "RDC", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)
    lvl_id = lvl_resp.json()["id"]

    await client.post("/buildings/rooms", json={"reference": "RM02A", "name": "Room A", "level_id": lvl_id}, headers=admin_headers)
    await client.post("/buildings/rooms", json={"reference": "RM02B", "name": "Room B", "level_id": lvl_id}, headers=admin_headers)

    response = await client.get(f"/buildings/rooms?level_id={lvl_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2


@pytest.mark.asyncio
async def test_room_with_usage_type(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "USITE01", "name": "USite"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "UBLDG01", "name": "UBldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    lvl_resp = await client.post("/buildings/levels", json={"reference": "ULVL01", "name": "RDC", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)

    ut_resp = await client.post("/buildings/usage-types", json={"code": "UTEST", "name": "Test Usage"}, headers=admin_headers)
    ut_id = ut_resp.json()["id"]

    response = await client.post("/buildings/rooms", json={
        "reference": "URM01",
        "name": "Room with Usage",
        "level_id": lvl_resp.json()["id"],
        "usage_type_id": ut_id,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["usage_type_id"] == ut_id


@pytest.mark.asyncio
async def test_room_with_room_type(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "TSITE01", "name": "TSite"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "TBLDG01", "name": "TBldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    lvl_resp = await client.post("/buildings/levels", json={"reference": "TLVL01", "name": "RDC", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)

    rt_resp = await client.post("/buildings/room-types", json={"code": "TTEST", "name": "Test Room Type"}, headers=admin_headers)
    rt_id = rt_resp.json()["id"]

    response = await client.post("/buildings/rooms", json={
        "reference": "TRM01",
        "name": "Room with Type",
        "level_id": lvl_resp.json()["id"],
        "room_type_id": rt_id,
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["room_type_id"] == rt_id


@pytest.mark.asyncio
async def test_update_room(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "USITE02", "name": "USite2"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "UBLDG02", "name": "UBldg2", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    lvl_resp = await client.post("/buildings/levels", json={"reference": "ULVL02", "name": "RDC", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)
    room_resp = await client.post("/buildings/rooms", json={"reference": "URM02", "name": "Original", "level_id": lvl_resp.json()["id"]}, headers=admin_headers)
    room_id = room_resp.json()["id"]

    ut_resp = await client.post("/buildings/usage-types", json={"code": "UUPD", "name": "Updated Usage"}, headers=admin_headers)
    ut_id = ut_resp.json()["id"]

    response = await client.patch(f"/buildings/rooms/{room_id}", json={
        "name": "Updated",
        "usage_type_id": ut_id,
    }, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["usage_type_id"] == ut_id


# ============================================================
# HIERARCHY TESTS
# ============================================================

@pytest.mark.asyncio
async def test_full_hierarchy(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "FH_SITE", "name": "Full Hierarchy Site"}, headers=admin_headers)
    site_id = site_resp.json()["id"]
    assert site_resp.status_code == 201

    bldg_resp = await client.post("/buildings", json={"reference": "FH_BLDG", "name": "Building A", "site_id": site_id}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]
    assert bldg_resp.status_code == 201

    lvl_resp = await client.post("/buildings/levels", json={"reference": "FH_LVL", "name": "RDC", "building_id": bldg_id, "level_order": 0}, headers=admin_headers)
    lvl_id = lvl_resp.json()["id"]
    assert lvl_resp.status_code == 201

    room_resp = await client.post("/buildings/rooms", json={"reference": "FH_RM01", "name": "Room 1", "level_id": lvl_id}, headers=admin_headers)
    assert room_resp.status_code == 201

    get_bldg = await client.get(f"/buildings/{bldg_id}", headers=admin_headers)
    assert get_bldg.status_code == 200
    bldg_data = get_bldg.json()
    assert len(bldg_data["levels"]) == 1
    assert bldg_data["levels"][0]["reference"] == "FH_LVL"

    get_lvl = await client.get(f"/buildings/levels/{lvl_id}", headers=admin_headers)
    assert get_lvl.status_code == 200
    lvl_data = get_lvl.json()
    assert len(lvl_data["rooms"]) == 1
    assert lvl_data["rooms"][0]["reference"] == "FH_RM01"


@pytest.mark.asyncio
async def test_level_without_rooms(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "NRSITE", "name": "NR Site"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "NRBLDG", "name": "NR Bldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    lvl_resp = await client.post("/buildings/levels", json={"reference": "NRLVL", "name": "RDC", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)
    lvl_id = lvl_resp.json()["id"]

    get_lvl = await client.get(f"/buildings/levels/{lvl_id}", headers=admin_headers)
    assert get_lvl.status_code == 200
    assert get_lvl.json()["room_count"] == 0


@pytest.mark.asyncio
async def test_multiple_buildings_in_site(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "MBSITE", "name": "Multi Bldg Site"}, headers=admin_headers)
    site_id = site_resp.json()["id"]

    await client.post("/buildings", json={"reference": "MB_BLDG1", "name": "Building 1", "site_id": site_id}, headers=admin_headers)
    await client.post("/buildings", json={"reference": "MB_BLDG2", "name": "Building 2", "site_id": site_id}, headers=admin_headers)

    response = await client.get(f"/buildings?site_id={site_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2


@pytest.mark.asyncio
async def test_multiple_levels_in_building(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "MLSITE", "name": "Multi Level Site"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "MLBLDG", "name": "Multi Level Bldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    bldg_id = bldg_resp.json()["id"]

    await client.post("/buildings/levels", json={"reference": "ML_0", "name": "Sous-sol", "building_id": bldg_id, "level_order": -1}, headers=admin_headers)
    await client.post("/buildings/levels", json={"reference": "ML_1", "name": "RDC", "building_id": bldg_id, "level_order": 0}, headers=admin_headers)
    await client.post("/buildings/levels", json={"reference": "ML_2", "name": "R+1", "building_id": bldg_id, "level_order": 1}, headers=admin_headers)

    response = await client.get(f"/buildings/levels?building_id={bldg_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 3


@pytest.mark.asyncio
async def test_multiple_rooms_in_level(client, admin_headers):
    site_resp = await client.post("/buildings/sites", json={"reference": "MRSITE", "name": "Multi Room Site"}, headers=admin_headers)
    bldg_resp = await client.post("/buildings", json={"reference": "MRBLDG", "name": "MR Bldg", "site_id": site_resp.json()["id"]}, headers=admin_headers)
    lvl_resp = await client.post("/buildings/levels", json={"reference": "MRLVL", "name": "RDC", "building_id": bldg_resp.json()["id"]}, headers=admin_headers)
    lvl_id = lvl_resp.json()["id"]

    await client.post("/buildings/rooms", json={"reference": "MR_01", "name": "Room 1", "level_id": lvl_id}, headers=admin_headers)
    await client.post("/buildings/rooms", json={"reference": "MR_02", "name": "Room 2", "level_id": lvl_id}, headers=admin_headers)
    await client.post("/buildings/rooms", json={"reference": "MR_03", "name": "Room 3", "level_id": lvl_id}, headers=admin_headers)

    response = await client.get(f"/buildings/rooms?level_id={lvl_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 3


# ============================================================
# REFERENCE TYPES
# ============================================================

@pytest.mark.asyncio
async def test_list_usage_types(client, admin_headers):
    await client.post("/buildings/usage-types", json={"code": "BUREAUX", "name": "Bureaux"}, headers=admin_headers)
    await client.post("/buildings/usage-types", json={"code": "LOGEMENT", "name": "Logement"}, headers=admin_headers)

    response = await client.get("/buildings/usage-types", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    codes = [item["code"] for item in data["items"]]
    assert "BUREAUX" in codes
    assert "LOGEMENT" in codes


@pytest.mark.asyncio
async def test_list_room_types(client, admin_headers):
    await client.post("/buildings/room-types", json={"code": "CHAMBRE", "name": "Chambre"}, headers=admin_headers)
    await client.post("/buildings/room-types", json={"code": "CUISINE", "name": "Cuisine"}, headers=admin_headers)

    response = await client.get("/buildings/room-types", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    codes = [item["code"] for item in data["items"]]
    assert "CHAMBRE" in codes
    assert "CUISINE" in codes


@pytest.mark.asyncio
async def test_create_usage_type(client, admin_headers):
    response = await client.post("/buildings/usage-types", json={
        "code": "COMMERCIAL",
        "name": "Commercial",
    }, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["code"] == "COMMERCIAL"


@pytest.mark.asyncio
async def test_create_room_type(client, admin_headers):
    response = await client.post("/buildings/room-types", json={
        "code": "GARAGE",
        "name": "Garage",
    }, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["code"] == "GARAGE"


# ============================================================
# TOGGLE / PAGINATION / AUTH
# ============================================================

@pytest.mark.asyncio
async def test_toggle_site_active(client, admin_headers):
    create_resp = await client.post("/buildings/sites", json={"reference": "TGL01", "name": "Toggle"}, headers=admin_headers)
    site_id = create_resp.json()["id"]

    response = await client.patch(f"/buildings/sites/{site_id}", json={"is_active": False}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_list_sites_pagination(client, admin_headers):
    for i in range(5):
        await client.post("/buildings/sites", json={"reference": f"PAG{i:03d}", "name": f"Page Site {i}"}, headers=admin_headers)

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


@pytest.mark.asyncio
async def test_level_not_found(client, admin_headers):
    response = await client.get("/buildings/levels/99999", headers=admin_headers)
    assert response.status_code == 404
