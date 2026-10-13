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
async def test_agenda_second_local_replaces_first(client, admin_headers):
    """Même période dans un autre local → migration.
    Demi-journée opposée dans un autre local → cohabitation (matin A / après-midi B)."""
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

    # Après-midi dans l'autre local : les deux demi-journées cohabitent
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
    # Matin dans A conservé, après-midi ajouté dans B
    assert room_a_day["present_count"] == 1
    assert any(p["is_mine"] and p["period"] == "morning" for p in room_a_day["presences"])
    assert room_b_day["present_count"] == 1
    assert any(p["is_mine"] and p["period"] == "afternoon" for p in room_b_day["presences"])
    assert day["total_present"] == 2

    # Mais si on remet un matin dans B : le matin de A est retiré
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
    assert morning_b.status_code == 200, morning_b.text

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}",
        headers=admin_headers,
    )
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["present_count"] == 0
    assert room_a_day["presences"] == []
    # B: la période demandée remplace la précédente (aucune fusion)
    assert room_b_day["present_count"] == 1
    mine_b = next(p for p in room_b_day["presences"] if p["is_mine"])
    assert mine_b["period"] == "morning"
    assert day["total_present"] == 1


@pytest.mark.asyncio
async def test_agenda_conflict_rules(client, admin_headers):
    """Un seul local par demi-journée : même période dans un autre local → retrait auto.
    Demi-journée opposée dans un autre local → autorisée (les deux cohabitent)."""
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

    # Même période dans un autre local : le premier est retiré automatiquement
    morning_b = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_b,
            "is_present": True,
            "period": "morning",
            "needs_meal": True,
            "needs_workstation": True,
        },
        headers=admin_headers,
    )
    assert morning_b.status_code == 200, morning_b.text

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers
    )
    assert planning.status_code == 200, planning.text
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day_a = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_day_b = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_day_a["present_count"] == 0, room_day_a
    assert room_day_a["presences"] == []
    assert room_day_b["present_count"] == 1, room_day_b
    mine_b = next(p for p in room_day_b["presences"] if p["is_mine"])
    assert mine_b["period"] == "morning"
    assert mine_b["needs_meal"] is True
    assert mine_b["needs_workstation"] is True
    assert day["total_present"] == 1

    # Demi-journée opposée dans un autre local : le matin dans B est retiré, après-midi créé dans A avec poste
    afternoon_c = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_a,  # retour dans A, mais après-midi
            "is_present": True,
            "period": "afternoon",
        },
        headers=admin_headers,
    )
    assert afternoon_c.status_code == 200, afternoon_c.text

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers
    )
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day_b = next(r for r in day["rooms"] if r["room_id"] == room_b)
    room_day_a = next(r for r in day["rooms"] if r["room_id"] == room_a)
    # Demi-journée opposée : le matin de B reste, l'après-midi s'ajoute dans A
    assert room_day_b["present_count"] == 1, room_day_b  # matin conservé dans B
    mine_b_after = next(p for p in room_day_b["presences"] if p["is_mine"])
    assert mine_b_after["period"] == "morning"
    assert room_day_a["present_count"] == 1, room_day_a  # après-midi créé dans A
    mine_a = next(p for p in room_day_a["presences"] if p["is_mine"])
    assert mine_a["period"] == "afternoon"
    # Pas de préférence « poste » : le poste n'est plus auto-coché
    assert mine_a["needs_workstation"] is False
    assert day["total_present"] == 2

    # Le poste reste modifiable sur la présence active
    desk_a = await client.patch(
        f"/agenda/presences/{afternoon_c.json()['id']}",
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

    # Un seul local par jour : déplacer la présence du matin de B vers A fusionne en journée complète
    clash = await client.patch(
        f"/agenda/presences/{presence_id}", json={"room_id": room_a}, headers=admin_headers
    )
    assert clash.status_code == 200, clash.text
    assert clash.json()["room_id"] == room_a
    assert clash.json()["period"] == "full"

    # Changer la période de l'autre présence (après-midi dans A) vers matin dans B
    conflict = await client.patch(
        f"/agenda/presences/{other.json()['id']}",
        json={"room_id": room_b, "period": "morning"},
        headers=admin_headers,
    )
    assert conflict.status_code == 200, conflict.text
    assert conflict.json()["room_id"] == room_b
    assert conflict.json()["period"] == "morning"


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



@pytest.mark.asyncio
async def test_remote_presence_is_row_without_room(client, admin_headers):
    """Télétravail : ligne sans local, comptée dans le jour mais pas dans les locaux."""
    room_id = await _setup_bureau_room(client, admin_headers, name="Télétravail Bureau")
    presence_date = _next_weekday(date.today()).isoformat()

    created = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_id,  # ignoré en télétravail
            "is_present": True,
            "period": "full",
            "is_remote": True,
            "needs_workstation": True,
            "needs_meal": True,
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["is_remote"] is True
    assert body["room_id"] is None
    assert body["needs_workstation"] is False
    assert body["needs_meal"] is False
    presence_id = body["id"]

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers
    )
    assert planning.status_code == 200, planning.text
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    # Compté dans le total du jour, sans poste
    assert day["total_present"] == 1, day
    assert day["total_workstations"] == 0
    # Pas de présence dans le local, compteurs locaux à zéro
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 0
    assert room_day["workstation_count"] == 0
    assert room_day["presences"] == []
    # Ligne télétravail présente
    remote = next(p for p in day["remote"] if p["is_mine"])
    assert remote["is_remote"] is True
    assert remote["room_id"] is None
    assert remote["period"] == "full"

    # PATCH télétravail : force poste/repas à False
    patched = await client.patch(
        f"/agenda/presences/{presence_id}",
        json={"is_remote": True, "needs_workstation": True, "needs_meal": True},
        headers=admin_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_remote"] is True
    assert patched.json()["room_id"] is None
    assert patched.json()["needs_workstation"] is False
    assert patched.json()["needs_meal"] is False


@pytest.mark.asyncio
async def test_remote_half_day_excludes_local_half(client, admin_headers):
    """Télétravail matin : la présence locale est réduite à l'après-midi (repas gardé)."""
    room_id = await _setup_bureau_room(client, admin_headers, name="Bureau Exclu")
    presence_date = _next_weekday(date.today()).isoformat()

    local = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_id,
            "is_present": True,
            "period": "full",
            "needs_workstation": True,
            "needs_meal": True,
        },
        headers=admin_headers,
    )
    assert local.status_code == 200, local.text

    remote = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": None,
            "is_present": True,
            "period": "morning",
            "is_remote": True,
        },
        headers=admin_headers,
    )
    assert remote.status_code == 200, remote.text
    assert remote.json()["period"] == "morning"
    assert remote.json()["room_id"] is None

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers
    )
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    # La présence locale n'est pas perdue : réduite à l'après-midi, repas gardé
    assert room_day["present_count"] == 1
    mine = next(p for p in room_day["presences"] if p["is_mine"])
    assert mine["period"] == "afternoon"
    assert mine["needs_meal"] is True
    assert mine["needs_workstation"] is True
    remote_mine = next(p for p in day["remote"] if p["is_mine"])
    assert remote_mine["period"] == "morning"
    assert day["total_present"] == 2

    # Télétravail journée entière : la présence locale est retirée
    full = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": None,
            "is_present": True,
            "period": "full",
            "is_remote": True,
        },
        headers=admin_headers,
    )
    assert full.status_code == 200, full.text

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers
    )
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 0
    assert room_day["presences"] == []
    remote_mine = next(p for p in day["remote"] if p["is_mine"])
    assert remote_mine["period"] == "full"
    assert day["total_present"] == 1


@pytest.mark.asyncio
async def test_local_presence_removes_overlapping_remote(client, admin_headers):
    """Case locale cochée : le télétravail de la même demi-journée est retiré."""
    room_id = await _setup_bureau_room(client, admin_headers, name="Bureau Local")
    presence_date = _next_weekday(date.today()).isoformat()

    remote = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": None,
            "is_present": True,
            "period": "full",
            "is_remote": True,
        },
        headers=admin_headers,
    )
    assert remote.status_code == 200, remote.text
    remote_id = remote.json()["id"]

    local = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_id,
            "is_present": True,
            "period": "morning",
        },
        headers=admin_headers,
    )
    assert local.status_code == 200, local.text
    assert local.json()["period"] == "morning"

    planning = await client.get(
        f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers
    )
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    # Retrait automatique : le télétravail est réduit à l'après-midi
    remote_mine = next(p for p in day["remote"] if p["is_mine"])
    assert remote_mine["period"] == "afternoon"
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 1
    mine = next(p for p in room_day["presences"] if p["is_mine"])
    assert mine["period"] == "morning"
    assert day["total_present"] == 2

    # Une ligne télétravail (sans local) ne peut pas redevenir locale
    back = await client.patch(
        f"/agenda/presences/{remote_id}",
        json={"is_remote": False},
        headers=admin_headers,
    )
    assert back.status_code == 409, back.text

@pytest.mark.asyncio
async def test_extend_morning_to_full_removes_afternoon_in_other_room(client, admin_headers):
    """Morning in A, afternoon in B -> extend A to full should remove afternoon from B"""
    room_a, room_b = await _setup_bureau_rooms(client, admin_headers, names=("Bureau A", "Bureau B"))
    
    presence_date = _next_weekday(date.today()).isoformat()
    
    # Morning in A
    morning = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert morning.status_code == 200, morning.text
    assert morning.json()["period"] == "morning"
    
    # Afternoon in B
    afternoon = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_b, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    assert afternoon.status_code == 200, afternoon.text
    assert afternoon.json()["period"] == "afternoon"
    
    # Check initial state
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["present_count"] == 1
    assert any(p["period"] == "morning" for p in room_a_day["presences"])
    assert room_b_day["present_count"] == 1
    assert any(p["period"] == "afternoon" for p in room_b_day["presences"])
    
    # Extend room A to full
    full = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "full"},
        headers=admin_headers,
    )
    print(f"Extend to full status: {full.status_code}, text: {full.text}")
    assert full.status_code == 200, full.text
    
    # Check final state
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    
    print(f"Room A: {room_a_day}")
    print(f"Room B: {room_b_day}")
    
    # Room A should have full
    assert room_a_day["present_count"] == 1
    assert any(p["period"] == "full" for p in room_a_day["presences"])
    
    # Room B should have NO presences (afternoon removed)
    assert room_b_day["present_count"] == 0, f"Room B should be empty but has: {room_b_day['presences']}"

@pytest.mark.asyncio
async def test_create_afternoon_in_a_removes_afternoon_in_b(client, admin_headers):
    """Morning in A, afternoon in B -> create afternoon in A should remove afternoon from B"""
    room_a, room_b = await _setup_bureau_rooms(client, admin_headers, names=("Bureau A", "Bureau B"))
    
    presence_date = _next_weekday(date.today()).isoformat()
    
    # Morning in A
    await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    
    # Afternoon in B
    await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_b, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    
    # Check initial state
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_b_day["present_count"] == 1
    assert any(p["period"] == "afternoon" for p in room_b_day["presences"])
    
    # Create afternoon in A (should remove afternoon from B)
    afternoon_a = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    print(f"Create afternoon in A status: {afternoon_a.status_code}, text: {afternoon_a.text}")
    assert afternoon_a.status_code == 200, afternoon_a.text
    
    # Check final state
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    
    print(f"Room A: {room_a_day}")
    print(f"Room B: {room_b_day}")
    
    # Room A: l'après-midi demandé remplace le matin (aucune fusion)
    assert room_a_day["present_count"] == 1
    assert any(p["period"] == "afternoon" for p in room_a_day["presences"])
    
    # Room B should have NO presences (afternoon removed)
    assert room_b_day["present_count"] == 0, f"Room B should be empty but has: {room_b_day['presences']}"

@pytest.mark.asyncio
async def test_create_afternoon_in_same_room_replaces_morning(client, admin_headers):
    """Morning in A -> create afternoon in A replaces it (pas de fusion)"""
    room_a, room_b = await _setup_bureau_rooms(client, admin_headers, names=("Bureau A", "Bureau B"))
    
    presence_date = _next_weekday(date.today()).isoformat()
    
    # Morning in A
    await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    
    # Check: morning exists in A
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    assert room_a_day["present_count"] == 1
    assert any(p["period"] == "morning" for p in room_a_day["presences"])
    
    # Create afternoon in SAME room A (remplace le matin, pas de fusion)
    await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    
    # Check: l'après-midi remplace le matin
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    print(f"Room A after adding afternoon: {room_a_day}")
    
    assert room_a_day["present_count"] == 1
    assert any(p["period"] == "afternoon" for p in room_a_day["presences"])


@pytest.mark.asyncio
async def test_resubscribe_half_day_after_cancel_keeps_requested_period(client, admin_headers):
    """Re-inscription apres annulation : la periode obsolene ne doit pas fusionner.

    Une presence desactivee (is_present=False) conserve sa periode en base.
    Clic sur « Matin » apres une annulation ne doit PAS cocher l'apres-midi.
    """
    room_id = await _setup_bureau_room(client, admin_headers)
    presence_date = _next_weekday(date.today()).isoformat()

    afternoon = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_id, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    assert afternoon.status_code == 200, afternoon.text

    cancelled = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_id, "is_present": False},
        headers=admin_headers,
    )
    assert cancelled.status_code == 200, cancelled.text

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 0

    morning = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_id, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert morning.status_code == 200, morning.text
    assert morning.json()["period"] == "morning"


@pytest.mark.asyncio
async def test_half_day_cells_toggle_independently(client, admin_headers):
    """Coche/decoche individuelles : aucune fusion matin/apres-midi.

    Reproduit les envois de la page « Ma présence » :
    - cocher une seule demi-journée ;
    - cocher les deux (journee complete) ;
    - decocher une demi-journée d'une journee complete ;
    - decocher la derniere demi-journée puis recocher une seule.
    """
    room_id = await _setup_bureau_room(client, admin_headers)
    presence_date = _next_weekday(date.today()).isoformat()

    async def upsert(**kwargs):
        payload = {"presence_date": presence_date, "room_id": room_id, **kwargs}
        resp = await client.post("/agenda/presences", json=payload, headers=admin_headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    # Cocher « Matin » seul
    assert (await upsert(is_present=True, period="morning"))["period"] == "morning"
    # Cocher aussi l'après-midi (le front envoie 'full' quand les deux sont coches)
    assert (await upsert(is_present=True, period="full"))["period"] == "full"
    # Decocher « Matin » : le front envoie la demi-journée restante
    assert (await upsert(is_present=True, period="afternoon"))["period"] == "afternoon"
    # Decocher « Après-midi » : dernière demi-journée -> absence
    assert (await upsert(is_present=False))["is_present"] is False
    # Recoquer « Après-midi » seul
    assert (await upsert(is_present=True, period="afternoon"))["period"] == "afternoon"


@pytest.mark.asyncio
async def test_remote_half_day_completion_unchecks_local_half(client, admin_headers):
    """Completer la journee de teletravail retire la demi-journee locale.

    L'interface complete la journee via PATCH {period: 'full'} : la presence
    locale qui chevauche doit etre retiree (cocher un teletravail decoche la
    demi-journee des locaux).
    """
    room_id = await _setup_bureau_room(client, admin_headers)
    presence_date = _next_weekday(date.today()).isoformat()

    local = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_id, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert local.status_code == 200, local.text

    # Teletravail l'apres-midi : coexiste avec le matin sur site
    remote = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "is_present": True, "period": "afternoon", "is_remote": True},
        headers=admin_headers,
    )
    assert remote.status_code == 200, remote.text

    # L'utilisateur coche aussi le teletravail du matin -> PATCH 'full'
    patched = await client.patch(
        f"/agenda/presences/{remote.json()['id']}", json={"period": "full"}, headers=admin_headers
    )
    assert patched.status_code == 200, patched.text

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    # Le matin sur site est retire
    assert room_day["present_count"] == 0
    assert room_day["presences"] == []
    remote_mine = next(p for p in day["remote"] if p["is_mine"])
    assert remote_mine["period"] == "full"


@pytest.mark.asyncio
async def test_full_remote_drops_local_meal_and_desk(client, admin_headers):
    """Teletravail matin + apres-midi : la presence locale (repas/poste) part."""
    room_id = await _setup_bureau_room(client, admin_headers)
    presence_date = _next_weekday(date.today()).isoformat()

    local = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_id,
            "is_present": True,
            "period": "full",
            "needs_workstation": True,
            "needs_meal": True,
        },
        headers=admin_headers,
    )
    assert local.status_code == 200, local.text

    # Teletravail matin : locale reduite a l'apres-midi, repas/poste conserves
    remote = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "is_present": True, "period": "morning", "is_remote": True},
        headers=admin_headers,
    )
    assert remote.status_code == 200, remote.text
    assert remote.json()["needs_workstation"] is False
    assert remote.json()["needs_meal"] is False

    # Teletravail apres-midi (PATCH comme l'interface) : plus rien sur site
    patched = await client.patch(
        f"/agenda/presences/{remote.json()['id']}", json={"period": "full"}, headers=admin_headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["needs_workstation"] is False
    assert patched.json()["needs_meal"] is False

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_day = next(r for r in day["rooms"] if r["room_id"] == room_id)
    assert room_day["present_count"] == 0
    assert room_day["presences"] == []
    assert room_day["workstation_count"] == 0


@pytest.mark.asyncio
async def test_past_date_registration_allowed(client, admin_headers):
    """Plus de garde-fou date passee : l'inscription sur une date passee reussit."""
    room_id = await _setup_bureau_room(client, admin_headers)

    past = date.today() - timedelta(days=1)
    while past.weekday() >= 5:
        past -= timedelta(days=1)
    assert past < date.today()

    resp = await client.post(
        "/agenda/presences",
        json={"presence_date": past.isoformat(), "room_id": room_id, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["period"] == "morning"


@pytest.mark.asyncio
async def test_clicking_other_room_migrates_registration(client, admin_headers):
    """Clic sur Matin dans un autre bureau : l'inscription migre la-bas.

    Meme demi-journee dans un autre local : l'ancien local est vide, le
    nouveau garde exactement la demi-journee demandee (pas de fusion).
    """
    room_ids = await _setup_bureau_rooms(client, admin_headers, names=("Bureau A", "Bureau B"))
    room_a, room_b = room_ids
    presence_date = _next_weekday(date.today()).isoformat()

    first = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert first.status_code == 200, first.text

    moved = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_b, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["period"] == "morning"

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["present_count"] == 0
    assert room_a_day["presences"] == []
    assert room_b_day["present_count"] == 1
    assert room_b_day["presences"][0]["period"] == "morning"


@pytest.mark.asyncio
async def test_split_half_day_across_locals(client, admin_headers):
    """Matin dans un local, apres-midi dans un autre : les deux cohabitent.

    Une journee complete dans A puis un apres-midi clique dans B est reduite
    a son matin dans A. Le teletravail (par demi-journee ou complet) retire
    la ou les presences locales qui chevauchent.
    """
    room_ids = await _setup_bureau_rooms(client, admin_headers, names=("Bureau A", "Bureau B"))
    room_a, room_b = room_ids
    presence_date = _next_weekday(date.today()).isoformat()

    full = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "full"},
        headers=admin_headers,
    )
    assert full.status_code == 200, full.text

    # Apres-midi clique dans B : A n'est plus qu'un matin
    afternoon_b = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_b, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    assert afternoon_b.status_code == 200, afternoon_b.text

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["present_count"] == 1
    assert room_a_day["presences"][0]["period"] == "morning"
    assert room_b_day["present_count"] == 1
    assert room_b_day["presences"][0]["period"] == "afternoon"
    assert day["total_present"] == 2

    # Teletravail l'apres-midi : seule la presence locale de l'apres-midi part
    remote = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "is_present": True, "period": "afternoon", "is_remote": True},
        headers=admin_headers,
    )
    assert remote.status_code == 200, remote.text

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["present_count"] == 1  # matin conserve
    assert room_b_day["present_count"] == 0  # apres-midi locale retire

    # Teletravail complet : plus rien sur site
    patched = await client.patch(
        f"/agenda/presences/{remote.json()['id']}", json={"period": "full"}, headers=admin_headers
    )
    assert patched.status_code == 200, patched.text

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["present_count"] == 0
    assert room_b_day["present_count"] == 0
    assert next(p for p in day["remote"] if p["is_mine"])["period"] == "full"


@pytest.mark.asyncio
async def test_meal_migrates_to_clicked_local(client, admin_headers):
    """Un seul repas par jour : cocher le repas dans un autre local migre le repas.

    L'inscription dans l'autre local est acceptee (pas d'erreur) et le repas
    quitte l'ancien local. Le decocher ne touche pas l'autre local.
    """
    room_ids = await _setup_bureau_rooms(client, admin_headers, names=("Bureau A", "Bureau B"))
    room_a, room_b = room_ids
    presence_date = _next_weekday(date.today()).isoformat()

    first = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_a,
            "is_present": True,
            "period": "full",
            "needs_meal": True,
            "needs_workstation": True,
        },
        headers=admin_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["needs_meal"] is True

    moved = await client.post(
        "/agenda/presences",
        json={
            "presence_date": presence_date,
            "room_id": room_b,
            "is_present": True,
            "period": "afternoon",
            "needs_meal": True,
        },
        headers=admin_headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["needs_meal"] is True

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    # A est reduite a son matin et a perdu son repas
    assert room_a_day["present_count"] == 1
    assert room_a_day["presences"][0]["period"] == "morning"
    assert room_a_day["presences"][0]["needs_meal"] is False
    assert room_b_day["present_count"] == 1
    assert room_b_day["presences"][0]["needs_meal"] is True

    # Le repas revient dans A (deuxieme direction)
    back = await client.post(
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
    assert back.status_code == 200, back.text

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["presences"][0]["needs_meal"] is True
    assert room_b_day["present_count"] == 1
    assert room_b_day["presences"][0]["needs_meal"] is False

    # Decocher le repas dans A ne touche pas B
    uncheck = await client.patch(
        f"/agenda/presences/{room_a_day['presences'][0]['id']}",
        json={"needs_meal": False},
        headers=admin_headers,
    )
    assert uncheck.status_code == 200, uncheck.text

    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["presences"][0]["needs_meal"] is False
    assert room_b_day["presences"][0]["needs_meal"] is False


@pytest.mark.asyncio
async def test_user_preference_defaults_workstation(client, admin_headers):
    """Préférence « poste » : auto-coché à l'inscription si active, sinon non.

    Désactivée par défaut, réglée depuis la page Paramètres (PATCH /auth/me).
    """
    room_ids = await _setup_bureau_rooms(client, admin_headers, names=("Bureau A", "Bureau B"))
    room_a, room_b = room_ids
    presence_date = _next_weekday(date.today()).isoformat()

    # Par défaut : la préférence est inactive, le poste n'est pas auto-coché
    first = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["needs_workstation"] is False

    # Activation de la préférence depuis les paramètres
    pref = await client.patch(
        "/auth/me", json={"default_needs_workstation": True}, headers=admin_headers
    )
    assert pref.status_code == 200, pref.text
    assert pref.json()["default_needs_workstation"] is True

    # Nouvelle inscription : le poste est auto-coché
    second = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_b, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["needs_workstation"] is True

    # Désactivation : les inscriptions suivantes repartent sans poste
    off = await client.patch(
        "/auth/me", json={"default_needs_workstation": False}, headers=admin_headers
    )
    assert off.status_code == 200, off.text
    assert off.json()["default_needs_workstation"] is False

    other_day = _next_weekday(date.today() + timedelta(days=7)).isoformat()
    third = await client.post(
        "/agenda/presences",
        json={"presence_date": other_day, "room_id": room_a, "is_present": True, "period": "full"},
        headers=admin_headers,
    )
    assert third.status_code == 200, third.text
    assert third.json()["needs_workstation"] is False
