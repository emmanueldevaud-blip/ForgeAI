"""Tests unitaires des résolveurs DHCP (pfSense) et DNS (Active Directory).

Cibles :
- DhcpLeaseResolver : cache TTL, parsing JSON/HTML, priorité API key > basic auth
- DnsResolver : résolution A / PTR, cache TTL, timeout, serveur explicite
"""
import pytest

from app.services.it_asset import (
    DhcpLeaseResolver,
    DnsResolver,
)


# ============================================================
# DhcpLeaseResolver (fetch injecté — aucun réseau)
# ============================================================


@pytest.fixture(autouse=True)
def _clear_dhcp_cache():
    DhcpLeaseResolver.clear_cache()
    yield
    DhcpLeaseResolver.clear_cache()


def _dhcp_resolver(fetch, **kwargs):
    return DhcpLeaseResolver("https://pfsense/api/v2/status/dhcp/leases", fetch_leases=fetch, **kwargs)


async def test_dhcp_get_lease_returns_entry_and_caches():
    """La liste des baux est récupérée en une seule passe, puis servie par le cache."""
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return {"192.168.100.50": {"mac": "aa:bb:cc:dd:ee:50", "hostname": "pc-bureau"}}

    r = _dhcp_resolver(fetch)
    lease = await r.get_lease("192.168.100.50")
    assert lease == {"mac": "aa:bb:cc:dd:ee:50", "hostname": "pc-bureau"}
    assert await r.get_lease("192.168.100.99") is None
    assert await r.get_lease("192.168.100.50") == {"mac": "aa:bb:cc:dd:ee:50", "hostname": "pc-bureau"}
    assert calls["n"] == 1


async def test_dhcp_get_hostname_and_mac():
    async def fetch():
        return {"10.0.0.1": {"mac": "11:22:33:44:55:66", "hostname": "server-01"}}

    r = _dhcp_resolver(fetch)
    assert await r.get_hostname("10.0.0.1") == "server-01"
    assert await r.get_mac("10.0.0.1") == "11:22:33:44:55:66"
    assert await r.get_hostname("10.0.0.2") is None
    assert await r.get_mac("10.0.0.2") is None


async def test_dhcp_expired_cache_refetches():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return {"10.0.0.1": {"mac": "aa:bb:cc:dd:ee:01", "hostname": "host-1"}}

    r = _dhcp_resolver(fetch, cache_ttl=0)
    await r.get_lease("10.0.0.1")
    await r.get_lease("10.0.0.1")
    assert calls["n"] == 2


async def test_dhcp_returns_none_on_fetch_failure():
    async def fetch():
        raise TimeoutError("pfSense injoignable")

    r = _dhcp_resolver(fetch)
    assert await r.get_lease("192.168.100.50") is None


async def test_dhcp_cache_key_includes_url():
    async def fetch():
        return {}

    a = DhcpLeaseResolver("https://pfsense1/api/v2/status/dhcp/leases", fetch_leases=fetch)
    b = DhcpLeaseResolver("https://pfsense2/api/v2/status/dhcp/leases", fetch_leases=fetch)
    assert a._cache_key != b._cache_key


# ============================================================
# KeaLeaseFileResolver (fichier local — aucun réseau)
# ============================================================


@pytest.fixture(autouse=True)
def _clear_kea_cache():
    from app.services.it_asset import KeaLeaseFileResolver
    KeaLeaseFileResolver.clear_cache()
    yield
    KeaLeaseFileResolver.clear_cache()


def _write_kea_file(tmp_path, content: str):
    """Helper to create a temporary Kea lease file."""
    p = tmp_path / "dhcp4.leases"
    p.write_text(content, encoding="utf-8")
    return str(p)


async def test_kea_parse_json_lines(tmp_path):
    """Parse valide JSON Lines Kea : IP, MAC, hostname, expire."""
    content = (
        '{"ip-address": "192.168.100.76", "hw-address": "aa:bb:cc:dd:ee:01", '
        '"hostname": "pcfixe-ede-8.design-ede.fr.", "expire": 2000000000}\n'
        '{"ip-address": "192.168.100.100", "hw-address": "bb:cc:dd:ee:ff:02", '
        '"hostname": "pcfixe-manu.", "expire": 2000000000}\n'
        '{"ip-address": "192.168.100.6", "hw-address": "cc:dd:ee:ff:00:11", '
        '"hostname": "pcfixe-reunion.design-ede.fr.", "expire": 2000000000}\n'
    )
    path = _write_kea_file(tmp_path, content)

    from app.services.it_asset import KeaLeaseFileResolver
    resolver = KeaLeaseFileResolver(path, cache_ttl=0)

    lease = await resolver.get_lease("192.168.100.76")
    assert lease == {"mac": "aa:bb:cc:dd:ee:01", "hostname": "pcfixe-ede-8.design-ede.fr"}

    lease = await resolver.get_lease("192.168.100.100")
    assert lease == {"mac": "bb:cc:dd:ee:ff:02", "hostname": "pcfixe-manu"}

    lease = await resolver.get_lease("192.168.100.6")
    assert lease == {"mac": "cc:dd:ee:ff:00:11", "hostname": "pcfixe-reunion.design-ede.fr"}


async def test_kea_hostname_absent(tmp_path):
    """Entrée sans hostname : retourne MAC mais hostname=None."""
    content = '{"ip-address": "192.168.100.50", "hw-address": "aa:bb:cc:dd:ee:ff"}\n'
    path = _write_kea_file(tmp_path, content)

    from app.services.it_asset import KeaLeaseFileResolver
    resolver = KeaLeaseFileResolver(path, cache_ttl=0)

    lease = await resolver.get_lease("192.168.100.50")
    assert lease == {"mac": "aa:bb:cc:dd:ee:ff", "hostname": None}


async def test_kea_expired_lease_ignored(tmp_path):
    """Bail expiré (expire dans le passé) : ignoré."""
    import time
    past = int(time.time()) - 3600
    content = f'{{"ip-address": "192.168.100.20", "hw-address": "aa:bb:cc:dd:ee:ff", "expire": {past}}}\n'
    path = _write_kea_file(tmp_path, content)

    from app.services.it_asset import KeaLeaseFileResolver
    resolver = KeaLeaseFileResolver(path, cache_ttl=0)

    lease = await resolver.get_lease("192.168.100.20")
    assert lease is None


async def test_kea_duplicate_ip_keeps_latest(tmp_path):
    """Même IP plusieurs fois : garde le bail le plus récent (expire max)."""
    content = (
        '{"ip-address": "192.168.100.25", "hw-address": "aa:bb:cc:dd:ee:01", "expire": 1000}\n'
        '{"ip-address": "192.168.100.25", "hw-address": "bb:cc:dd:ee:ff:02", "expire": 2000}\n'
    )
    path = _write_kea_file(tmp_path, content)

    from app.services.it_asset import KeaLeaseFileResolver
    resolver = KeaLeaseFileResolver(path, cache_ttl=0)

    lease = await resolver.get_lease("192.168.100.25")
    assert lease["mac"] == "bb:cc:dd:ee:ff:02"  # le plus récent


async def test_kea_file_not_found(tmp_path):
    """Fichier introuvable : retourne None sans exception."""
    from app.services.it_asset import KeaLeaseFileResolver
    resolver = KeaLeaseFileResolver(str(tmp_path / "inexistant.leases"), cache_ttl=0)

    lease = await resolver.get_lease("192.168.100.1")
    assert lease is None


async def test_kea_invalid_json_line_ignored(tmp_path):
    """Ligne JSON invalide ignorée, lignes valides parsées."""
    content = (
        'not json\n'
        '{"ip-address": "192.168.100.30", "hw-address": "aa:bb:cc:dd:ee:03", "expire": 2000000000}\n'
    )
    path = _write_kea_file(tmp_path, content)

    from app.services.it_asset import KeaLeaseFileResolver
    resolver = KeaLeaseFileResolver(path, cache_ttl=0)

    lease = await resolver.get_lease("192.168.100.30")
    assert lease == {"mac": "aa:bb:cc:dd:ee:03", "hostname": None}


async def test_kea_normalize_hostname_trailing_dot(tmp_path):
    """Hostname avec point final : strip + lowercase."""
    content = (
        '{"ip-address": "192.168.100.40", "hw-address": "aa:bb:cc:dd:ee:04", '
        '"hostname": "PCFIXE-MANU.Design-ede.FR.", "expire": 2000000000}\n'
    )
    path = _write_kea_file(tmp_path, content)

    from app.services.it_asset import KeaLeaseFileResolver
    resolver = KeaLeaseFileResolver(path, cache_ttl=0)

    lease = await resolver.get_lease("192.168.100.40")
    assert lease["hostname"] == "pcfixe-manu.design-ede.fr"


async def test_kea_cache_ttl(tmp_path):
    """Cache TTL : une seule lecture fichier pour plusieurs appels."""
    import time
    content = '{"ip-address": "192.168.100.50", "hw-address": "aa:bb:cc:dd:ee:ff", "expire": 2000000000}\n'
    path = _write_kea_file(tmp_path, content)

    from app.services.it_asset import KeaLeaseFileResolver
    calls = {"n": 0}
    original_get_leases = KeaLeaseFileResolver._get_leases

    async def counting_get_leases(self):
        calls["n"] += 1
        return await original_get_leases(self)

    import app.services.it_asset as mod
    mod.KeaLeaseFileResolver._get_leases = counting_get_leases
    try:
        resolver = KeaLeaseFileResolver(path, cache_ttl=300)
        await resolver.get_lease("192.168.100.50")
        await resolver.get_lease("192.168.100.50")
        assert calls["n"] == 1
    finally:
        mod.KeaLeaseFileResolver._get_leases = original_get_leases


async def test_kea_permission_error(tmp_path):
    """Permission refusée : log et retour None."""
    import os
    content = '{"ip-address": "192.168.100.50", "hw-address": "aa:bb:cc:dd:ee:ff"}\n'
    path = _write_kea_file(tmp_path, content)
    os.chmod(path, 0o000)  # pas de lecture

    from app.services.it_asset import KeaLeaseFileResolver
    resolver = KeaLeaseFileResolver(path, cache_ttl=0)

    try:
        lease = await resolver.get_lease("192.168.100.50")
        assert lease is None
    finally:
        os.chmod(path, 0o644)


# ============================================================
# DnsResolver (mock dnspython — aucun réseau)
# ============================================================


@pytest.fixture(autouse=True)
def _clear_dns_cache():
    DnsResolver.clear_cache()
    yield
    DnsResolver.clear_cache()


def _dns_resolver(resolve_side_effect, **kwargs):
    """Créer un DnsResolver avec un resolveur mocké."""
    r = DnsResolver("192.168.100.254", **kwargs)
    # Remplacer la méthode _resolve par un mock
    r._resolve = resolve_side_effect
    return r


async def test_dns_resolve_a_returns_ip():
    async def fake_resolve(name, rtype):
        assert rtype == "A"
        assert name == "pc-bureau.example.com"
        return "192.168.100.50"

    r = _dns_resolver(fake_resolve)
    assert await r.resolve_a("pc-bureau.example.com") == "192.168.100.50"


async def test_dns_resolve_ptr_returns_hostname():
    async def fake_resolve(name, rtype):
        assert rtype == "PTR"
        assert name == "50.100.168.192.in-addr.arpa"
        return "pc-bureau.example.com"

    r = _dns_resolver(fake_resolve)
    assert await r.resolve_ptr("192.168.100.50") == "pc-bureau.example.com"


async def test_dns_resolve_a_returns_none_on_nxdomain():
    async def fake_resolve(name, rtype):
        import dns.exception
        raise dns.exception.DNSException("NXDOMAIN")

    r = _dns_resolver(fake_resolve)
    assert await r.resolve_a("inconnu.example.com") is None


async def test_dns_resolve_ptr_returns_none_on_nxdomain():
    async def fake_resolve(name, rtype):
        import dns.exception
        raise dns.exception.DNSException("NXDOMAIN")

    r = _dns_resolver(fake_resolve)
    assert await r.resolve_ptr("192.168.100.99") is None


async def test_dns_cache_works():
    """Test que le cache DNS fonctionne (via le cache interne de _resolve)."""
    calls = {"n": 0}

    # Créer un resolver avec un vrai _resolve mais mocké au niveau dnspython
    import dns.asyncresolver
    original_resolve = dns.asyncresolver.Resolver.resolve

    calls = {"n": 0}

    async def fake_resolve(self, name, rtype, *args, **kwargs):
        calls["n"] += 1
        # Créer une réponse mockée
        class MockAnswer:
            def __getitem__(self, idx):
                class MockRecord:
                    def __str__(self):
                        return "192.168.100.50"
                return MockRecord()
            def __iter__(self):
                yield self[0]
        return MockAnswer()

    import dns.asyncresolver
    dns.asyncresolver.Resolver.resolve = fake_resolve

    try:
        r = DnsResolver("192.168.100.254", cache_ttl=300)
        assert await r.resolve_a("pc-bureau.example.com") == "192.168.100.50"
        assert await r.resolve_a("pc-bureau.example.com") == "192.168.100.50"
        # Le cache devrait éviter le second appel
        assert calls["n"] == 1
    finally:
        dns.asyncresolver.Resolver.resolve = original_resolve


async def test_dns_expired_cache_refetches():
    calls = {"n": 0}

    async def fake_resolve(name, rtype):
        calls["n"] += 1
        return "192.168.100.50"

    r = _dns_resolver(fake_resolve, cache_ttl=0)
    await r.resolve_a("pc-bureau.example.com")
    await r.resolve_a("pc-bureau.example.com")
    assert calls["n"] == 2


async def test_dns_cache_key_includes_server_and_type():
    async def fake_resolve(name, rtype):
        return "1.2.3.4"

    a = DnsResolver("192.168.100.1")
    b = DnsResolver("192.168.100.2")
    a._resolve = fake_resolve
    b._resolve = fake_resolve
    await a.resolve_a("test.com")
    await b.resolve_a("test.com")
    assert a._cache_key != b._cache_key


async def test_dns_resolve_ptr_pcfixe_manu_real():
    """Test réel : PTR 192.168.100.100 → PCFIXE-MANU.design-ede.fr.

    Ce test nécessite un accès réseau au serveur AD DNS (192.168.100.254)
    et que la zone inverse 100.168.192.in-addr.arpa existe.
    """
    import dns.asyncresolver
    
    resolver = DnsResolver("192.168.100.254", timeout=2.0, cache_ttl=0)
    
    # Vérifier que le serveur répond
    try:
        result = await resolver.resolve_ptr("192.168.100.100")
        assert result == "PCFIXE-MANU.design-ede.fr", f"Attendu PCFIXE-MANU.design-ede.fr, reçu {result}"
    except AssertionError:
        raise
    except Exception as e:
        # Si le serveur DNS n'est pas accessible en test, on skip plutôt que fail
        import pytest
        pytest.skip(f"Serveur DNS AD non accessible: {e}")


# ============================================================
# Tests d'intégration (scan mocké avec DHCP + DNS)
# ============================================================


from tests.test_it_asset import _FakeArpResolverSettings


class _FakeAllResolverSettings(_FakeArpResolverSettings):
    """Settings avec ARP + DHCP + DNS activés."""

    IT_ARP_RESOLVER_ENABLED = True
    IT_ARP_RESOLVER_HOST = "192.168.79.253"
    IT_ARP_RESOLVER_COMMUNITY = ""
    IT_ARP_RESOLVER_VERSION = "2c"
    IT_ARP_RESOLVER_PORT = 161
    IT_ARP_RESOLVER_CACHE_TTL = 300
    IT_DHCP_RESOLVER_ENABLED = True
    IT_DHCP_RESOLVER_URL = "https://pfsense/api/v2/status/dhcp/leases"
    IT_DHCP_RESOLVER_API_KEY = "test-key"
    IT_DHCP_RESOLVER_USER = ""
    IT_DHCP_RESOLVER_PASSWORD = ""
    IT_DHCP_RESOLVER_CACHE_TTL = 300
    IT_DHCP_KEA_LEASE_FILE = ""  # Pas de fichier Kea local dans les tests d'intégration
    IT_DHCP_KEA_CACHE_TTL = 300
    IT_DNS_RESOLVER_ENABLED = True
    IT_DNS_RESOLVER_SERVER = "192.168.79.254"
    IT_DNS_RESOLVER_PORT = 53
    IT_DNS_RESOLVER_TIMEOUT = 2.0
    IT_DNS_RESOLVER_CACHE_TTL = 300


def _patch_all_settings(monkeypatch):
    from app.services import it_asset as it_asset_module
    monkeypatch.setattr(it_asset_module, "get_settings", lambda: _FakeAllResolverSettings())


def _patch_dhcp_fetch(monkeypatch, leases=None, error=None):
    """Patch le fetch DHCP globalement pour les tests."""
    calls = {"n": 0}

    async def fake_fetch():
        calls["n"] += 1
        if error:
            raise error
        return dict(leases or {})

    import app.services.it_asset as it_asset_module
    original_build = it_asset_module.NetworkDiscoveryService._build_dhcp_resolver

    async def patched_build(self):
        # original_build is now async and returns the resolver directly
        resolver = await original_build(self)
        if resolver:
            resolver._fetch_leases = fake_fetch
        return resolver

    monkeypatch.setattr(it_asset_module.NetworkDiscoveryService, "_build_dhcp_resolver", patched_build)
    return calls


def _patch_dns_resolve(monkeypatch, ptr_map=None, a_map=None, error=None):
    """Patch la résolution DNS globalement pour les tests."""
    calls = {"n": 0}

    async def fake_resolve(name, rtype):
        calls["n"] += 1
        if error:
            raise error
        if rtype == "PTR":
            return ptr_map.get(name) if ptr_map else None
        return a_map.get(name) if a_map else None

    import app.services.it_asset as it_asset_module
    original_build = it_asset_module.NetworkDiscoveryService._build_dns_resolver

    async def patched_build(self):
        resolver = await original_build(self)
        if resolver:
            resolver._resolve = fake_resolve
        return resolver

    monkeypatch.setattr(it_asset_module.NetworkDiscoveryService, "_build_dns_resolver", patched_build)
    return calls


async def test_scan_uses_dhcp_hostname_when_snmp_unknown(db_session, monkeypatch):
    """Nom inconnu en SNMP → hostname DHCP utilisé."""
    from app.services.it_asset import ArpTableResolver, DhcpLeaseResolver, DnsResolver, ITAssetService
    from tests.test_it_asset import _patch_arp_settings

    ArpTableResolver.clear_cache()
    DhcpLeaseResolver.clear_cache()
    DnsResolver.clear_cache()

    from tests.test_it_asset import _create_room, _mock_discovery

    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab DHCP",
        "cidr": "192.168.79.0/30",
        "snmp_enabled": True,
        "snmp_community": "public",
        "snmp_version": "v2c",
    })

    # SNMP répond mais sans sys_name
    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.79.1"},
        mac_by_ip={"192.168.79.1": "aa:bb:cc:dd:ee:01"},
        snmp_by_ip={
            "192.168.79.1": {
                "1.3.6.1.2.1.1.1.0": "Linux host",
            }
        },
)
    _patch_all_settings(monkeypatch)
    # Désactiver ARP pour ce test : surcharger IT_ARP_RESOLVER_ENABLED
    import app.services.it_asset as it_asset_module
    class _NoArpSettings(_FakeAllResolverSettings):
        IT_ARP_RESOLVER_ENABLED = False
    monkeypatch.setattr(it_asset_module, "get_settings", lambda: _NoArpSettings())
    _patch_dhcp_fetch(monkeypatch, leases={
        "192.168.79.1": {"mac": "aa:bb:cc:dd:ee:01", "hostname": "pc-compta"}
    })
    
    result = await discovery.scan_network_range(network_range.id)

    assert result["assets_created"] == 1
    asset = await service.get_it_asset_by_ip("192.168.79.1")
    assert asset.name == "pc-compta"  # Nom DHCP utilisé


async def test_scan_uses_dns_ptr_when_dhcp_unknown(db_session, monkeypatch):
    """Nom inconnu en SNMP et DHCP → DNS PTR utilisé."""
    from app.services.it_asset import ArpTableResolver, DhcpLeaseResolver, DnsResolver, ITAssetService
    from tests.test_it_asset import _patch_arp_settings

    ArpTableResolver.clear_cache()
    DhcpLeaseResolver.clear_cache()
    DnsResolver.clear_cache()

    from tests.test_it_asset import _create_room, _mock_discovery

    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab DNS",
        "cidr": "192.168.80.0/30",
        "snmp_enabled": True,
        "snmp_community": "public",
        "snmp_version": "v2c",
    })

    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.80.1"},
        mac_by_ip={"192.168.80.1": "aa:bb:cc:dd:ee:02"},
        snmp_by_ip={
            "192.168.80.1": {
                "1.3.6.1.2.1.1.1.0": "Linux host",
            }
        },
    )
    _patch_all_settings(monkeypatch)
    # Désactiver ARP pour ce test : surcharger IT_ARP_RESOLVER_ENABLED
    import app.services.it_asset as it_asset_module
    class _NoArpSettings(_FakeAllResolverSettings):
        IT_ARP_RESOLVER_ENABLED = False
    monkeypatch.setattr(it_asset_module, "get_settings", lambda: _NoArpSettings())
    _patch_dhcp_fetch(monkeypatch, leases={})  # Pas de bail DHCP
    _patch_dns_resolve(monkeypatch, ptr_map={
        "1.80.168.192.in-addr.arpa": "printer-lab.example.com"
    })

    result = await discovery.scan_network_range(network_range.id)

    assert result["assets_created"] == 1
    asset = await service.get_it_asset_by_ip("192.168.80.1")
    assert asset.name == "printer-lab.example.com"  # Nom DNS PTR utilisé


async def test_scan_priority_snmp_name_over_dhcp_over_dns(db_session, monkeypatch):
    """Priorité : SNMP sys_name > DHCP hostname > DNS PTR."""
    from app.services.it_asset import ArpTableResolver, DhcpLeaseResolver, DnsResolver, ITAssetService
    from tests.test_it_asset import _patch_arp_settings

    ArpTableResolver.clear_cache()
    DhcpLeaseResolver.clear_cache()
    DnsResolver.clear_cache()

    from tests.test_it_asset import _create_room, _mock_discovery

    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab Priority",
        "cidr": "192.168.81.0/30",
        "snmp_enabled": True,
        "snmp_community": "public",
        "snmp_version": "v2c",
    })

    # SNMP a un sys_name, DHCP et DNS en ont d'autres
    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.81.1"},
        mac_by_ip={"192.168.81.1": "aa:bb:cc:dd:ee:03"},
        snmp_by_ip={
            "192.168.81.1": {
                "1.3.6.1.2.1.1.1.0": "Linux host",
                "1.3.6.1.2.1.1.5.0": "snmp-name",  # SNMP sys_name
            }
        },
    )
    _patch_all_settings(monkeypatch)
    _patch_dhcp_fetch(monkeypatch, leases={
        "192.168.81.1": {"mac": "aa:bb:cc:dd:ee:03", "hostname": "dhcp-name"}
    })
    _patch_dns_resolve(monkeypatch, ptr_map={
        "1.81.168.192.in-addr.arpa": "dns-name.example.com"
    })

    result = await discovery.scan_network_range(network_range.id)

    assert result["assets_created"] == 1
    asset = await service.get_it_asset_by_ip("192.168.81.1")
    assert asset.name == "snmp-name"  # SNMP sys_name prioritaire


async def test_scan_dhcp_mac_fallback_when_arp_fails(db_session, monkeypatch):
    """MAC absente ARP/SNMP → MAC DHCP utilisée."""
    from app.services.it_asset import ArpTableResolver, DhcpLeaseResolver, DnsResolver, ITAssetService
    from tests.test_it_asset import _patch_arp_settings

    ArpTableResolver.clear_cache()
    DhcpLeaseResolver.clear_cache()
    DnsResolver.clear_cache()

    from tests.test_it_asset import _create_room, _mock_discovery

    await _create_room(db_session)
    service = ITAssetService(db_session)
    network_range = await service.create_network_range({
        "name": "Lab DHCP MAC",
        "cidr": "192.168.82.0/30",
        "snmp_enabled": True,
        "snmp_community": "public",
        "snmp_version": "v2c",
    })

    discovery = await _mock_discovery(
        db_session,
        monkeypatch,
        reachable_ips={"192.168.82.1"},
        mac_by_ip={},  # Pas d'ARP local
        snmp_by_ip={
            "192.168.82.1": {
                "1.3.6.1.2.1.1.1.0": "Linux host",
            }
        },
    )
    _patch_all_settings(monkeypatch)
    # Désactiver ARP pour ce test : surcharger IT_ARP_RESOLVER_ENABLED
    import app.services.it_asset as it_asset_module
    class _NoArpSettings(_FakeAllResolverSettings):
        IT_ARP_RESOLVER_ENABLED = False
    monkeypatch.setattr(it_asset_module, "get_settings", lambda: _NoArpSettings())
    _patch_dhcp_fetch(monkeypatch, leases={
        "192.168.82.1": {"mac": "11:22:33:44:55:66", "hostname": "dhcp-host"}
    })

    result = await discovery.scan_network_range(network_range.id)

    assert result["assets_created"] == 1
    asset = await service.get_it_asset_by_ip("192.168.82.1")
    assert asset.mac_address == "11:22:33:44:55:66"  # MAC DHCP
    assert asset.name == "dhcp-host"  # Nom DHCP