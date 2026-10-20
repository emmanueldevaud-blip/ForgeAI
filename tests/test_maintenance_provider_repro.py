"""Reproduction bug création prestataire maintenance."""

import pytest


async def test_create_provider_repro(client, admin_headers):
    payload = {
        "name": "Test Presta",
        "code": "TP01",
        "company_name": "Societe Test",
        "email": "test@example.com",
        "phone": "0102030405",
        "address": "1 rue de la paix",
        "specialties": "Electricite",
        "is_active": True,
    }
    response = await client.post(
        "/maintenance/providers", json=payload, headers=admin_headers
    )
    print("STATUS:", response.status_code)
    print("BODY:", response.text)
    assert response.status_code == 201, response.text
