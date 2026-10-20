"""Mapping des locaux (bureau ET logement) sur les sites et coût du repas par site."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.api.intendance import meal_cost_by_site
from app.models import (
    AgendaPresence, Building, Housing, IntendanceCategory, IntendanceExpense,
    IntendanceSite, Occupancy, Room, Site, UsageType,
)


async def _seed(db_session):
    """Insère le jeu de données et renvoie des identifiants (session partagée)."""
    bureau_usage = UsageType(code="BUREAUX", name="Bureaux")
    logement_usage = UsageType(code="LOGEMENT", name="Logement")
    physical_site = Site(reference="SITE1", name="Site test")
    db_session.add_all([bureau_usage, logement_usage, physical_site])
    await db_session.flush()

    building = Building(site_id=physical_site.id, reference="B1", name="Batiment 1")
    db_session.add(building)
    await db_session.flush()

    bureau_room = Room(
        building_id=building.id, reference="B101", name="Bureau 1",
        usage_type_id=bureau_usage.id,
    )
    logement_room = Room(
        building_id=building.id, reference="L101", name="Chambre 1",
        usage_type_id=logement_usage.id,
    )
    site_bureau = IntendanceSite(name="Site bureau")
    site_logement = IntendanceSite(name="Site logement")
    db_session.add_all([bureau_room, logement_room, site_bureau, site_logement])
    db_session.add(IntendanceCategory(name="Nourriture"))
    await db_session.flush()

    # Lundi (compté) + samedi (exclu : jours ouvrés uniquement).
    db_session.add_all([
        AgendaPresence(
            presence_date=date(2026, 1, 5), room_id=bureau_room.id,
            external_name="Invite A", is_present=True, needs_meal=True,
        ),
        AgendaPresence(
            presence_date=date(2026, 1, 10), room_id=bureau_room.id,
            external_name="Invite A", is_present=True, needs_meal=True,
        ),
    ])

    # Occupation samedi 03/01 -> mardi 06/01 inclusive, 2 personnes :
    # 4 jours d'occupation, week-end compris = 8 repas.
    housing = Housing(room_id=logement_room.id, capacity=2)
    db_session.add(housing)
    await db_session.flush()
    db_session.add(Occupancy(
        housing_id=housing.id, status="confirmed",
        arrival_date=datetime(2026, 1, 3), departure_date=datetime(2026, 1, 6),
        nb_persons=2,
    ))

    db_session.add(IntendanceExpense(
        fingerprint="fp-meal-1", req_number=1, expense_date=date(2026, 1, 5),
        item_description="Courses", amount=Decimal("100.00"),
        category="Nourriture", user_name="DEVAUD", site_id=site_bureau.id,
    ))
    db_session.add(IntendanceExpense(
        fingerprint="fp-meal-2", req_number=2, expense_date=date(2026, 1, 5),
        item_description="Courses", amount=Decimal("80.00"),
        category="Nourriture", user_name="DEVAUD", site_id=site_logement.id,
    ))
    ids = {
        "bureau_room_id": bureau_room.id,
        "logement_room_id": logement_room.id,
        "site_bureau_id": site_bureau.id,
        "site_logement_id": site_logement.id,
    }
    await db_session.commit()
    # Les tests partagent la session avec l'application : sans expiration,
    # Session.get() renvoie l'instance déjà présente et ignore le selectinload.
    db_session.expire_all()
    return ids


async def test_site_rooms_accepts_logement_room(client, admin_headers, db_session):
    data = await _seed(db_session)

    response = await client.put(
        f"/intendance/expenses/sites/{data['site_bureau_id']}/rooms",
        json={"room_ids": [data["bureau_room_id"], data["logement_room_id"]]},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    mapped = {room["id"] for room in response.json()["mapped_rooms"]}
    assert mapped == {data["bureau_room_id"], data["logement_room_id"]}

    listed = await client.get("/intendance/expenses/sites", headers=admin_headers)
    assert listed.status_code == 200
    site = next(item for item in listed.json()["items"] if item["id"] == data["site_bureau_id"])
    assert {room["id"] for room in site["mapped_rooms"]} == mapped


async def test_site_rooms_still_rejects_other_rooms(client, admin_headers, db_session):
    data = await _seed(db_session)
    # Local sans type d'usage : toujours refusé.
    bureau_room = (await db_session.execute(
        select(Room).where(Room.id == data["bureau_room_id"])
    )).scalar_one()
    room = Room(building_id=bureau_room.building_id, reference="X001", name="Sans usage")
    db_session.add(room)
    await db_session.commit()

    response = await client.put(
        f"/intendance/expenses/sites/{data['site_bureau_id']}/rooms",
        json={"room_ids": [room.id]},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "bureau ou logement" in response.json()["detail"]


async def test_meal_cost_by_site_counts_occupancy_days(client, admin_headers, db_session):
    data = await _seed(db_session)

    for site_id, room_id in (
        (data["site_bureau_id"], data["bureau_room_id"]),
        (data["site_logement_id"], data["logement_room_id"]),
    ):
        response = await client.put(
            f"/intendance/expenses/sites/{site_id}/rooms",
            json={"room_ids": [room_id]},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text

    db_session.expire_all()
    result = await meal_cost_by_site(
        date(2026, 1, 1), date(2026, 1, 31), user_name=None, site_id=None,
        current_user=None, db=db_session,
    )
    by_name = {item["name"]: item for item in result["items"]}

    # Bureau : présence du lundi uniquement (le samedi est exclu).
    assert by_name["Site bureau"]["meal_count"] == 1
    assert by_name["Site bureau"]["amount"] == 100.0
    assert by_name["Site bureau"]["cost_per_person"] == 100.0

    # Logement : 4 jours d'occupation x 2 personnes, week-end inclus.
    assert by_name["Site logement"]["meal_count"] == 8
    assert by_name["Site logement"]["cost_per_person"] == 10.0
