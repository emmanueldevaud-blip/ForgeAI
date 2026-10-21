"""Tests des pièces jointes aux contrats de maintenance."""

import os
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.maintenance import MaintenanceContractAttachment


@pytest.fixture(autouse=True)
def attachment_upload_dir(tmp_path, monkeypatch):
    upload_dir = tmp_path / "contract_attachments"
    monkeypatch.setenv("MAINTENANCE_UPLOAD_DIR", str(upload_dir))
    return upload_dir


async def _create_test_contract(client, admin_headers):
    """Create a provider then a contract, return contract_id."""
    from uuid import uuid4
    provider_data = {
        "name": "Test Provider",
        "contact_email": "test@provider.com",
        "phone": "+33123456789",
    }
    r = await client.post("/maintenance/providers", json=provider_data, headers=admin_headers)
    assert r.status_code == 201, f"Failed to create provider: {r.status_code} {r.text}"
    provider_id = r.json()["id"]

    from datetime import date
    contract_data = {
        "provider_id": provider_id,
        "reference": f"CONTRAT-TEST-{uuid4().hex[:8]}",
        "subject": "Test Contract",
        "start_date": date.today().isoformat(),
        "is_active": True,
    }
    r = await client.post("/maintenance/contracts", json=contract_data, headers=admin_headers)
    assert r.status_code == 201, f"Failed to create contract: {r.status_code} {r.text}"
    return r.json()["id"]


async def test_contract_attachment_full_lifecycle(client, admin_headers, db_session, attachment_upload_dir):
    """Test complet upload → liste → download → delete → persistance."""
    contract_id = await _create_test_contract(client, admin_headers)

    # Test 1: Upload PDF
    pdf_content = b"%PDF-1.4 test content"
    files = {"file": ("contrat.pdf", pdf_content, "application/pdf")}
    r = await client.post(
        f"/maintenance/contracts/{contract_id}/attachments",
        files=files,
        headers=admin_headers,
    )
    assert r.status_code == 201, f"Upload failed: {r.status_code} {r.text}"
    attachment = r.json()
    assert attachment["filename"] == "contrat.pdf"
    assert attachment["file_size"] == len(pdf_content)

    # Verify file on disk
    uploaded_path = Path(attachment["file_path"])
    assert uploaded_path.exists(), "Fichier non écrit sur disque"

    # Test 2: List attachments
    r = await client.get(f"/maintenance/contracts/{contract_id}/attachments", headers=admin_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["filename"] == "contrat.pdf"

    # Test 3: Download
    att_id = attachment["id"]
    r = await client.get(f"/maintenance/attachments/{att_id}/download", headers=admin_headers)
    assert r.status_code == 200
    assert r.content == pdf_content
    assert "inline" in r.headers.get("content-disposition", ""), "PDF doit être affiché en aperçu"

    # Test 4: Persistence - the attachment should be committed in DB
    result = await db_session.execute(select(MaintenanceContractAttachment).where(MaintenanceContractAttachment.id == att_id))
    persisted = result.scalar_one()
    assert persisted.id == att_id
    assert persisted.filename == "contrat.pdf"

    # Test 5: Delete
    r = await client.delete(f"/maintenance/attachments/{att_id}", headers=admin_headers)
    assert r.status_code == 200

    # Verify file deleted from disk
    assert not uploaded_path.exists(), "Fichier non supprimé du disque"

    # Verify list is now empty
    r = await client.get(f"/maintenance/contracts/{contract_id}/attachments", headers=admin_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 0

    # Verify download returns 404 after deletion
    r = await client.get(f"/maintenance/attachments/{att_id}/download", headers=admin_headers)
    assert r.status_code == 404


async def test_contract_attachment_upload_unknown_contract(client, admin_headers):
    """Upload sur contrat inexistant → 404."""
    pdf_content = b"%PDF-1.4 test"
    files = {"file": ("contrat.pdf", pdf_content, "application/pdf")}
    r = await client.post(
        "/maintenance/contracts/999999/attachments",
        files=files,
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_contract_attachment_unsafe_type_is_forced_download(client, admin_headers):
    """Un type MIME non sûr (hors images/PDF) est servi en téléchargement, pas en aperçu."""
    contract_id = await _create_test_contract(client, admin_headers)
    files = {"file": ("outil.exe", b"MZbinary", "application/x-msdownload")}
    r = await client.post(
        f"/maintenance/contracts/{contract_id}/attachments",
        files=files,
        headers=admin_headers,
    )
    assert r.status_code == 201
    att_id = r.json()["id"]

    r = await client.get(f"/maintenance/attachments/{att_id}/download", headers=admin_headers)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")