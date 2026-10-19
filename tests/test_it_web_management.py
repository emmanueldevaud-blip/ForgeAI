"""Tests de la détection d'interface web d'administration (IT Asset).

Aucun réseau réel pendant ces tests :
- les « équipements » sont des serveurs locaux 127.0.0.1 construits dans le
  test (HTTP simple ou TLS avec CA de test) ;
- le scan mocke le ping / ARP / SNMP (même pattern que test_it_asset) ;
- les redirections vers des adresses hors inventaire sont vérifiées côté
  valideur (anti-SSRF), sans requête sortante.

Couverture : HTTP, HTTPS (confiance ET refus de certificat non fiable),
401/403, port fermé, timeout, redirections suivies/bloquées, URL manuelle
préservée, IP absente/invalide, permissions API, compatibilité des assets
existants, intégration au scan, sélection du refresh périodique.
"""

import asyncio
import datetime as dt
import ipaddress
import socket
import ssl
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import ITAsset, NetworkRange
from app.schemas.it_asset import ITAssetResponse
from app.services.it_asset import (
    AssetMonitoringService,
    ITAssetService,
    NetworkDiscoveryService,
)
from app.services.web_detect import (
    STATUS_ACCESSIBLE,
    STATUS_AUTH_REQUIRED,
    STATUS_TLS_UNTRUSTED,
    STATUS_TO_CHECK,
    STATUS_UNREACHABLE,
    WebInterfaceDetector,
    validate_management_url,
)

SETTINGS = get_settings()


# ============================================================
# Helpers : serveurs locaux (127.0.0.1 uniquement)
# ============================================================


def _http_response(status=200, reason="OK", headers=None, body=None):
    if body is None:
        body = b"<html><body>admin console</body></html>"
    base_headers = {"Content-Length": str(len(body)), "Connection": "close"}
    base_headers.update(headers or {})
    lines = [f"HTTP/1.1 {status} {reason}"]
    lines += [f"{key}: {value}" for key, value in base_headers.items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + body


class LocalHttpServer:
    """Serveur HTTP minimal sur 127.0.0.1 (aucun réseau réel).

    ``responder(request) -> bytes | None`` construit la réponse ; ``None``
    signifie « accepter la connexion mais ne jamais répondre » (timeout).
    """

    def __init__(self, responder=None, ssl_ctx=None):
        self.requests = []
        self._responder = responder or (lambda request: _http_response())
        self._ssl_ctx = ssl_ctx
        self._server = None
        self._hang = asyncio.Event()
        self.port = None

    async def _handle(self, reader, writer):
        try:
            head = await reader.read(65536)
            if not head:
                return
            text = head.decode("latin-1", "replace")
            first_line = text.split("\r\n", 1)[0]
            parts = first_line.split()
            headers = {}
            for line in text.split("\r\n")[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
            request = {
                "method": parts[0] if parts else "?",
                "path": parts[1] if len(parts) > 1 else "/",
                "headers": headers,
            }
            self.requests.append(request)
            payload = self._responder(request)
            if payload is None:
                # Connexion acceptée mais aucune réponse : timeout HTTP.
                await self._hang.wait()
                return
            writer.write(payload)
            await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self):
        self._hang = asyncio.Event()
        self._server = await asyncio.start_server(
            self._handle, "127.0.0.1", 0, ssl=self._ssl_ctx
        )
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self):
        # Libérer d'abord les handlers bloqués (jamais de réponse) :
        # sur Python 3.12+, wait_closed() attend la fin des handlers.
        self._hang.set()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


def _make_test_ca_and_cert(tmp_path):
    """CA de test + certificat serveur SAN IP 127.0.0.1 (EC P-256)."""
    now = dt.datetime.now(dt.timezone.utc)

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ForgeAI Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    server_key = ec.generate_private_key(ec.SECP256R1())
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    ca_file = tmp_path / "ca.pem"
    cert_file = tmp_path / "server.pem"
    key_file = tmp_path / "server.key"
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    client_ctx = ssl.create_default_context(cafile=str(ca_file))
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(str(cert_file), str(key_file))
    return client_ctx, server_ctx


def _free_closed_port() -> int:
    """Port local susceptible d'être refusé (liaison puis fermeture)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _patch_ports(monkeypatch, *ports):
    monkeypatch.setattr(SETTINGS, "IT_WEB_DETECT_PORTS", ",".join(str(p) for p in ports))


async def _create_asset(db, **kwargs):
    service = ITAssetService(db)
    data = {
        "name": kwargs.pop("name", "Switch-Test"),
        "asset_type": kwargs.pop("asset_type", "switch"),
    }
    data.update(kwargs)
    asset = await service.create_it_asset(data)
    assert asset is not None
    return asset


# ============================================================
# Unitaires purs (aucune DB, aucun réseau)
# ============================================================


def test_validate_management_url_rules():
    assert validate_management_url(None) is None
    assert validate_management_url("") == ""
    assert validate_management_url("  https://192.168.1.1/admin  ") == "https://192.168.1.1/admin"
    with pytest.raises(ValueError):
        validate_management_url("ftp://192.168.1.1/")
    with pytest.raises(ValueError):
        validate_management_url("http://user:pass@192.168.1.1/")
    with pytest.raises(ValueError):
        validate_management_url("http://192.168.1.1/\nX-Inject: 1")
    with pytest.raises(ValueError):
        validate_management_url("http://")


async def test_probe_url_rejects_non_http_schemes():
    detector = WebInterfaceDetector(None)
    result = await detector.probe_url("ftp://127.0.0.1/")
    assert result["http_detected"] is False
    assert result["status"] == STATUS_UNREACHABLE
    assert "schéma refusé" in result["error"]


# ============================================================
# Détection sur serveur local HTTP
# ============================================================


async def test_detect_http_accessible(db_session, monkeypatch):
    server = LocalHttpServer(
        lambda request: _http_response(headers={"Server": "TestSwitch/1.0"})
    )
    port = await server.start()
    try:
        _patch_ports(monkeypatch, port)
        asset = await _create_asset(db_session, ip_address="127.0.0.1")
        service = ITAssetService(db_session)

        updated = await service.detect_management_url(asset.id)

        assert updated.management_url == f"http://127.0.0.1:{port}/"
        assert updated.management_url_source == "auto"
        assert updated.management_url_status == STATUS_ACCESSIBLE
        assert updated.management_url_detected_at is not None
        web = updated.discovery_data["web"]
        assert web["http_detected"] is True
        assert web["http_status"] == 200
        assert web["server"] == "TestSwitch/1.0"
        assert web["tcp_open"] is True
        assert web["ports_candidate"] == [port]
        assert len(server.requests) == 1
    finally:
        await server.stop()


@pytest.mark.parametrize("status_code,reason", [(401, "Unauthorized"), (403, "Forbidden")])
async def test_detect_auth_required_is_not_a_failure(db_session, monkeypatch, status_code, reason):
    server = LocalHttpServer(
        lambda request: _http_response(
            status=status_code,
            reason=reason,
            headers={"WWW-Authenticate": 'Basic realm="TestDevice"'},
        )
    )
    port = await server.start()
    try:
        _patch_ports(monkeypatch, port)
        asset = await _create_asset(db_session, ip_address="127.0.0.1")
        service = ITAssetService(db_session)

        updated = await service.detect_management_url(asset.id)

        # 401/403 = interface protégée, JAMAIS une panne.
        assert updated.management_url_status == STATUS_AUTH_REQUIRED
        assert updated.management_url == f"http://127.0.0.1:{port}/"
        web = updated.discovery_data["web"]
        assert web["http_status"] == status_code
        assert "Basic" in (web["www_authenticate"] or "")
    finally:
        await server.stop()


async def test_detect_unreachable_closed_port(db_session, monkeypatch):
    _patch_ports(monkeypatch, _free_closed_port())
    asset = await _create_asset(db_session, ip_address="127.0.0.1")
    service = ITAssetService(db_session)

    updated = await service.detect_management_url(asset.id)

    assert updated.management_url is None
    assert updated.management_url_status == STATUS_UNREACHABLE
    web = updated.discovery_data["web"]
    assert web["tcp_open"] is False
    assert web["http_detected"] is False
    assert web["error"] == "aucun port ouvert"


async def test_detect_tcp_open_but_no_http_answer(db_session, monkeypatch):
    # Port ouvert mais jamais de réponse HTTP : on distingue TCP et HTTP.
    server = LocalHttpServer(lambda request: None)
    port = await server.start()
    try:
        _patch_ports(monkeypatch, port)
        monkeypatch.setattr(SETTINGS, "IT_WEB_DETECT_HTTP_TIMEOUT", 0.6)
        asset = await _create_asset(db_session, ip_address="127.0.0.1")
        service = ITAssetService(db_session)

        updated = await service.detect_management_url(asset.id)

        assert updated.management_url is None
        assert updated.management_url_status == STATUS_UNREACHABLE
        web = updated.discovery_data["web"]
        assert web["tcp_open"] is True      # TCP ouvert
        assert web["http_detected"] is False  # ... mais pas d'interface HTTP
        assert web["error"]
    finally:
        await server.stop()


# ============================================================
# HTTPS : confiance ET vérification jamais désactivée
# ============================================================


async def test_detect_https_trusted_and_untrusted(tmp_path, db_session, monkeypatch):
    client_ctx, server_ctx = _make_test_ca_and_cert(tmp_path)
    server = LocalHttpServer(ssl_ctx=server_ctx)
    port = await server.start()
    try:
        _patch_ports(monkeypatch, port)
        asset = await _create_asset(db_session, ip_address="127.0.0.1")
        service = ITAssetService(db_session)
        trusted_detector = WebInterfaceDetector(db_session, verify=client_ctx)

        # 1. CA de test injecté comme magasin de confiance : accessible.
        updated = await service.detect_management_url(asset.id, detector=trusted_detector)
        assert updated.management_url == f"https://127.0.0.1:{port}/"
        assert updated.management_url_status == STATUS_ACCESSIBLE
        assert updated.discovery_data["web"]["scheme"] in ("http", "https")

        # 2. verify=True (par défaut, magasin système) : certificat inconnu →
        #    tls_untrusted. La vérification n'est JAMAIS contournée.
        strict_detector = WebInterfaceDetector(db_session, verify=True)
        updated = await service.detect_management_url(asset.id, detector=strict_detector)
        assert updated.management_url_status == STATUS_TLS_UNTRUSTED
        assert updated.discovery_data["web"]["http_detected"] is False
    finally:
        await server.stop()


# ============================================================
# Redirections (anti-SSRF)
# ============================================================


async def test_detect_redirect_http_to_https_followed(tmp_path, db_session, monkeypatch):
    client_ctx, server_ctx = _make_test_ca_and_cert(tmp_path)
    tls_server = LocalHttpServer(ssl_ctx=server_ctx)
    tls_port = await tls_server.start()
    target = f"https://127.0.0.1:{tls_port}/"
    http_server = LocalHttpServer(
        lambda request: _http_response(302, "Found", headers={"Location": target})
    )
    http_port = await http_server.start()
    try:
        _patch_ports(monkeypatch, http_port)
        asset = await _create_asset(db_session, ip_address="127.0.0.1")
        service = ITAssetService(db_session)
        detector = WebInterfaceDetector(db_session, verify=client_ctx)

        updated = await service.detect_management_url(asset.id, detector=detector)

        assert updated.management_url == target
        assert updated.management_url_status == STATUS_ACCESSIBLE
        assert updated.discovery_data["web"]["redirect_to"] == target
    finally:
        await http_server.stop()
        await tls_server.stop()


async def test_detect_redirect_out_of_scope_is_blocked(db_session, monkeypatch):
    # 10.255.255.1 n'est dans aucun inventaire ni aucune plage : la
    # redirection ne doit PAS être suivie (aucune requête sortante).
    server = LocalHttpServer(
        lambda request: _http_response(
            302, "Found", headers={"Location": "http://10.255.255.1/admin"}
        )
    )
    port = await server.start()
    try:
        _patch_ports(monkeypatch, port)
        asset = await _create_asset(db_session, ip_address="127.0.0.1")
        service = ITAssetService(db_session)

        updated = await service.detect_management_url(asset.id)

        # L'interface d'origine a répondu, la cible hors périmètre est bloquée.
        assert updated.management_url_status == STATUS_ACCESSIBLE
        assert updated.management_url == f"http://127.0.0.1:{port}/"
        web = updated.discovery_data["web"]
        assert web["redirect_blocked"] == "http://10.255.255.1/admin"
        assert "non autorisée" in web["redirect_error"]
        # Une seule requête : celle vers le serveur local (pas le saut suivant).
        assert len(server.requests) == 1
    finally:
        await server.stop()


# ============================================================
# URL manuelle, IP absente/invalide
# ============================================================


async def test_manual_url_is_never_overwritten(db_session, monkeypatch):
    server = LocalHttpServer()
    port = await server.start()
    try:
        asset = await _create_asset(db_session, ip_address="127.0.0.1")
        service = ITAssetService(db_session)
        manual_url = f"http://127.0.0.1:{port}/custom"
        stored = await service.set_management_url(asset.id, manual_url)
        assert stored.management_url_source == "manual"
        assert stored.management_url_status == STATUS_TO_CHECK

        # Re-détection : vérifie l'URL manuelle sans jamais la modifier.
        updated = await service.detect_management_url(asset.id)
        assert updated.management_url == manual_url
        assert updated.management_url_source == "manual"
        assert updated.management_url_status == STATUS_ACCESSIBLE
        assert updated.management_url_detected_at is not None

        # Même une probe « update_url=True » ne doit pas écraser une URL manuelle.
        await service.record_management_probe(
            asset.id,
            {"status": STATUS_ACCESSIBLE, "url": f"http://127.0.0.1:{port}/other"},
            update_url=True,
        )
        final = await service.get_it_asset(asset.id)
        assert final.management_url == manual_url
        assert final.management_url_source == "manual"
    finally:
        await server.stop()


async def test_detect_without_ip_reports_to_check(db_session):
    asset = await _create_asset(db_session)  # aucune IP
    service = ITAssetService(db_session)

    updated = await service.detect_management_url(asset.id)

    assert updated.management_url is None
    assert updated.management_url_status == STATUS_TO_CHECK
    assert updated.discovery_data["web"]["error"] == "aucune adresse IP configurée"

    # IP invalide côté detector : pas de requête, statut « à vérifier ».
    detector = WebInterfaceDetector(db_session)
    probe = await detector.probe_asset("999.999.999.999", None)
    assert probe["status"] == STATUS_TO_CHECK
    assert probe["error"] == "adresse IP absente ou invalide"


# ============================================================
# API : permissions et validation
# ============================================================


async def test_management_url_api_permissions(client, auth_headers, admin_headers, db_session):
    asset = await _create_asset(db_session, ip_address="127.0.0.1")

    # Utilisateur sans permission it_asset.* : 403 sur les trois endpoints.
    resp = await client.patch(
        f"/it-assets/{asset.id}/management-url",
        json={"management_url": "http://127.0.0.1/"},
        headers=auth_headers,
    )
    assert resp.status_code == 403
    resp = await client.post(f"/it-assets/{asset.id}/management-url/detect", headers=auth_headers)
    assert resp.status_code == 403
    resp = await client.post(f"/it-assets/{asset.id}/management-url/check", headers=auth_headers)
    assert resp.status_code == 403

    # L'équipement n'a pas été modifié par les tentatives refusées.
    untouched = await ITAssetService(db_session).get_it_asset(asset.id)
    assert untouched.management_url is None

    # 404 sur un équipement inexistant (admin).
    resp = await client.post("/it-assets/999999/management-url/detect", headers=admin_headers)
    assert resp.status_code == 404


async def test_management_url_api_validation(client, admin_headers, db_session):
    asset = await _create_asset(db_session, ip_address="127.0.0.1")

    # Schéma hors http/https refusé (422).
    resp = await client.patch(
        f"/it-assets/{asset.id}/management-url",
        json={"management_url": "ftp://192.168.1.1/"},
        headers=admin_headers,
    )
    assert resp.status_code == 422

    # Identifiants embarqués refusés (422).
    resp = await client.patch(
        f"/it-assets/{asset.id}/management-url",
        json={"management_url": "http://admin:secret@192.168.1.1/"},
        headers=admin_headers,
    )
    assert resp.status_code == 422

    # Saisie valide → source manuelle.
    resp = await client.patch(
        f"/it-assets/{asset.id}/management-url",
        json={"management_url": "https://192.168.1.10/admin"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["management_url"] == "https://192.168.1.10/admin"
    assert body["management_url_source"] == "manual"
    assert body["management_url_status"] == STATUS_TO_CHECK

    # Champ vide = effacement.
    resp = await client.patch(
        f"/it-assets/{asset.id}/management-url",
        json={"management_url": ""},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["management_url"] is None
    assert resp.json()["management_url_source"] is None


async def test_management_url_api_detect_and_check(client, admin_headers, db_session, monkeypatch):
    server = LocalHttpServer()
    port = await server.start()
    try:
        asset = await _create_asset(db_session, ip_address="127.0.0.1")
        service = ITAssetService(db_session)
        await service.set_management_url(asset.id, f"http://127.0.0.1:{port}/")

        # Check : l'URL manuelle répond → accessible, URL inchangée.
        resp = await client.post(
            f"/it-assets/{asset.id}/management-url/check", headers=admin_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["management_url"] == f"http://127.0.0.1:{port}/"
        assert body["management_url_status"] == STATUS_ACCESSIBLE
        assert body["management_url_source"] == "manual"
        assert body["details"]["http_detected"] is True

        # Detect : l'URL manuelle pointe sur un port fermé alors qu'un
        # serveur répondrait sur l'IP → la détection vérifie l'URL
        # manuelle, ne l'écrase jamais, et reporte « injoignable ».
        closed = _free_closed_port()
        resp = await client.patch(
            f"/it-assets/{asset.id}/management-url",
            json={"management_url": f"http://127.0.0.1:{closed}/"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        _patch_ports(monkeypatch, port)  # serveur local vivant (détection auto possible)
        resp = await client.post(
            f"/it-assets/{asset.id}/management-url/detect", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["management_url"] == f"http://127.0.0.1:{closed}/"
        assert resp.json()["management_url_source"] == "manual"
        assert resp.json()["management_url_status"] == STATUS_UNREACHABLE

        # Check sans URL → 400 explicite.
        other = await _create_asset(db_session, name="Autre-Asset", ip_address=None)
        resp = await client.post(
            f"/it-assets/{other.id}/management-url/check", headers=admin_headers
        )
        assert resp.status_code == 400
    finally:
        await server.stop()


# ============================================================
# Compatibilité avec les équipements existants
# ============================================================


async def test_existing_assets_keep_null_management_fields(db_session):
    asset = await _create_asset(
        db_session, name="Asset-Avant-Fonctionnalite", ip_address="192.168.1.50"
    )
    service = ITAssetService(db_session)

    # Champs encore vides : réponse sérialisable, aucune régression.
    resp = ITAssetResponse.model_validate(asset)
    assert resp.management_url is None
    assert resp.management_url_source is None
    assert resp.management_url_status is None
    assert resp.management_url_detected_at is None

    # Update générique inchangé : ne touche pas aux champs management (None).
    updated = await service.update_it_asset(asset.id, {"name": "Asset-Renomme"})
    assert updated.name == "Asset-Renomme"
    assert updated.management_url is None

    # Liste / recherche inchangées.
    result = await db_session.execute(select(ITAsset).where(ITAsset.id == asset.id))
    assert result.scalar_one_or_none() is not None


# ============================================================
# Intégration au scan réseau (mocké — serveur local uniquement)
# ============================================================


async def _mock_local_scan(db, monkeypatch, reachable_ips):
    discovery = NetworkDiscoveryService(db)

    async def fake_ping(ip, timeout=2.0):
        return (ip in reachable_ips, 5.0)

    async def fake_arp(ip):
        return {"127.0.0.1": "AA:BB:CC:DD:EE:77"}.get(ip)

    async def fake_snmp(ip, community, version="2c", timeout=2.0, retries=3, port=161):
        return None

    monkeypatch.setattr(discovery, "_ping_host", fake_ping)
    monkeypatch.setattr(discovery, "_get_mac_from_arp", fake_arp)
    monkeypatch.setattr(discovery, "_get_snmp_info", fake_snmp)
    return discovery


async def test_scan_integration_detects_web_interface(db_session, monkeypatch):
    server = LocalHttpServer(
        lambda request: _http_response(headers={"Server": "ScanTarget/1.0"})
    )
    port = await server.start()
    try:
        monkeypatch.setattr(SETTINGS, "IT_WEB_DETECT_ENABLED", True)
        _patch_ports(monkeypatch, port)
        service = ITAssetService(db_session)
        network_range = await service.create_network_range({
            "name": "Boucle",
            "cidr": "127.0.0.0/30",  # .1 (atteint) et .2 (inatteint)
            "snmp_enabled": False,
        })
        discovery = await _mock_local_scan(db_session, monkeypatch, reachable_ips={"127.0.0.1"})

        result = await discovery.scan_network_range(network_range.id)

        # Non-régression du scan : compteurs inchangés, aucun échec.
        assert "error" not in result
        assert result["hosts_scanned"] == 2
        assert result["hosts_found"] == 1
        assert result["assets_created"] == 1

        # L'asset créé reçoit son interface web détectée automatiquement.
        asset = await service.get_it_asset_by_ip("127.0.0.1")
        assert asset is not None
        assert asset.management_url == f"http://127.0.0.1:{port}/"
        assert asset.management_url_source == "auto"
        assert asset.management_url_status == STATUS_ACCESSIBLE
        assert asset.discovery_data["web"]["server"] == "ScanTarget/1.0"
    finally:
        await server.stop()


# ============================================================
# Refresh périodique (sélection et lot)
# ============================================================


async def _set_stale(db, asset, hours):
    asset.management_url_detected_at = datetime.now(UTC) - timedelta(hours=hours)
    await db.commit()


async def test_periodic_refresh_selects_only_due_and_limits_batch(db_session, test_engine, monkeypatch):
    monkeypatch.setattr(SETTINGS, "IT_WEB_DETECT_ENABLED", True)
    service = ITAssetService(db_session)
    stale_old = await _create_asset(db_session, name="Stale-Ancien", ip_address="127.0.0.1")
    stale_mid = await _create_asset(db_session, name="Stale-Moyen", ip_address="127.0.0.2")
    stale_new = await _create_asset(db_session, name="Stale-Recent", ip_address="127.0.0.3")
    fresh = await _create_asset(db_session, name="Fraichement-Verifie", ip_address="127.0.0.4")
    no_url = await _create_asset(db_session, name="Sans-URL", ip_address="127.0.0.5")
    for asset in (stale_old, stale_mid, stale_new, fresh):
        await service.set_management_url(asset.id, f"http://{asset.ip_address}/")

    await _set_stale(db_session, stale_old, hours=30)
    await _set_stale(db_session, stale_mid, hours=28)
    await _set_stale(db_session, stale_new, hours=26)
    await _set_stale(db_session, fresh, hours=1)
    assert no_url.management_url is None

    # Vérification factice (aucun réseau) : enregistre les ids appelés.
    checked_ids = []

    async def fake_check(self, asset_id, detector=None):
        checked_ids.append(asset_id)
        return object()

    monkeypatch.setattr(ITAssetService, "check_management_url", fake_check)
    # Sessions internes du refresh : sur la DB de test uniquement.
    test_maker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", test_maker)

    # Lot limité à 2 : seulement les deux plus anciens sont re-vérifiés.
    monkeypatch.setattr(SETTINGS, "IT_WEB_DETECT_REFRESH_BATCH", 2)
    result = await AssetMonitoringService(db_session).refresh_due_management_urls()
    assert result["due"] == 2
    assert result["checked"] == 2
    assert set(checked_ids) == {stale_old.id, stale_mid.id}

    # Lot plus grand : tous les équipements périmés avec URL (pas le frais,
    # pas celui sans URL).
    checked_ids.clear()
    monkeypatch.setattr(SETTINGS, "IT_WEB_DETECT_REFRESH_BATCH", 10)
    result = await AssetMonitoringService(db_session).refresh_due_management_urls()
    assert result["due"] == 3
    assert result["checked"] == 3
    assert set(checked_ids) == {stale_old.id, stale_mid.id, stale_new.id}


async def test_periodic_refresh_disabled_by_setting(db_session, monkeypatch):
    monkeypatch.setattr(SETTINGS, "IT_WEB_DETECT_ENABLED", False)
    result = await AssetMonitoringService(db_session).refresh_due_management_urls()
    assert result["disabled"] is True
    assert result["due"] == 0
