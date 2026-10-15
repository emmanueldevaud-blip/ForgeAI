"""Tests unitaires de la résolution MAC croisée via table ARP SNMP (routeur/pfSense).

Cibles :
- conversion octets SNMP -> notation aa:bb:cc:dd:ee:ff ;
- jointure des colonnes MAC/IP de la table ipNetToMedia par index de ligne ;
- cache TTL : une seule passe ARP par scan, pas un sondage par hôte ;
- entrées absentes, erreurs SNMP et routeur indisponible : jamais d'exception ;
- la communauté SNMP ne fuite ni dans la clé de cache ni dans les logs.
"""
import pytest

from app.services.it_asset import (
    ArpTableResolver,
    _arp_columns_to_map,
    _parse_mac_octets,
)


# ============================================================
# Helpers purs (aucun réseau, aucune DB)
# ============================================================


def test_parse_mac_octets_binary_to_colon_hex():
    # Format attendu : notation standard aa:bb:cc:dd:ee:ff, minuscules
    assert _parse_mac_octets(bytes([0x00, 0x11, 0x32, 0x42, 0xC1, 0xFC])) == "00:11:32:42:c1:fc"
    assert _parse_mac_octets(bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])) == "ff:ff:ff:ff:ff:ff"


def test_parse_mac_octets_rejects_empty_wrong_size_and_zeros():
    assert _parse_mac_octets(None) is None
    assert _parse_mac_octets(b"") is None
    assert _parse_mac_octets(b"\x01\x02\x03") is None  # taille incorrecte
    assert _parse_mac_octets(b"\x00" * 6) is None  # 00:00:00:00:00:00 = non résolue


def test_arp_columns_to_map_joins_on_line_index():
    # Indexs au format ifIndex.IP (pfSense/net-snmp) : la jointure se fait
    # sur l'index commun, la colonne IP fournit l'adresse de destination
    phys = {
        "2.192.168.100.250": "00:11:32:42:c1:fc",
        "12.192.168.100.29": "84:a9:3e:8b:5e:47",
    }
    addrs = {
        "2.192.168.100.250": "192.168.100.250",
        "12.192.168.100.29": "192.168.100.29",
    }
    assert _arp_columns_to_map(phys, addrs) == {
        "192.168.100.250": "00:11:32:42:c1:fc",
        "192.168.100.29": "84:a9:3e:8b:5e:47",
    }


def test_arp_columns_to_map_skips_rows_without_counterpart():
    # MAC sans IP correspondante, IP sans MAC, indexs disjoints : ignorés
    assert _arp_columns_to_map({"1.10.0.0.1": "aa:bb:cc:dd:ee:01"}, {}) == {}
    assert _arp_columns_to_map({}, {"1.10.0.0.1": "10.0.0.1"}) == {}
    assert _arp_columns_to_map({"a": "aa:bb:cc:dd:ee:01"}, {"b": "10.0.0.1"}) == {}


# ============================================================
# ArpTableResolver (fetch injecté — aucun accès réseau)
# ============================================================


@pytest.fixture(autouse=True)
def _clear_arp_cache():
    ArpTableResolver.clear_cache()
    yield
    ArpTableResolver.clear_cache()


def _resolver(fetch, **kwargs):
    return ArpTableResolver("192.168.100.253", "design", fetch_table=fetch, **kwargs)


async def test_get_mac_returns_entry_and_caches_single_fetch():
    """La table ARP est récupérée en une seule passe, puis servie par le cache."""
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return {"192.168.100.250": "00:11:32:42:c1:fc"}

    r = _resolver(fetch)
    assert await r.get_mac("192.168.100.250") == "00:11:32:42:c1:fc"
    assert await r.get_mac("192.168.100.42") is None  # entrée absente de la table
    assert await r.get_mac("192.168.100.250") == "00:11:32:42:c1:fc"
    assert calls["n"] == 1  # un seul sondage routeur pour 3 résolutions


async def test_get_mac_expired_cache_refetches():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return {"10.0.0.1": "aa:bb:cc:dd:ee:01"}

    r = _resolver(fetch, cache_ttl=0)  # TTL nul : cache toujours expiré
    await r.get_mac("10.0.0.1")
    await r.get_mac("10.0.0.1")
    assert calls["n"] == 2


async def test_get_mac_returns_none_when_fetch_fails():
    """Routeur indisponible / timeout SNMP : None, jamais d'exception."""

    async def fetch():
        raise TimeoutError("routeur injoignable")

    r = _resolver(fetch)
    assert await r.get_mac("192.168.100.250") is None


async def test_get_mac_returns_none_without_fetch_callable():
    r = ArpTableResolver("192.168.100.253", "design")
    assert await r.get_mac("192.168.100.250") is None


async def test_cache_key_ignores_community_and_differs_by_host():
    """La communauté SNMP n'entre pas dans la clé de cache (et n'est jamais loguée)."""

    async def fetch():
        return {}

    a = ArpTableResolver("192.168.100.253", "design", fetch_table=fetch)
    b = ArpTableResolver("192.168.100.253", "autre-communaute", fetch_table=fetch)
    assert a._cache_key == b._cache_key
    assert "design" not in a._cache_key
    c = ArpTableResolver("192.168.100.254", "design", fetch_table=fetch)
    assert c._cache_key != a._cache_key
