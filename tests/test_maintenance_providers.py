"""Tests API des prestataires de maintenance (create/update/persistance)."""
from sqlalchemy import select

from app.models.maintenance import MaintenanceProvider


async def test_create_and_update_provider(client, admin_headers, db_session):
    r = await client.post(
        "/maintenance/providers",
        json={"name": "Presta Update Test", "phone": "01"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["created_at"]

    r2 = await client.patch(
        f"/maintenance/providers/{pid}",
        json={"phone": "02", "email": "new@x.fr"},
        headers=admin_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["phone"] == "02"
    assert r2.json()["email"] == "new@x.fr"
    assert r2.json()["updated_at"]

    r3 = await client.get(f"/maintenance/providers/{pid}", headers=admin_headers)
    assert r3.status_code == 200
    assert r3.json()["phone"] == "02"

    row = (await db_session.execute(
        select(MaintenanceProvider).where(MaintenanceProvider.id == pid)
    )).scalar_one_or_none()
    assert row is not None, "provider non persiste en base"
    assert row.phone == "02"
