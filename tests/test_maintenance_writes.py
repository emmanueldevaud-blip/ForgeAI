"""Tests de non-régression des écritures du module maintenance.

Chaque écriture doit être commitée (les données doivent survivre à un
rollback de session) et les relations/colonnes serveur doivent être
rechargées avant sérialisation de la réponse (sinon 500 sur MySQL).
"""
import uuid

import pytest
from sqlalchemy import func, select

from app.models.maintenance import (
    MaintenanceContract,
    MaintenanceCost,
    MaintenanceIntervention,
    MaintenanceIntervenant,
    MaintenancePart,
    MaintenancePlan,
    MaintenancePlanChecklist,
    MaintenanceRequest,
    MaintenanceStatusHistory,
    MaintenanceWorkOrder,
    WorkOrderPart,
)


@pytest.fixture(autouse=True)
def unique_maintenance_numbers(monkeypatch):
    import app.services.maintenance as maintenance_service

    monkeypatch.setattr(
        maintenance_service,
        "_generate_request_number",
        lambda: f"DM-{uuid.uuid4().hex[:12].upper()}",
    )
    monkeypatch.setattr(
        maintenance_service,
        "_generate_work_order_number",
        lambda: f"OT-{uuid.uuid4().hex[:12].upper()}",
    )


@pytest.fixture
async def equipment_ctx(client, admin_headers):
    u = uuid.uuid4().hex[:8]
    site = await client.post(
        "/buildings/sites", json={"name": f"Site MTN {u}"}, headers=admin_headers
    )
    assert site.status_code == 201, site.text
    building = await client.post(
        "/buildings",
        json={"name": f"Bat MTN {u}", "site_id": site.json()["id"]},
        headers=admin_headers,
    )
    assert building.status_code == 201, building.text
    room = await client.post(
        "/buildings/rooms",
        json={"name": f"Local MTN {u}", "building_id": building.json()["id"]},
        headers=admin_headers,
    )
    assert room.status_code == 201, room.text
    equipment = await client.post(
        "/equipment",
        json={"name": f"Equip MTN {u}", "room_id": room.json()["id"]},
        headers=admin_headers,
    )
    assert equipment.status_code == 201, equipment.text
    return equipment.json()


@pytest.fixture
async def provider_ctx(client, admin_headers):
    r = await client.post(
        "/maintenance/providers",
        json={"name": f"Presta MTN {uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
async def part_ctx(client, admin_headers):
    r = await client.post(
        "/maintenance/parts",
        json={"reference": f"P-{uuid.uuid4().hex[:10]}", "name": "Piece MTN"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_and_update_part(client, admin_headers, db_session):
    ref = f"P-{uuid.uuid4().hex[:10]}"
    r = await client.post(
        "/maintenance/parts",
        json={"reference": ref, "name": "Filtre a air"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["created_at"]
    pid = r.json()["id"]

    r2 = await client.patch(
        f"/maintenance/parts/{pid}",
        json={"name": "Filtre HA", "unit": "pcs"},
        headers=admin_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["name"] == "Filtre HA"
    assert r2.json()["updated_at"]

    r3 = await client.get(f"/maintenance/parts/{pid}", headers=admin_headers)
    assert r3.status_code == 200
    assert r3.json()["name"] == "Filtre HA"

    await db_session.rollback()
    row = (
        await db_session.execute(
            select(MaintenancePart).where(MaintenancePart.id == pid)
        )
    ).scalar_one_or_none()
    assert row is not None, "piece non persistee en base"
    assert row.name == "Filtre HA"


async def test_create_and_update_contract(
    client, admin_headers, db_session, equipment_ctx, provider_ctx
):
    ref = f"C-{uuid.uuid4().hex[:10]}"
    r = await client.post(
        "/maintenance/contracts",
        json={
            "provider_id": provider_ctx["id"],
            "reference": ref,
            "subject": "Contrat CVC",
            "start_date": "2026-01-01",
            "equipment_ids": [equipment_ctx["id"]],
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created_at"]
    assert body["updated_at"]
    assert body["provider"] is not None, "provider non charge dans la reponse"
    assert body["provider"]["id"] == provider_ctx["id"]
    cid = body["id"]

    r2 = await client.patch(
        f"/maintenance/contracts/{cid}",
        json={"subject": "Contrat CVC renouvele", "equipment_ids": []},
        headers=admin_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["subject"] == "Contrat CVC renouvele"
    assert r2.json()["provider"]["id"] == provider_ctx["id"]
    assert r2.json()["updated_at"]

    r3 = await client.get(f"/maintenance/contracts/{cid}", headers=admin_headers)
    assert r3.status_code == 200
    assert r3.json()["subject"] == "Contrat CVC renouvele"
    assert r3.json()["equipment_count"] == 0
    assert r3.json()["provider"]["id"] == provider_ctx["id"]

    await db_session.rollback()
    row = (
        await db_session.execute(
            select(MaintenanceContract).where(MaintenanceContract.id == cid)
        )
    ).scalar_one_or_none()
    assert row is not None, "contrat non persiste en base"
    assert row.subject == "Contrat CVC renouvele"


async def test_create_and_update_request_with_status_history(
    client, admin_headers, db_session
):
    r = await client.post(
        "/maintenance/requests",
        json={"title": "Fuite d'eau local tech", "priority": "haute"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created_at"]
    assert body["updated_at"]
    assert body["number"]
    assert body["status"] == "nouvelle"
    rid = body["id"]

    r2 = await client.patch(
        f"/maintenance/requests/{rid}",
        json={"title": "Fuite corrigee", "status": "en_cours", "comment": "Plombier appele"},
        headers=admin_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["title"] == "Fuite corrigee"
    assert r2.json()["status"] == "en_cours"
    assert r2.json()["updated_at"]

    r3 = await client.get(f"/maintenance/requests/{rid}", headers=admin_headers)
    assert r3.status_code == 200
    assert r3.json()["status"] == "en_cours"

    await db_session.rollback()
    row = (
        await db_session.execute(
            select(MaintenanceRequest).where(MaintenanceRequest.id == rid)
        )
    ).scalar_one_or_none()
    assert row is not None, "demande non persistee en base"
    assert row.status == "en_cours"
    history = (
        await db_session.execute(
            select(func.count())
            .select_from(MaintenanceStatusHistory)
            .where(
                MaintenanceStatusHistory.entity_type == "request",
                MaintenanceStatusHistory.entity_id == rid,
            )
        )
    ).scalar_one()
    assert history == 2, "historique des statuts non persiste"


async def test_create_work_order_from_request(client, admin_headers, db_session):
    r = await client.post(
        "/maintenance/requests",
        json={"title": "Porte bloque"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    r2 = await client.post(
        f"/maintenance/requests/{rid}/create-work-order",
        json={"title": "Porte bloque - OT"},
        headers=admin_headers,
    )
    assert r2.status_code == 201, r2.text
    body = r2.json()
    assert body["created_at"]
    assert body["number"]
    assert body["request_id"] == rid
    wid = body["id"]

    r3 = await client.get(f"/maintenance/requests/{rid}", headers=admin_headers)
    assert r3.status_code == 200
    assert r3.json()["status"] == "a_qualifier"

    await db_session.rollback()
    wo = (
        await db_session.execute(
            select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.id == wid)
        )
    ).scalar_one_or_none()
    assert wo is not None, "OT non persiste en base"
    assert wo.request_id == rid
    req = (
        await db_session.execute(
            select(MaintenanceRequest).where(MaintenanceRequest.id == rid)
        )
    ).scalar_one()
    assert req.status == "a_qualifier"


async def test_work_order_and_children_writes(
    client, admin_headers, db_session, admin_user, equipment_ctx, part_ctx
):
    r = await client.post(
        "/maintenance/work-orders",
        json={
            "title": "Remplacement moteur",
            "equipment_id": equipment_ctx["id"],
            "priority": "haute",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created_at"]
    assert body["number"]
    wid = body["id"]

    r2 = await client.patch(
        f"/maintenance/work-orders/{wid}",
        json={"status": "en_cours", "comment": "Demarrage"},
        headers=admin_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "en_cours"
    assert r2.json()["updated_at"]
    assert r2.json()["equipment_summary"]["id"] == equipment_ctx["id"]

    r3 = await client.get(f"/maintenance/work-orders/{wid}", headers=admin_headers)
    assert r3.status_code == 200
    assert r3.json()["status"] == "en_cours"

    interv = await client.post(
        f"/maintenance/work-orders/{wid}/interventions",
        json={"description": "Diagnostic", "duration_hours": "1.5"},
        headers=admin_headers,
    )
    assert interv.status_code == 201, interv.text
    assert interv.json()["created_at"]
    assert interv.json()["intervention_date"]
    intervention_id = interv.json()["id"]

    cost = await client.post(
        f"/maintenance/work-orders/{wid}/costs",
        json={"cost_type": "pieces", "amount": "150.00"},
        headers=admin_headers,
    )
    assert cost.status_code == 201, cost.text
    assert cost.json()["created_at"]
    assert float(cost.json()["amount"]) == 150.0
    cost_id = cost.json()["id"]

    inter = await client.post(
        f"/maintenance/work-orders/{wid}/intervenants",
        json={"user_id": admin_user.id, "role_in_intervention": "Chef"},
        headers=admin_headers,
    )
    assert inter.status_code == 201, inter.text
    assert inter.json()["created_at"]
    iid = inter.json()["id"]

    inter2 = await client.patch(
        f"/maintenance/intervenants/{iid}",
        json={"hours_spent": "2.5"},
        headers=admin_headers,
    )
    assert inter2.status_code == 200, inter2.text
    assert float(inter2.json()["hours_spent"]) == 2.5

    wo_part = await client.post(
        f"/maintenance/work-orders/{wid}/parts",
        json={"part_id": part_ctx["id"], "quantity": 2},
        headers=admin_headers,
    )
    assert wo_part.status_code == 201, wo_part.text
    assert wo_part.json()["part_summary"]["reference"] == part_ctx["reference"]
    link_id = wo_part.json()["id"]

    rm_part = await client.delete(
        f"/maintenance/work-order-parts/{link_id}", headers=admin_headers
    )
    assert rm_part.status_code == 200, rm_part.text

    rm_inter = await client.delete(
        f"/maintenance/intervenants/{iid}", headers=admin_headers
    )
    assert rm_inter.status_code == 200, rm_inter.text

    await db_session.rollback()

    wo = (
        await db_session.execute(
            select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.id == wid)
        )
    ).scalar_one_or_none()
    assert wo is not None, "OT non persiste en base"
    assert wo.status == "en_cours"

    interventions = (
        await db_session.execute(
            select(func.count())
            .select_from(MaintenanceIntervention)
            .where(MaintenanceIntervention.work_order_id == wid)
        )
    ).scalar_one()
    assert interventions == 1, "intervention non persistee"

    costs = (
        await db_session.execute(
            select(func.count())
            .select_from(MaintenanceCost)
            .where(MaintenanceCost.work_order_id == wid)
        )
    ).scalar_one()
    assert costs == 1, "cout non persiste"

    intervenants = (
        await db_session.execute(
            select(func.count())
            .select_from(MaintenanceIntervenant)
            .where(MaintenanceIntervenant.work_order_id == wid)
        )
    ).scalar_one()
    assert intervenants == 0, "suppression de l'intervenant non commitee"

    wo_parts = (
        await db_session.execute(
            select(func.count())
            .select_from(WorkOrderPart)
            .where(WorkOrderPart.work_order_id == wid)
        )
    ).scalar_one()
    assert wo_parts == 0, "suppression de la piece non commitee"

    history = (
        await db_session.execute(
            select(func.count())
            .select_from(MaintenanceStatusHistory)
            .where(
                MaintenanceStatusHistory.entity_type == "work_order",
                MaintenanceStatusHistory.entity_id == wid,
            )
        )
    ).scalar_one()
    assert history == 2, "historique des statuts OT non persiste"


async def test_create_and_update_plan_with_checklist(
    client, admin_headers, db_session, equipment_ctx
):
    r = await client.post(
        "/maintenance/plans",
        json={
            "equipment_id": equipment_ctx["id"],
            "title": "Revue trimestrielle",
            "frequency": "trimestrielle",
            "checklist_items": [
                {"description": "Controler les niveaux", "sort_order": 0, "is_required": True},
                {"description": "Nettoyer les filtres", "sort_order": 1, "is_required": False},
            ],
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created_at"]
    assert body["updated_at"]
    assert len(body["checklist_items"]) == 2
    pid = body["id"]

    r2 = await client.patch(
        f"/maintenance/plans/{pid}",
        json={
            "title": "Revue semestrielle",
            "frequency": "semestrielle",
            "checklist_items": [
                {"description": "Point unique", "sort_order": 0, "is_required": True}
            ],
        },
        headers=admin_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["title"] == "Revue semestrielle"
    assert r2.json()["updated_at"]
    assert len(r2.json()["checklist_items"]) == 1, "checklist non remplacee"
    assert r2.json()["checklist_items"][0]["description"] == "Point unique"

    r3 = await client.get(f"/maintenance/plans/{pid}", headers=admin_headers)
    assert r3.status_code == 200
    assert r3.json()["equipment_summary"]["id"] == equipment_ctx["id"]
    assert len(r3.json()["checklist_items"]) == 1

    await db_session.rollback()
    plan = (
        await db_session.execute(
            select(MaintenancePlan).where(MaintenancePlan.id == pid)
        )
    ).scalar_one_or_none()
    assert plan is not None, "plan non persiste en base"
    assert plan.title == "Revue semestrielle"
    checklist = (
        await db_session.execute(
            select(func.count())
            .select_from(MaintenancePlanChecklist)
            .where(MaintenancePlanChecklist.plan_id == pid)
        )
    ).scalar_one()
    assert checklist == 1, "checklist non persistee"
