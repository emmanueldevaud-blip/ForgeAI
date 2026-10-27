"""Tests du module IT Asset : helpers, service et scan réseau mocké.

Cibles :
- normalisation MAC / parsing SNMP (unitaires) ;
- création d'asset avec les champs V2 (inventaire avancé) ;
- verrou documenté : ``update_it_asset`` ignore les valeurs ``None`` ;
- dédoublonnage de l'import (MAC / IP / serial) ;
- scan réseau mocké (jamais de scan réseau réel) avec priorité
  Manuel > SNMP sur les champs ``snmp_*`` et le nom.
"""
import pytest
from sqlalchemy import select

from app.models import ITAsset, NetworkRange, Room, Building, Site
from app.services.it_asset import (
    ITAssetService,
    NetworkDiscoveryService,
    _normalize_mac,
    _parse_snmp_results,
    send_wake_on_lan,
    shutdown_windows_host,
    generate_rdp_file_content,
)


# ============================================================
# Helpers purs (aucune DB)
# ============================================================


def test_normalize_mac_lowercases_and_replaces_dashes():
    assert _normalize_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"


def test_normalize_mac_passthrough_and_empty():
    assert _normalize_mac("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:dd:ee:ff"
    assert _normalize_mac(None) is None
    assert _normalize_mac("") is None


def test_parse_snmp_results_extracts_sys_fields_and_vendor():
    raw = {
        "1.3.6.1.2.1.1.1.0": "Cisco IOS Software, C2960 Software",
        "1.3.6.1.2.1.1.5.0": "SW-LAB-01",
        "1.3.6.1.2.1.1.4.0": "netadmin@example.com",
        "1.3.6.1.2.1.1.6.0": "Local technique RDC",
    }
    parsed = _parse_snmp_results(raw)
    assert parsed["sys_descr"] == "Cisco IOS Software, C2960 Software"
    assert parsed["sys_name"] == "SW-LAB-01"
    assert parsed["sys_contact"] == "netadmin@example.com"
    assert parsed["sys_location"] == "Local technique RDC"
    assert parsed["vendor"] == "Cisco"


def test_parse_snmp_results_ignores_empty_values():
    parsed = _parse_snmp_results({"1.3.6.1.2.1.1.1.0": None, "1.3.6.1.2.1.1.5.0": ""})
    assert "sys_descr" not in parsed
    assert "vendor" not in parsed


# ============================================================
# Fixtures DB
# ============================================================


async def _create_room(db) -> Room:
    """Créer un site/bâtiment/pièce. La pièce reçoit l'id=1 (auto-incrément)."""
    site = Site(reference="SITE-TEST", name="Site de test")
    db.add(site)
    await db.flush()
    building = Building(site_id=site.id, reference="B-1", name="Bâtiment test")
    db.add(building)
    await db.flush()
    room = Room(building_id=building.id, reference="R-101", name="Salle test")
    db.add(room)
    await db.commit()
    await db.refresh(room)
    assert room.id == 1  # requis : scan_host utilise room_id=1 en dur
    return room


# ============================================================
# ITAssetService
# ============================================================


async def test_create_it_asset_persists_v2_inventory_fields(db_session):
    await _create_room(db_session)
    service = ITAssetService(db_session)

    asset = await service.create_it_asset({
        "name": "PC-Direction",
        "asset_type": "pc_windows",
        "room_id": 1,
        "status": "online",
        "manufacturer": "Dell",
        "model": "OptiPlex 7010",
        "serial_number": "SN-TEST-001",
        "ip_address": "192.168.1.10",
        "mac_address": "AA-BB-CC-DD-EE-01",
        "os": "Windows",
        "os_version": "11",
        "os_build": "22631.3672",
        "os_architecture": "64-bit",
        "cpu_name": "Intel Core i5-13500",
        "cpu_cores": 14,
        "ram_total_mb": 16384,
        "ram_free_mb": 8192,
        "disk_total_mb": 512000,
        "disk_free_mb": 256000,
        "bios_version": "1.12.0",
        "manufacturer_system": "Dell Inc.",
        "domain": "forgeai.local",
        "computer_name_ad": "PC-DIRECTION",
        "organizational_unit": "OU=Direction,DC=forgeai,DC=local",
        "is_domain_joined": True,
        "agent_version": "1.0.0",
        "snmp_manufacturer": "Dell",
        "snmp_model": "OptiPlex 7010",
        "snmp_firmware_version": "1.12.0",
        "snmp_contact": "it@forgeai.local",
        "snmp_location": "Bureau direction",
        "notes": "Poste de la direction",
    })

    assert asset is not None
    assert asset.reference.startswith("IT-")
    assert asset.mac_address == "aa:bb:cc:dd:ee:01"  # normalisée
    assert asset.os_build == "22631.3672"
    assert asset.os_architecture == "64-bit"
    assert asset.cpu_cores == 14
    assert asset.ram_total_mb == 16384
    assert asset.disk_free_mb == 256000
    assert asset.bios_version == "1.12.0"
    assert asset.manufacturer_system == "Dell Inc."
    assert asset.domain == "forgeai.local"
    assert asset.computer_name_ad == "PC-DIRECTION"
    assert asset.is_domain_joined is True
    assert asset.snmp_manufacturer == "Dell"
    assert asset.snmp_location == "Bureau direction"

    # Relecture depuis la DB (persistance des champs V2)
    reloaded = await service.get_it_asset(asset.id)
    assert reloaded.os_build == "22631.3672"
    assert reloaded.snmp_contact == "it@forgeai.local"


async def test_update_it_asset_ignores_none_values(db_session):
    """Verrou documenté : update_it_asset n'applique jamais None (impossible de vider un champ)."""
    await _create_room(db_session)
    service = ITAssetService(db_session)
    asset = await service.create_it_asset({
        "name": "PC-Test",
        "asset_type": "pc_windows",
        "room_id": 1,
        "os_build": "19045.4651",
        "notes": "Note initiale",
    })

    updated = await service.update_it_asset(asset.id, {
        "name": None,          # ignoré : le nom reste inchangé
        "os_build": "22631.3672",
        "notes": None,         # ignoré : la note reste inchangée
    })

    assert updated.name == "PC-Test"
    assert updated.os_build == "22631.3672"
    assert updated.notes == "Note initiale"


async def test_import_it_assets_skips_duplicates_by_mac(db_session):
    await _create_room(db_session)
    service = ITAssetService(db_session)

    items = [
        {
            "name": "PC-Import-1",
            "asset_type": "pc_windows",
            "room_id": 1,
            "mac_address": "11:22:33:44:55:66",
            "ip_address": "10.0.0.10",
        },
        {
            "name": "PC-Import-Doublon",
            "asset_type": "pc_windows",
            "room_id": 1,
            "mac_address": "11:22:33:44:55:66",  # même MAC
            "ip_address": "10.0.0.99",
        },
    ]

    result = await service.import_it_assets(items, skip_duplicates=True)

    assert result["created"] == 1
    assert result["skipped"] == 1
    assert result["errors"] == []

    assets = (await db_session.execute(select(ITAsset))).scalars().all()
    assert len(assets) == 1
    assert assets[0].name == "PC-Import-1"


async def test_import_it_assets_reports_missing_room(db_session):
    await _create_room(db_session)
    service = ITAssetService(db_session)

    result = await service.import_it_assets([
        {"name": "PC-Sans-Salle", "asset_type": "pc_windows"},  # ni room_id ni référence
    ])

    assert result["created"] == 0
    assert result["skipped"] == 1
    assert any("Pièce introuvable" in err for err in result["errors"])


# ============================================================
# Scan réseau (mocké — aucun scan réseau réel)
# ============================================================


async def _mock_discovery(db, monkeypatch, *, reachable_ips, mac_by_ip, snmp_by_ip):
    """Instancier un NetworkDiscoveryService entièrement mocké."""
    discovery = NetworkDiscoveryService(db)

    async def fake_ping(ip, timeout=2.0):
        if ip in reachable_ips:
            return True, 5.0
        return False, None

    async def fake_arp(ip):
        return mac_by_ip.get(ip)

    async def fake_snmp(ip, community, version="2c", timeout=2.0, retries=3, port=161):
        return snmp_by_ip.get(ip)

    monkeypatch.setattr(discovery, "_ping_host", fake_ping)
    monkeypatch.setattr(discovery, "_get_mac_from_arp", fake_arp)
    monkeypatch.setattr(discovery, "_get_snmp_info", fake_snmp)
    return discovery


async def test_scan_network_range_creates_asset_with_snmp_fields(db_session, monkeypatch):
    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab",
        "cidr": "192.168.77.0/30",  # 2 hosts : .1 et .2
        "snmp_enabled": True,
        "snmp_community": "public",
        "snmp_version": "v2c",
        "snmp_port": 161,
    })

    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.77.1"},
        mac_by_ip={"192.168.77.1": "AA:BB:CC:DD:EE:01"},
        snmp_by_ip={
            "192.168.77.1": {
                "1.3.6.1.2.1.1.1.0": "Cisco IOS Software, C2960",
                "1.3.6.1.2.1.1.5.0": "SW-LAB-01",
                "1.3.6.1.2.1.1.4.0": "netadmin@example.com",
                "1.3.6.1.2.1.1.6.0": "Local technique RDC",
            }
        },
    )

    result = await discovery.scan_network_range(network_range.id)

    assert result["hosts_scanned"] == 2
    assert result["hosts_found"] == 1
    assert result["assets_created"] == 1

    asset = await service.get_it_asset_by_ip("192.168.77.1")
    assert asset is not None
    assert asset.name == "SW-LAB-01"  # sys_name SNMP
    assert asset.mac_address == "aa:bb:cc:dd:ee:01"
    assert asset.status == "online"
    assert asset.discovery_source == "network_scan"
    assert asset.snmp_manufacturer == "Cisco"  # vendor déduit du sysDescr
    assert asset.snmp_contact == "netadmin@example.com"
    assert asset.snmp_location == "Local technique RDC"
    assert asset.discovery_data["snmp"]["raw"]["1.3.6.1.2.1.1.5.0"] == "SW-LAB-01"


async def test_scan_network_range_does_not_overwrite_manual_values(db_session, monkeypatch):
    """Priorité Manuel > scan > SNMP : nom et champs saisis manuellement préservés."""
    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab 2",
        "cidr": "192.168.78.0/30",
        "snmp_enabled": True,
        "snmp_community": "public",
        "snmp_version": "v2c",
    })
    existing = await service.create_it_asset({
        "name": "PC-Direction",  # nom manuel
        "asset_type": "pc_windows",
        "room_id": 1,
        "ip_address": "192.168.78.1",
        "mac_address": "aa:bb:cc:dd:ee:02",
        "snmp_manufacturer": "Fabricant Manuel",  # valeur manuelle
    })

    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.78.1"},
        mac_by_ip={"192.168.78.1": "aa:bb:cc:dd:ee:02"},
        snmp_by_ip={
            "192.168.78.1": {
                "1.3.6.1.2.1.1.1.0": "Dell OS",
                "1.3.6.1.2.1.1.4.0": "contact@snmp.local",
            }
        },
    )

    result = await discovery.scan_network_range(network_range.id)

    assert result["assets_updated"] == 1
    assert result["assets_created"] == 0

    asset = await service.get_it_asset(existing.id)
    assert asset.name == "PC-Direction"  # non écrasé par le scan
    assert asset.snmp_manufacturer == "Fabricant Manuel"  # non écrasé par SNMP
    assert asset.snmp_contact == "contact@snmp.local"  # champ vide → renseigné par SNMP
    assert asset.status == "online"


# ============================================================
# Scan réseau — résolution MAC croisée via routeur (table ARP SNMP)
# ============================================================


class _FakeArpResolverSettings:
    """Réplique minimale des settings IT_ARP_RESOLVER_* pour activer le résolveur."""

    IT_ARP_RESOLVER_ENABLED = True
    IT_ARP_RESOLVER_HOST = "192.168.79.253"
    IT_ARP_RESOLVER_COMMUNITY = ""
    IT_ARP_RESOLVER_VERSION = "2c"
    IT_ARP_RESOLVER_PORT = 161
    IT_ARP_RESOLVER_CACHE_TTL = 300
    # Nouveaux settings DHCP/DNS (désactivés par défaut pour les tests existants)
    IT_DHCP_RESOLVER_ENABLED = False
    IT_DHCP_RESOLVER_URL = ""
    IT_DHCP_RESOLVER_API_KEY = ""
    IT_DHCP_RESOLVER_USER = ""
    IT_DHCP_RESOLVER_PASSWORD = ""
    IT_DHCP_RESOLVER_CACHE_TTL = 300
    IT_DHCP_KEA_LEASE_FILE = ""
    IT_DHCP_KEA_CACHE_TTL = 300
    IT_DNS_RESOLVER_ENABLED = False
    IT_DNS_RESOLVER_SERVER = ""
    IT_DNS_RESOLVER_PORT = 53
    IT_DNS_RESOLVER_TIMEOUT = 2.0
    IT_DNS_RESOLVER_CACHE_TTL = 300


def _patch_arp_settings(monkeypatch, enabled=True):
    from app.services import it_asset as it_asset_module

    class _S(_FakeArpResolverSettings):
        IT_ARP_RESOLVER_ENABLED = enabled

    monkeypatch.setattr(it_asset_module, "get_settings", lambda: _S())


def _patch_arp_walk(monkeypatch, discovery, phys=None, addrs=None, error=None):
    """Mocker le walk SNMP des colonnes ARP sur l'instance de scan."""
    calls = {"n": 0}

    async def fake_walk(ip, column_oid, community, **kwargs):
        calls["n"] += 1
        if error:
            raise error
        from app.services.it_asset import _IPNETTOMEDIA_ADDR, _IPNETTOMEDIA_PHYS

        if column_oid == _IPNETTOMEDIA_PHYS:
            return dict(phys or {})
        if column_oid == _IPNETTOMEDIA_ADDR:
            return dict(addrs or {})
        return {}

    monkeypatch.setattr(discovery, "_snmp_walk_column", fake_walk)
    return calls


async def test_scan_resolves_mac_via_router_arp_when_mac_unknown(db_session, monkeypatch):
    """MAC absente de l'ARP local et du SNMP de l'hôte → table ARP du routeur."""
    from app.services.it_asset import ArpTableResolver

    ArpTableResolver.clear_cache()
    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab ARP",
        "cidr": "192.168.79.0/30",
        "snmp_enabled": True,
        "snmp_community": "public",
        "snmp_version": "v2c",
    })

    # Hôte joignable mais : ARP local vide, SNMP de l'équipement sans MAC
    # (cas du NAS : ifTable = loopback seul)
    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.79.1"},
        mac_by_ip={},
        snmp_by_ip={
            "192.168.79.1": {
                "1.3.6.1.2.1.1.1.0": "Linux NAS-DESIGN",
                "1.3.6.1.2.1.1.5.0": "NAS-DESIGN",
            }
        },
    )
    _patch_arp_settings(monkeypatch)
    walk_calls = _patch_arp_walk(
        monkeypatch,
        discovery,
        phys={"1.192.168.79.1": "aa:bb:cc:dd:ee:77"},
        addrs={"1.192.168.79.1": "192.168.79.1"},
    )

    result = await discovery.scan_network_range(network_range.id)

    assert result["assets_created"] == 1
    assert walk_calls["n"] == 2  # deux colonnes (phys + adresse), une seule passe
    asset = await service.get_it_asset_by_ip("192.168.79.1")
    assert asset.mac_address == "aa:bb:cc:dd:ee:77"  # MAC venue de la table du routeur
    assert asset.name == "NAS-DESIGN"


async def test_scan_never_overwrites_directly_discovered_mac(db_session, monkeypatch):
    """Priorité : MAC découverte directement (ARP local) → routeur jamais sollicité."""
    from app.services.it_asset import ArpTableResolver

    ArpTableResolver.clear_cache()
    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab ARP 2",
        "cidr": "192.168.80.0/30",
        "snmp_enabled": False,
    })

    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.80.1"},
        mac_by_ip={"192.168.80.1": "aa:bb:cc:dd:ee:01"},  # ARP local
        snmp_by_ip={},
    )
    _patch_arp_settings(monkeypatch)
    walk_calls = _patch_arp_walk(
        monkeypatch,
        discovery,
        phys={"1.192.168.80.1": "ff:ff:ff:ff:ff:99"},  # MAC routeur (différente)
        addrs={"1.192.168.80.1": "192.168.80.1"},
    )

    result = await discovery.scan_network_range(network_range.id)

    assert result["assets_created"] == 1
    assert walk_calls["n"] == 0  # le routeur n'est jamais interrogé
    asset = await service.get_it_asset_by_ip("192.168.80.1")
    assert asset.mac_address == "aa:bb:cc:dd:ee:01"  # MAC directe préservée


async def test_scan_survives_arp_resolver_failure(db_session, monkeypatch):
    """Routeur indisponible : le scan se termine, l'asset est créé sans MAC."""
    from app.services.it_asset import ArpTableResolver

    ArpTableResolver.clear_cache()
    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab ARP 3",
        "cidr": "192.168.81.0/30",
        "snmp_enabled": False,
    })

    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.81.1"},
        mac_by_ip={},
        snmp_by_ip={},
    )
    _patch_arp_settings(monkeypatch)
    _patch_arp_walk(monkeypatch, discovery, error=TimeoutError("pfSense injoignable"))

    result = await discovery.scan_network_range(network_range.id)

    assert result["hosts_scanned"] == 2
    assert result["assets_created"] == 1  # le scan n'a pas échoué
    asset = await service.get_it_asset_by_ip("192.168.81.1")
    assert asset.mac_address is None  # MAC inconnue, asset malgré tout créé


async def test_scan_skips_resolver_when_not_configured(db_session, monkeypatch):
    """Sans IT_ARP_RESOLVER_ENABLED, le résolveur n'est pas construit (statu quo)."""
    from app.services.it_asset import ArpTableResolver

    ArpTableResolver.clear_cache()
    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab ARP 4",
        "cidr": "192.168.82.0/30",
        "snmp_enabled": False,
    })

    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.82.1"},
        mac_by_ip={},
        snmp_by_ip={},
    )
    _patch_arp_settings(monkeypatch, enabled=False)
    walk_calls = _patch_arp_walk(
        monkeypatch,
        discovery,
        phys={"1.192.168.82.1": "aa:bb:cc:dd:ee:02"},
        addrs={"1.192.168.82.1": "192.168.82.1"},
    )

    result = await discovery.scan_network_range(network_range.id)

    assert result["assets_created"] == 1
    assert walk_calls["n"] == 0  # aucun sondage SNMP routeur
    asset = await service.get_it_asset_by_ip("192.168.82.1")
    assert asset.mac_address is None


async def test_scan_assigns_network_range_room_to_discovered_asset(db_session, monkeypatch):
    """Vérifier que la plage réseau retient son local et que les équipements découverts en héritent."""
    room = await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Plage Salle 101",
        "cidr": "192.168.83.0/30",
        "room_id": room.id,
        "snmp_enabled": False,
    })

    assert network_range.room_id == room.id
    assert network_range.room is not None
    assert network_range.room.reference == "R-101"

    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.83.1"},
        mac_by_ip={"192.168.83.1": "aa:bb:cc:dd:ee:83"},
        snmp_by_ip={},
    )

    result = await discovery.scan_network_range(network_range.id)
    assert result["assets_created"] == 1

    asset = await service.get_it_asset_by_ip("192.168.83.1")
    assert asset is not None
    assert asset.room_id == room.id
    assert asset.room is not None
    assert asset.room.reference == "R-101"


# ============================================================
# Tests Poste Windows : Wake-on-LAN, Shutdown et RDP
# ============================================================


def test_wake_on_lan_magic_packet(monkeypatch):
    """Vérifier la création et l'envoi du paquet magique WoL."""
    packets_sent = []

    class MockSocket:
        def __init__(self, *args, **kwargs):
            pass
        def setsockopt(self, *args):
            pass
        def sendto(self, packet, addr):
            packets_sent.append((packet, addr))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import socket
    monkeypatch.setattr(socket, "socket", MockSocket)

    res = send_wake_on_lan("aa:bb:cc:dd:ee:ff", broadcast_ips=["192.168.1.255"])
    assert res is True
    assert len(packets_sent) >= 2
    raw_packet, addr = packets_sent[0]
    # 6 octets 0xff + 16 * 6 octets de MAC = 102 octets
    assert len(raw_packet) == 102
    assert raw_packet[:6] == b"\xff" * 6
    assert raw_packet[6:12] == bytes.fromhex("aabbccddeeff")


def test_wake_on_lan_invalid_mac():
    with pytest.raises(ValueError, match="Adresse MAC invalide"):
        send_wake_on_lan("invalid-mac")


def test_generate_rdp_file_content():
    content = generate_rdp_file_content("192.168.1.50", "PC-COMPTA-01")
    assert "full address:s:192.168.1.50" in content
    assert "prompt for credentials:i:1" in content
    assert "screen mode id:i:2" in content


async def test_shutdown_windows_host_custom_cmd(monkeypatch):
    """Vérifier l'exécution d'une commande personnalisée via IT_SHUTDOWN_COMMAND."""
    monkeypatch.setenv("IT_SHUTDOWN_COMMAND", "echo shutdown {ip}")
    success, msg = await shutdown_windows_host("192.168.1.50", force=True)
    assert success is True
    assert "succès" in msg


async def test_service_wake_and_rdp_windows_asset(db_session, monkeypatch):
    """Vérifier wake_asset et generate_rdp_content depuis le service."""
    monkeypatch.setattr("app.services.it_asset.send_wake_on_lan", lambda mac, ips=None: True)

    service = ITAssetService(db_session)
    asset = await service.create_it_asset({
        "name": "PC-WINDOWS-SECRETARIAT",
        "asset_type": "pc_windows",
        "ip_address": "192.168.10.42",
        "mac_address": "00:11:22:33:44:55",
    })

    # Test wake
    success, message, mac = await service.wake_asset(asset.id)
    assert success is True
    assert mac == "00:11:22:33:44:55"
    assert "Wake-on-LAN" in message

    # Test RDP
    rdp_content, filename = await service.generate_rdp_content(asset.id)
    assert "192.168.10.42" in rdp_content
    assert filename.endswith(".rdp")


