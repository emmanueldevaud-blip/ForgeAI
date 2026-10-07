from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Group, GroupGroup, PermissionModel, Role, RolePermission, UserGroup, UserRoleAssignment
from app.models.user import UserRole
from app.services.auth import create_user


def _next_weekday(day: date) -> date:
    """Prochain jour ouvre (lun-ven), aujourd'hui s'il en est deja un."""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


async def _setup_bureau_rooms(client, admin_headers, names=("Bureau 1",)):
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
    room_ids = []
    for name in names:
        room = await client.post(
            "/buildings/rooms",
            json={
                "name": name,
                "building_id": building.json()["id"],
                "usage_type_id": usage.json()["id"],
                "workstation_capacity": 4,
            },
            headers=admin_headers,
        )
        assert room.status_code == 201, room.text
        assert room.json()["workstation_capacity"] == 4
        room_ids.append(room.json()["id"])
    return room_ids


async def _setup_bureau_room(client, admin_headers, name="Bureau 1", capacity=4):
    room_ids = await _setup_bureau_rooms(client, admin_headers, names=(name,))
    return room_ids[0]


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
    assert len(data["days"]) == 5
    # Lun–Ven only
    from datetime import datetime as _dt
    for d in data["days"]:
        assert _dt.strptime(d["date"], "%Y-%m-%d").weekday() < 5
    today = date.today().isoformat()
    if date.today().weekday() < 5:
        assert any(day["date"] == today for day in data["days"])

    created = await client.post(
        "/agenda/presences",
        json={
            # Le planning semaine n'affiche que lun-ven : toujours tester
            # sur un jour ouvre meme lorsque les tests tournent le week-end.
            "presence_date": _next_weekday(date.today()).isoformat(),
            "room_id": room_id,
            "is_present": True,
            "needs_workstation": True,
            "needs_meal": True,
            "period": "morning",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    presence_id = created.json()["id"]
    assert presence_id > 0
    assert created.json()["period"] == "morning"
    assert created.json()["needs_meal"] is True

    presence_date = created.json()["presence_date"]
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    assert day["total_present"] >= 1
    assert day["total_workstations"] >= 1
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 1
    assert room_day["workstation_count"] == 1
    mine = next(p for p in room_day["presences"] if p["is_mine"])
    assert mine["period"] == "morning"
    assert mine["person_type"] == "user"
    assert mine["needs_meal"] is True

    external = await client.post(
        "/agenda/presences/external",
        json={
            "presence_date": presence_date,
            "room_id": room_id,
            "external_name": "Visiteur Test",
            "needs_workstation": False,
            "period": "afternoon",
        },
        headers=admin_headers,
    )
    assert external.status_code == 200, external.text
    assert external.json()["period"] == "afternoon"

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 2
    assert any(p["person_type"] == "external" and p["period"] == "afternoon" for p in room_day["presences"])

    removed = await client.delete(f"/agenda/presences/{presence_id}", headers=admin_headers)
    assert removed.status_code == 204

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 1


@pytest.mark.asyncio
async def test_agenda_split_presence_two_rooms(client, admin_headers):
    room_a, room_b = await _setup_bureau_rooms(
        client, admin_headers, names=("Bureau A", "Bureau B")
    )

    # Jour ouvre : le planning semaine ignore samedi/dimanche.
    presence_date = _next_weekday(date.today()).isoformat()
    morning = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_a,
            "is_present": True,
            "period": "morning",
        },
        headers=admin_headers,
    )
    assert morning.status_code == 200, morning.text
    assert morning.json()["room_id"] == room_a
    assert morning.json()["period"] == "morning"

    afternoon = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_b,
            "is_present": True,
            "period": "afternoon",
        },
        headers=admin_headers,
    )
    assert afternoon.status_code == 200, afternoon.text
    assert afternoon.json()["room_id"] == room_b
    assert afternoon.json()["period"] == "afternoon"

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}",
        headers=admin_headers,
    )
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert any(p["is_mine"] and p["period"] == "morning" for p in room_a_day["presences"])
    assert any(p["is_mine"] and p["period"] == "afternoon" for p in room_b_day["presences"])


@pytest.mark.asyncio
async def test_agenda_conflict_rules(client, admin_headers):
    room_a, room_b = await _setup_bureau_rooms(
        client, admin_headers, names=("Conf A", "Conf B")
    )
    presence_date = date.today().isoformat()

    morning = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_a,
            "is_present": True,
            "period": "morning",
        },
        headers=admin_headers,
    )
    assert morning.status_code == 200, morning.text

    # Same period in another room is forbidden
    morning_b = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_b,
            "is_present": True,
            "period": "morning",
        },
        headers=admin_headers,
    )
    assert morning_b.status_code == 409, morning_b.text

    # Opposite half-day is allowed
    afternoon_b = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_b,
            "is_present": True,
            "period": "afternoon",
            "needs_meal": True,
            "needs_workstation": True,
        },
        headers=admin_headers,
    )
    assert afternoon_b.status_code == 200, afternoon_b.text

    # Meal already used in room B
    meal_a = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_a,
            "is_present": True,
            "period": "morning",
            "needs_meal": True,
        },
        headers=admin_headers,
    )
    assert meal_a.status_code == 409, meal_a.text

    # Workstation in both rooms is allowed (update room A)
    desk_a = await client.patch(
        f"/agenda/presences/{morning.json()['id']}",
        json={"needs_workstation": True},
        headers=admin_headers,
    )
    assert desk_a.status_code == 200, desk_a.text
    assert desk_a.json()["needs_workstation"] is True


@pytest.mark.asyncio
async def test_agenda_month_view(client, admin_headers):
    await _setup_bureau_room(client, admin_headers)
    today = date.today().isoformat()

    month = await client.get(f"/agenda/planning?view=month&anchor={today}", headers=admin_headers)
    assert month.status_code == 200
    assert month.json()["view"] == "month"
    assert len(month.json()["days"]) >= 28

    quarter = await client.get(f"/agenda/planning?view=quarter&anchor={today}", headers=admin_headers)
    assert quarter.status_code == 422


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


async def _create_user_with_permissions(db_session, username, permission_codes):
    user = await create_user(db_session, {
        "username": username,
        "email": f"{username}@example.com",
        "password": "password123",
        "is_active": True,
        "role": UserRole.USER,
        "source": "local",
    })
    permissions = (await db_session.execute(
        select(PermissionModel).where(PermissionModel.code.in_(list(permission_codes)))
    )).scalars().all()
    assert permissions, "permissions RBAC manquantes"
    role = Role(code=f"role-{username}", name=f"Rôle {username}")
    db_session.add(role)
    await db_session.flush()
    db_session.add_all([RolePermission(role_id=role.id, permission_id=permission.id) for permission in permissions])
    db_session.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    await db_session.commit()
    return user


async def _login_headers(client, username):
    response = await client.post("/auth/login", json={"username": username, "password": "password123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.cookies.get('access_token')}"}


@pytest.mark.asyncio
async def test_upsert_presence_for_another_user_requires_manage(client, db_session, admin_headers):
    room_id = await _setup_bureau_room(client, admin_headers)
    await _create_user_with_permissions(db_session, "agenda-reader", ["agenda.access"])
    target = await _create_user_with_permissions(db_session, "agenda-target", ["agenda.access"])
    headers = await _login_headers(client, "agenda-reader")
    payload = {
        "presence_date": _next_weekday(date.today()).isoformat(),
        "room_id": room_id,
        "is_present": True,
        "period": "morning",
    }

    forbidden = await client.post(
        "/agenda/presences", json={**payload, "user_id": target.id}, headers=headers
    )
    assert forbidden.status_code == 403, forbidden.text

    own = await client.post("/agenda/presences", json=payload, headers=headers)
    assert own.status_code == 200, own.text
    assert own.json()["user_id"] is not None


@pytest.mark.asyncio
async def test_manager_upserts_presence_for_another_user(client, db_session, admin_headers):
    room_id = await _setup_bureau_room(client, admin_headers)
    target = await _create_user_with_permissions(db_session, "agenda-target-managed", ["agenda.access"])
    presence_date = _next_weekday(date.today()).isoformat()

    created = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_id,
            "is_present": True,
            "period": "morning",
            "user_id": target.id,
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["user_id"] == target.id

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers
    )
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    person = next(
        p for p in room_day["presences"]
        if p["person_type"] == "user" and p["person_id"] == target.id
    )
    assert person["is_mine"] is False
    assert person["period"] == "morning"


@pytest.mark.asyncio
async def test_update_presence_can_move_room(client, admin_headers):
    room_a, room_b = await _setup_bureau_rooms(client, admin_headers, names=("Move A", "Move B"))
    presence_date = _next_weekday(date.today()).isoformat()

    created = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    presence_id = created.json()["id"]

    moved = await client.patch(
        f"/agenda/presences/{presence_id}", json={"room_id": room_b}, headers=admin_headers
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["room_id"] == room_b

    other = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    assert other.status_code == 200, other.text

    # Deux présences du même jour ne peuvent pas se rejoindre dans le même local
    clash = await client.patch(
        f"/agenda/presences/{presence_id}", json={"room_id": room_a}, headers=admin_headers
    )
    assert clash.status_code == 409, clash.text

    # Période en conflit dans un autre local
    conflict = await client.patch(
        f"/agenda/presences/{other.json()['id']}",
        json={"room_id": room_b, "period": "morning"},
        headers=admin_headers,
    )
    assert conflict.status_code == 409, conflict.text


@pytest.mark.asyncio
async def test_update_presence_conflict_uses_presence_owner(client, db_session, admin_headers):
    room_editor, room_owner, room_free = await _setup_bureau_rooms(
        client, admin_headers, names=("Conf Editor", "Conf Owner", "Conf Free")
    )
    presence_date = _next_weekday(date.today()).isoformat()
    target = await _create_user_with_permissions(db_session, "agenda-owned", ["agenda.access"])

    admin_presence = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_editor, "is_present": True, "period": "full"},
        headers=admin_headers,
    )
    assert admin_presence.status_code == 200, admin_presence.text

    target_presence = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_owner,
            "is_present": True,
            "period": "morning",
            "user_id": target.id,
        },
        headers=admin_headers,
    )
    assert target_presence.status_code == 200, target_presence.text

    # Le gestionnaire n'a aucune inscription sur cet après-midi : la mise à jour doit passer
    updated = await client.patch(
        f"/agenda/presences/{target_presence.json()['id']}",
        json={"period": "afternoon", "room_id": room_free},
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["period"] == "afternoon"
    assert updated.json()["room_id"] == room_free


@pytest.mark.asyncio
async def test_agenda_planning_categorized_by_group_hierarchy(client, db_session, admin_headers):
    # Deux groupes imbriques (hiérarchie AD), description affichee a la
    # place du nom.
    parent = Group(
        code="agenda-group-parent",
        name="GG_BUREAU",
        description="Bureau principal",
        source="local",
    )
    child = Group(
        code="agenda-group-child",
        name="GG_BUREAU_INT",
        description="Intendance",
        source="local",
    )
    db_session.add(parent)
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(parent)
    await db_session.refresh(child)
    db_session.add(GroupGroup(parent_group_id=parent.id, child_group_id=child.id))

    only_parent = await _create_user_with_permissions(db_session, "agenda-mem-parent", ["agenda.access"])
    only_child = await _create_user_with_permissions(db_session, "agenda-mem-child", ["agenda.access"])
    both = await _create_user_with_permissions(db_session, "agenda-mem-both", ["agenda.access"])
    for user, group in (
        (only_parent, parent),
        (only_child, child),
        (both, parent),
        (both, child),
    ):
        db_session.add(UserGroup(user_id=user.id, group_id=group.id))
    await db_session.commit()

    saved = await client.put(
        "/agenda/settings",
        json={"planning_group_ids": [child.id, parent.id]},
        headers=admin_headers,
    )
    assert saved.status_code == 200, saved.text

    # La description (pas le nom) est proposee dans les parametres.
    groups = await client.get("/agenda/groups", headers=admin_headers)
    assert groups.status_code == 200, groups.text
    options = {g["id"]: g for g in groups.json()["groups"]}
    assert options[parent.id]["description"] == "Bureau principal"
    assert options[child.id]["description"] == "Intendance"

    presence_date = _next_weekday(date.today()).isoformat()
    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers
    )
    assert planning.status_code == 200, planning.text
    payload = planning.json()

    # Ordre : arbre (parent puis enfant) et libelle = description.
    assert [g["name"] for g in payload["planning_groups"]] == ["GG_BUREAU", "GG_BUREAU_INT"]
    assert payload["planning_groups"][0]["description"] == "Bureau principal"
    assert payload["planning_groups"][0]["depth"] == 0
    assert payload["planning_groups"][0]["parent_id"] is None
    assert payload["planning_groups"][1]["depth"] == 1
    assert payload["planning_groups"][1]["parent_id"] == parent.id

    # Une seule ligne par personne, rattachee au premier groupe de l'ordre.
    group_by_person = {p["person_id"]: p["group_id"] for p in payload["planning_people"]}
    assert group_by_person[only_parent.id] == parent.id
    assert group_by_person[only_child.id] == child.id
    assert group_by_person[both.id] == parent.id


@pytest.mark.asyncio
async def test_agenda_settings_and_group_members_in_planning(client, db_session, admin_headers):
    settings = await client.get("/agenda/settings", headers=admin_headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()["planning_group_ids"] == []

    member = await _create_user_with_permissions(db_session, "agenda-group-member", ["agenda.access"])
    # Définir prénom/nom pour le format d'affichage "NOM Prénom"
    member.first_name = "Jean"
    member.last_name = "Dupont"
    await db_session.commit()
    group = Group(code="agenda-planning-group", name="Groupe Planning Agenda")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    db_session.add(UserGroup(user_id=member.id, group_id=group.id))
    await db_session.commit()

    presence_date = _next_weekday(date.today()).isoformat()
    week_url = f"/agenda/planning?view=week&anchor={presence_date}"

    groups = await client.get("/agenda/groups", headers=admin_headers)
    assert groups.status_code == 200, groups.text
    group_ids = [g["id"] for g in groups.json()["groups"]]
    assert group.id in group_ids

    # Aucun groupe coche : le membre sans presence n'apparait pas.
    planning = await client.get(week_url, headers=admin_headers)
    assert planning.status_code == 200, planning.text
    names = [p["name"] for p in planning.json()["planning_people"]]
    assert member.full_name not in names

    saved = await client.put(
        "/agenda/settings",
        json={"planning_group_ids": [group.id, group.id, 999999]},
        headers=admin_headers,
    )
    assert saved.status_code == 200, saved.text
    # doublons et groupes inconnus nettoyes
    assert saved.json()["planning_group_ids"] == [group.id]

    # Le membre est liste sans presence renseignee, rattache a son groupe.
    planning = await client.get(week_url, headers=admin_headers)
    people = planning.json()["planning_people"]
    expected_name = f"{member.last_name.upper()} {member.first_name}".strip()
    assert {"person_id": member.id, "name": expected_name, "group_id": group.id, "last_name": "Dupont", "first_name": "Jean"} in people

    # Meme avec une presence, le membre reste rattache a son groupe :
    # le front fusionne cette ligne avec celle creee depuis la presence.
    room_id = await _setup_bureau_room(client, admin_headers)
    created = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_id,
            "is_present": True,
            "period": "full",
            "user_id": member.id,
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text

    planning = await client.get(week_url, headers=admin_headers)
    people = planning.json()["planning_people"]
    expected_name = f"{member.last_name.upper()} {member.first_name}".strip()
    assert {"person_id": member.id, "name": expected_name, "group_id": group.id, "last_name": "Dupont", "first_name": "Jean"} in people

    # Groupes inexistants ignores lors de l'enregistrement.
    saved = await client.put(
        "/agenda/settings",
        json={"planning_group_ids": [424242]},
        headers=admin_headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["planning_group_ids"] == []


@pytest.mark.asyncio
async def test_agenda_settings_requires_manage(client, db_session):
    # agenda.access ne suffit pas : la configuration est reservee aux gestionnaires.
    await _create_user_with_permissions(db_session, "agenda-reader-settings", ["agenda.access"])
    headers = await _login_headers(client, "agenda-reader-settings")

    settings = await client.get("/agenda/settings", headers=headers)
    assert settings.status_code == 403
    saved = await client.put("/agenda/settings", json={"planning_group_ids": []}, headers=headers)
    assert saved.status_code == 403
    groups = await client.get("/agenda/groups", headers=headers)
    assert groups.status_code == 403


@pytest.mark.asyncio
async def test_agenda_occupancy_not_double_counted(client, admin_headers, db_session, admin_user):
    """Une personne inscrite et presente en occupancy le meme jour compte une fois.

    Le planning livre les occupants en « NOM Prenom » alors que les presences
    livrent « Prenom Nom » : la comparaison doit ignorer l'ordre des mots.
    """
    from datetime import datetime as _datetime

    from app.models.housing import Housing, Occupancy, Occupant

    admin_user.first_name = "Caroline"
    admin_user.last_name = "DESMERY"
    await db_session.commit()

    room_id = await _setup_bureau_room(client, admin_headers, name="Bureau Dedup")
    presence_date = _next_weekday(date.today())

    created = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date.isoformat(),
            "room_id": room_id,
            "is_present": True,
            "period": "morning",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text

    housing = Housing(room_id=room_id)
    db_session.add(housing)
    await db_session.flush()

    day_start = _datetime(presence_date.year, presence_date.month, presence_date.day)
    db_session.add(
        Occupancy(
            housing_id=housing.id,
            status="confirmed",
            arrival_date=day_start,
            departure_date=day_start + timedelta(days=1),
            agenda_room_id=room_id,
            occupants=[Occupant(first_name="Caroline", last_name="DESMERY")],
        )
    )
    await db_session.commit()

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date.isoformat()}",
        headers=admin_headers,
    )
    assert planning.status_code == 200, planning.text
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date.isoformat())
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)

    assert day["total_present"] == 1, day
    assert room_day["present_count"] == 1, room_day
    assert [p["person_type"] for p in room_day["presences"]] == ["user"]
    assert not any(p["person_type"] == "occupant" for p in day["integrated"])
