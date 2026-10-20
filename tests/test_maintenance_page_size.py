"""Les menus deroulants du frontend chargent les listes avec page_size=1000.

Une limite inferieure rejetait la requete en 422 et le catch frontend
laissait les menus vides (prestataires non affiches dans le modal contrat).
"""


async def test_provider_list_accepts_frontend_dropdown_page_size(
    client, admin_headers
):
    created = await client.post(
        "/maintenance/providers",
        json={"name": "Presta Menu Test"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text

    r = await client.get(
        "/maintenance/providers?page_size=1000&is_active=true",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    names = [p["name"] for p in r.json()["items"]]
    assert "Presta Menu Test" in names, "prestataire absent du menu deroulant"


async def test_maintenance_lists_accepts_page_size_1000(client, admin_headers):
    for endpoint in ("/maintenance/plans", "/maintenance/work-orders", "/maintenance/parts"):
        r = await client.get(f"{endpoint}?page_size=1000", headers=admin_headers)
        assert r.status_code == 200, f"{endpoint} -> {r.status_code}: {r.text[:200]}"
