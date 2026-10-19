import math
import asyncio
import socket
import subprocess
import platform
import json
import os
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Network, IPv6Network, IPv4Address, IPv6Address
from typing import Optional, List, Tuple

from sqlalchemy import select, func, or_, and_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ITAsset, ITAssetType, NetworkRange, DiscoveryLog, AssetObservation, ITAlert, ITAssetHistory, Room, Building, Site, ITAlertType, ITAlertSeverity
from app.models.user import User
from app.services.audit import AuditService
from app.core.config import get_settings


# Désactiver le chargement des MIB PySNMP (erreurs MibNotFoundError dans le
# callback dispatcher) : on utilise exclusivement les OID numériques.
# Le patch au niveau classe affecte aussi le dispatcher asynchrone.
from pysnmp.smi.builder import MibBuilder
from pysnmp.smi import error as _pysnmp_error

_original_import_symbols = MibBuilder.import_symbols

def _safe_import_symbols(self, modName, *symbols, **kwargs):
    try:
        return _original_import_symbols(self, modName, *symbols, **kwargs)
    except _pysnmp_error.MibNotFoundError:
        return ()  # Pas de résolution MIB, OID numériques uniquement

MibBuilder.import_symbols = _safe_import_symbols


async def _generate_it_asset_reference(db: AsyncSession) -> str:
    now = datetime.now(UTC)
    prefix = f"IT-{now.strftime('%Y%m')}-"

    result = await db.execute(
        select(ITAsset.reference)
        .where(ITAsset.reference.like(f"{prefix}%"))
        .order_by(ITAsset.reference.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()

    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    return f"{prefix}{seq:03d}"


def _normalize_mac(mac: Optional[str]) -> Optional[str]:
    if not mac:
        return None
    return mac.replace('-', ':').lower()


def _normalize_ip(ip: Optional[str]) -> Optional[str]:
    return ip


_SNMP_OID_PREFIXES = {
    "sys_descr": "1.3.6.1.2.1.1.1",
    "sys_object_id": "1.3.6.1.2.1.1.2",
    "sys_uptime": "1.3.6.1.2.1.1.3",
    "sys_contact": "1.3.6.1.2.1.1.4",
    "sys_name": "1.3.6.1.2.1.1.5",
    "sys_location": "1.3.6.1.2.1.1.6",
    "ip_media_phys_address": "1.3.6.1.2.1.4.22.1.2",
    "if_phys_address": "1.3.6.1.2.1.2.2.1.6",
}

_SNMP_VENDOR_HINTS = (
    ("cisco", "Cisco"),
    ("hewlett", "Hewlett-Packard"),
    ("hp ", "Hewlett-Packard"),
    ("juniper", "Juniper"),
    ("fortinet", "Fortinet"),
    ("mikrotik", "MikroTik"),
    ("ubiquiti", "Ubiquiti"),
    ("dell", "Dell"),
    ("lexmark", "Lexmark"),
    ("brother", "Brother"),
    ("hikvision", "Hikvision"),
    ("synology", "Synology"),
    ("diskstation", "Synology"),
    ("canon", "Canon"),
    ("ricoh", "Ricoh"),
    ("kyocera", "Kyocera"),
    ("epson", "Epson"),
)


def _parse_snmp_results(results: dict) -> dict:
    """Extraire les valeurs utiles (sysDescr, sysName, ...) d'une réponse SNMP brute."""
    parsed: dict = {}
    for key, value in results.items():
        if not value:
            continue
        for field, prefix in _SNMP_OID_PREFIXES.items():
            if field not in parsed and key.startswith(prefix):
                parsed[field] = value
                break
    descr = (parsed.get("sys_descr") or "").lower()
    contact = (parsed.get("sys_contact") or "").lower()
    for hint, vendor in _SNMP_VENDOR_HINTS:
        if hint in descr or hint in contact:
            parsed["vendor"] = vendor
            break
    return parsed


_SNMP_TYPE_HINTS = (
    ("imprimante", "printer"),
    ("printer", "printer"),
    ("laserjet", "printer"),
    ("inkjet", "printer"),
    ("imageclass", "printer"),
    ("workcentre", "printer"),
    ("magicolor", "printer"),
    ("canon", "printer"),
    ("ricoh", "printer"),
    ("kyocera", "printer"),
    ("lexmark", "printer"),
    ("epson", "printer"),
    ("firewall", "firewall"),
    ("fortigate", "firewall"),
    ("sophos", "firewall"),
    ("paloalto", "firewall"),
    ("access point", "access_point"),
    ("unifi", "access_point"),
    ("unleashed", "access_point"),
    ("switch", "switch"),
    ("catalyst", "switch"),
    ("commutateur", "switch"),
    ("jetstream", "switch"),
    ("ws-c", "switch"),
    ("c2960", "switch"),
    ("c3560", "switch"),
    ("c3850", "switch"),
    ("c9200", "switch"),
    ("c9300", "switch"),
    ("router", "router"),
    ("routeur", "router"),
    ("nas", "server"),
    ("proxmox", "server"),
    ("esxi", "server"),
    ("vmware", "server"),
    ("windows server", "server"),
    ("synology", "server"),
    ("qnap", "server"),
    ("windows 11", "pc_windows"),
    ("windows 10", "pc_windows"),
    ("windows 7", "pc_windows"),
    ("debian", "pc_linux"),
    ("ubuntu", "pc_linux"),
    ("fedora", "pc_linux"),
    ("centos", "pc_linux"),
)


def _infer_asset_type(sys_descr: Optional[str]) -> Optional[str]:
    """Inférer un type d'asset depuis la description système SNMP."""
    if not sys_descr:
        return None
    descr = sys_descr.lower()
    for hint, asset_type in _SNMP_TYPE_HINTS:
        if hint in descr:
            return asset_type
    return None


def _parse_snmp_mac(value: Optional[str]) -> Optional[str]:
    """Convertir une adresse MAC renvoyée par SNMP (OctetString) en format aa:bb:cc:dd:ee:ff."""
    if not value:
        return None
    v = str(value).strip()
    mac = None
    if v.startswith(("0x", "0X")):
        hexpart = v[2:]
        if len(hexpart) == 12 and all(c in "0123456789abcdefABCDEF" for c in hexpart):
            mac = ":".join(hexpart[i:i + 2].lower() for i in range(0, 12, 2))
    else:
        import re
        if re.fullmatch(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', v):
            mac = v.replace("-", ":").lower()
        else:
            parts = re.split(r'[:\-\s\.]', v)
            if len(parts) == 6 and all(0 < len(p) <= 2 and all(c in "0123456789abcdefABCDEF" for c in p) for p in parts):
                mac = ":".join(p.lower().zfill(2) for p in parts)
    if mac == "00:00:00:00:00:00":
        return None
    return mac


# --- Résolution MAC croisée via table ARP SNMP d'un routeur/pare-feu (ex. pfSense) ---

# Colonnes de la table RFC1213 ipNetToMedia (table ARP)
_IPNETTOMEDIA_PHYS = "1.3.6.1.2.1.4.22.1.2"  # ipNetToMediaPhysAddress (MAC, octets binaires)
_IPNETTOMEDIA_ADDR = "1.3.6.1.2.1.4.22.1.3"  # ipNetToMediaAddress (IP, chaîne pointée)


def _parse_mac_octets(raw: Optional[bytes]) -> Optional[str]:
    """Convertir 6 octets SNMP en notation aa:bb:cc:dd:ee:ff.

    Retourne None pour une valeur vide, de taille incorrecte ou nulle
    (00:00:00:00:00:00 = entrée ARP non résolue).
    """
    if not raw or len(raw) != 6:
        return None
    mac = ":".join(f"{b:02x}" for b in raw)
    return None if mac == "00:00:00:00:00:00" else mac


def _arp_columns_to_map(phys_by_index: dict, addr_by_index: dict) -> dict:
    """Relier les colonnes MAC et IP de la table ipNetToMedia par index de ligne.

    Les deux colonnes partagent le même index de ligne SNMP (la valeur de
    l'index diffère selon les agents : IP seule, ou ifIndex + IP). La jointure
    se fait donc sur l'index commun, jamais sur la valeur.

    Retourne {ip: mac}. Les lignes sans contrepartie ou sans MAC valide sont
    ignorées.
    """
    table: dict = {}
    for index, mac in phys_by_index.items():
        ip = addr_by_index.get(index)
        if ip and mac:
            table[ip] = mac
    return table


class ArpTableResolver:
    """Résolution IP -> MAC via la table ARP SNMP d'un routeur (ex. pfSense).

    La table est récupérée en une seule passe puis mise en cache (TTL
    configurable) pour ne pas interroger le routeur à chaque hôte scanné.
    Aucune exception ne sort de ``get_mac`` : routeur indisponible, timeout ou
    entrée absente retournent simplement None.
    """

    # Cache partagé entre scans : {cle: (horodatage, {ip: mac})}
    _cache: dict = {}

    def __init__(
        self,
        host: str,
        community: str,
        *,
        version: str = "2c",
        port: int = 161,
        cache_ttl: int = 300,
        fetch_table=None,
    ):
        self.host = host
        self.community = community
        self.version = version
        self.port = port
        self.cache_ttl = cache_ttl
        # Callable async () -> {ip: mac} ; fourni par le service (walk SNMP).
        self._fetch_table = fetch_table
        # La communauté n'entre pas dans la clé de cache ni dans aucun log.
        self._cache_key = f"{host}:{port}:{version}"

    async def get_mac(self, ip: str) -> Optional[str]:
        """MAC de `ip` via le cache ou une passe ARP, ou None (sans exception)."""
        try:
            table = await self._get_table()
            return table.get(ip)
        except Exception as e:
            print(f"[ARP-RESOLVER] Échec de la table ARP via {self.host}: {e}")
            return None

    async def _get_table(self) -> dict:
        import time as _time
        now = _time.monotonic()
        cached = self._cache.get(self._cache_key)
        if cached and (now - cached[0]) < self.cache_ttl:
            return cached[1]
        table = (await self._fetch_table()) if self._fetch_table else {}
        self._cache[self._cache_key] = (now, table)
        return table

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()


# --- Source B : Résolution des baux DHCP depuis pfSense ---

class DhcpLeaseResolver:
    """Récupération des baux DHCP (IP, MAC, hostname) depuis pfSense.

    Supporte deux modes selon la version pfSense :
    - API REST v2 (/api/v2/status/dhcp/leases) avec clé API
    - Page de statut HTML (fallback) si pas d'API

    La table est récupérée en une seule passe puis mise en cache (TTL configurable).
    """

    _cache: dict = {}

    def __init__(
        self,
        url: str,
        *,
        api_key: str = "",
        user: str = "",
        password: str = "",
        cache_ttl: int = 300,
        fetch_leases=None,
    ):
        self.url = url
        self.api_key = api_key
        self.user = user
        self.password = password
        self.cache_ttl = cache_ttl
        self._fetch_leases = fetch_leases
        self._cache_key = f"dhcp:{url}"

    async def get_lease(self, ip: str) -> Optional[dict]:
        """Retourne {'mac': str, 'hostname': str} ou None."""
        try:
            leases = await self._get_leases()
            return leases.get(ip)
        except Exception as e:
            print(f"[DHCP-RESOLVER] Échec baux DHCP via {self.url}: {e}")
            return None

    async def get_hostname(self, ip: str) -> Optional[str]:
        lease = await self.get_lease(ip)
        return lease.get("hostname") if lease else None

    async def get_mac(self, ip: str) -> Optional[str]:
        lease = await self.get_lease(ip)
        return lease.get("mac") if lease else None

    async def _get_leases(self) -> dict:
        import time as _time
        now = _time.monotonic()
        cached = self._cache.get(self._cache_key)
        if cached and (now - cached[0]) < self.cache_ttl:
            return cached[1]
        leases = (await self._fetch_leases()) if self._fetch_leases else {}
        self._cache[self._cache_key] = (now, leases)
        return leases

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()


# --- Source B bis : Résolution DHCP via fichier local Kea (fallback local) ---

class KeaLeaseFileResolver:
    """Récupération des baux DHCP depuis un fichier local Kea (format CSV).

    Le fichier de baux Kea (`/var/lib/kea/dhcp4.leases` sur pfSense) est copié
    sur le VPS (ex. via SCP cron) et lu localement. Format attendu : CSV Kea
    (format memfile dhcp4.leases).

    Colonnes CSV Kea (format memfile dhcp4.leases) :
      0: address (IP)
      1: hwaddr (MAC)
      2: client-id (DUID)
      3: valid-lifetime
      4: expire (Unix timestamp)
      5: subnet-id
      6: fqdn-fwd
      7: fqdn-rev
      8: hostname
      9+: colonnes additionnelles (ignorées)

    Gère :
    - Parsing robuste CSV (module csv, ignore lignes vides/invalides)
    - Filtrage baux expirés (selon `expire` timestamp Unix)
    - Déduplication : conserve le bail le plus récent par IP (expire max)
    - Normalisation hostname (strip trailing dot, lowercase)
    - Fichier absent/illisible : log + retour table vide sans exception
    """

    _cache: dict = {}

    def __init__(
        self,
        lease_file_path: str,
        *,
        cache_ttl: int = 300,
    ):
        self.lease_file_path = lease_file_path
        self.cache_ttl = cache_ttl
        self._cache_key = f"kea:{lease_file_path}"

    async def get_lease(self, ip: str) -> Optional[dict]:
        """Retourne {'mac': str, 'hostname': str} ou None."""
        try:
            leases = await self._get_leases()
            return leases.get(ip)
        except Exception as e:
            print(f"[KEA-RESOLVER] Échec lecture baux Kea via {self.lease_file_path}: {e}")
            return None

    async def get_hostname(self, ip: str) -> Optional[str]:
        lease = await self.get_lease(ip)
        return lease.get("hostname") if lease else None

    async def get_mac(self, ip: str) -> Optional[str]:
        lease = await self.get_lease(ip)
        return lease.get("mac") if lease else None

    @staticmethod
    def _normalize_hostname(hostname: Optional[str]) -> Optional[str]:
        """Normalise le hostname : strip trailing dot, lowercase, strip whitespace."""
        if not hostname:
            return None
        h = hostname.strip().rstrip(".").lower()
        return h if h else None

    @staticmethod
    def _is_lease_valid(expire: Optional[str], now: float) -> bool:
        """Vérifie si le bail est encore valide (pas expiré)."""
        if expire is None or expire == "":
            return True  # Pas d'expiration = valide
        try:
            return float(expire) > now
        except (ValueError, TypeError):
            return True  # En cas de format invalide, on considère valide

    async def _get_leases(self) -> dict:
        import time as _time
        # Pour la vérification d'expiration, on utilise time.time() (Unix timestamp)
        # car les baux Kea stockent l'expiration en Unix timestamp
        now_unix = _time.time()
        now_mono = _time.monotonic()
        cached = self._cache.get(self._cache_key)
        if cached and (now_mono - cached[0]) < self.cache_ttl:
            return cached[1]

        leases_by_ip: dict = {}
        try:
            # Lecture du fichier CSV (format Kea memfile dhcp4.leases)
            with open(self.lease_file_path, "r", encoding="utf-8") as f:
                import csv
                reader = csv.reader(f)
                for row in reader:
                    # Ignorer lignes vides
                    if not row:
                        continue
                    # Format Kea CSV : address,hwaddr,client-id,valid-lifetime,expire,subnet-id,fqdn-fwd,fqdn-rev,hostname,...
                    if len(row) < 9:
                        continue  # Ligne incomplète
                    ip = row[0].strip()
                    mac = row[1].strip()
                    expire = row[4].strip()
                    hostname = row[8].strip() if len(row) > 8 else ""

                    if not ip or not mac:
                        continue  # Entrée incomplète

                    # Vérifier expiration (comparaison Unix timestamp)
                    if not self._is_lease_valid(expire, now_unix):
                        continue

                    # Normalisation
                    mac_norm = mac.lower().replace("-", ":")
                    host_norm = self._normalize_hostname(hostname)

                    # Déduplication : garde le bail le plus récent (par expire timestamp)
                    existing = leases_by_ip.get(ip)
                    expire_val = 0
                    try:
                        expire_val = int(float(expire)) if expire else 0
                    except (ValueError, TypeError):
                        expire_val = 0
                    if existing is None or expire_val > existing.get("_expire", 0):
                        leases_by_ip[ip] = {
                            "mac": mac_norm,
                            "hostname": host_norm,
                            "_expire": expire_val,  # pour déduplication
                        }

        except FileNotFoundError:
            print(f"[KEA-RESOLVER] Fichier de baux introuvable : {self.lease_file_path}")
        except PermissionError:
            print(f"[KEA-RESOLVER] Permission refusée pour lire : {self.lease_file_path}")
        except Exception as e:
            print(f"[KEA-RESOLVER] Erreur lecture fichier Kea {self.lease_file_path}: {e}")

        # Nettoyer le champ temporaire _expire
        leases_clean = {ip: {"mac": v["mac"], "hostname": v["hostname"]} for ip, v in leases_by_ip.items()}

        self._cache[self._cache_key] = (_time.monotonic(), leases_clean)
        return leases_clean

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()


# --- Source C : Résolution DNS via Active Directory ---

class DnsResolver:
    """Résolution DNS (A / PTR) via un serveur DNS spécifique (ex. AD).

    Utilise `dnspython` pour requêter directement le serveur DNS AD,
    sans dépendre du résolveur système du conteneur.
    """

    _cache: dict = {}

    def __init__(
        self,
        server: str,
        *,
        port: int = 53,
        timeout: float = 2.0,
        cache_ttl: int = 300,
    ):
        self.server = server
        self.port = port
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache_key = f"dns:{server}:{port}"

    async def resolve_a(self, hostname: str) -> Optional[str]:
        """Résolution directe A -> IP."""
        try:
            return await self._resolve(hostname, "A")
        except Exception:
            return None

    async def resolve_ptr(self, ip: str) -> Optional[str]:
        """Résolution inverse PTR -> hostname."""
        try:
            # Construire l'adresse inverse in-addr.arpa
            parts = ip.split(".")
            if len(parts) == 4:
                rev = ".".join(reversed(parts)) + ".in-addr.arpa"
                return await self._resolve(rev, "PTR")
        except Exception:
            pass
        return None

    async def _resolve(self, name: str, rtype: str) -> Optional[str]:
        import dns.asyncresolver
        import dns.exception

        # Clé de cache incluant le type
        cache_key = f"{self._cache_key}:{rtype}:{name}"
        import time as _time
        now = _time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self.cache_ttl:
            return cached[1]

        resolver = dns.asyncresolver.Resolver()
        resolver.nameservers = [self.server]
        resolver.port = self.port
        resolver.timeout = self.timeout
        resolver.lifetime = self.timeout

        try:
            answer = await resolver.resolve(name, rtype)
            result = str(answer[0]).rstrip(".")
            self._cache[cache_key] = (now, result)
            return result
        except (dns.exception.DNSException, Exception):
            return None

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()


class ITAssetService:
    def __init__(
        self,
        db: AsyncSession,
        audit: AuditService = None,
        current_user: User = None,
    ):
        self.db = db
        self.audit = audit
        self.current_user = current_user

    # ============================================================
    # IT ASSETS
    # ============================================================

    async def search_it_assets(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        asset_type: Optional[str] = None,
        status: Optional[str] = None,
        room_id: Optional[int] = None,
        site_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[ITAsset], int]:
        query = select(ITAsset).options(
            selectinload(ITAsset.room).selectinload(Room.building).selectinload(Building.site),
        )
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    ITAsset.reference.ilike(search_term),
                    ITAsset.name.ilike(search_term),
                    ITAsset.manufacturer.ilike(search_term),
                    ITAsset.serial_number.ilike(search_term),
                    ITAsset.ip_address.ilike(search_term),
                    ITAsset.mac_address.ilike(search_term),
                )
            )

        if asset_type is not None:
            conditions.append(ITAsset.asset_type == asset_type)

        if status is not None:
            conditions.append(ITAsset.status == status)

        if room_id is not None:
            conditions.append(ITAsset.room_id == room_id)

        if site_id is not None:
            query = query.join(Room, ITAsset.room_id == Room.id)
            query = query.join(Building, Room.building_id == Building.id)
            conditions.append(Building.site_id == site_id)

        if is_active is not None:
            conditions.append(ITAsset.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "reference": ITAsset.reference,
            "name": ITAsset.name,
            "asset_type": ITAsset.asset_type,
            "status": ITAsset.status,
            "ip_address": ITAsset.ip_address,
            "mac_address": ITAsset.mac_address,
            "serial_number": ITAsset.serial_number,
            "created_at": ITAsset.created_at,
            "updated_at": ITAsset.updated_at,
            "last_seen": ITAsset.last_seen,
        }
        sort_column = allowed_sort_fields.get(sort_by, ITAsset.created_at)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().unique().all())

        return items, total

    async def get_it_asset(self, asset_id: int) -> Optional[ITAsset]:
        result = await self.db.execute(
            select(ITAsset)
            .options(
                selectinload(ITAsset.room).selectinload(Room.building).selectinload(Building.site),
            )
            .where(ITAsset.id == asset_id)
        )
        return result.scalar_one_or_none()

    async def get_it_asset_by_reference(self, reference: str) -> Optional[ITAsset]:
        result = await self.db.execute(
            select(ITAsset).where(ITAsset.reference == reference)
        )
        return result.scalar_one_or_none()

    async def get_it_asset_by_mac(self, mac: str) -> Optional[ITAsset]:
        normalized = _normalize_mac(mac)
        if not normalized:
            return None
        result = await self.db.execute(
            select(ITAsset).where(ITAsset.mac_address == normalized)
        )
        return result.scalar_one_or_none()

    async def get_it_asset_by_ip(self, ip: str) -> Optional[ITAsset]:
        normalized = _normalize_ip(ip)
        if not normalized:
            return None
        result = await self.db.execute(
            select(ITAsset).where(ITAsset.ip_address == normalized)
        )
        return result.scalar_one_or_none()

    async def create_it_asset(self, data: dict) -> Optional[ITAsset]:
        data["reference"] = await _generate_it_asset_reference(self.db)
        if data.get("mac_address"):
            data["mac_address"] = _normalize_mac(data["mac_address"])
        if data.get("ip_address"):
            data["ip_address"] = _normalize_ip(data["ip_address"])

        asset = ITAsset(**data)
        self.db.add(asset)
        try:
            await self.db.commit()
            await self.db.refresh(asset)
        except IntegrityError:
            await self.db.rollback()
            return None

        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="it_asset",
                user=self.current_user,
                object_type="it_asset",
                object_id=asset.id,
                object_repr=f"{asset.reference} - {asset.name}",
                new_values=data,
                status="success",
            )

        return await self.get_it_asset(asset.id)

    async def update_it_asset(self, asset_id: int, data: dict) -> Optional[ITAsset]:
        asset = await self.get_it_asset(asset_id)
        if not asset:
            return None

        data.pop("reference", None)

        if data.get("mac_address"):
            data["mac_address"] = _normalize_mac(data["mac_address"])
        if data.get("ip_address"):
            data["ip_address"] = _normalize_ip(data["ip_address"])

        old_values = {k: getattr(asset, k) for k in data.keys() if hasattr(asset, k)}

        for key, value in data.items():
            if value is not None and hasattr(asset, key):
                setattr(asset, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(asset)
        except IntegrityError:
            await self.db.rollback()
            return None

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="it_asset",
                user=self.current_user,
                object_type="it_asset",
                object_id=asset.id,
                object_repr=f"{asset.reference} - {asset.name}",
                old_values=old_values,
                new_values=data,
                status="success",
            )

            for field_name, new_value in data.items():
                old_value = old_values.get(field_name)
                if old_value != new_value:
                    await self._log_history(asset_id, field_name, str(old_value) if old_value else None, str(new_value) if new_value else None)

        return await self.get_it_asset(asset.id)

    async def _log_history(self, asset_id: int, field_name: str, old_value: Optional[str], new_value: Optional[str]):
        history = ITAssetHistory(
            asset_id=asset_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed_by=self.current_user.id if self.current_user else None,
        )
        self.db.add(history)
        await self.db.flush()

    # ------------------------------------------------------------
    # Interface web d'administration (URL de gestion)
    # ------------------------------------------------------------

    async def set_management_url(self, asset_id: int, url: Optional[str]) -> Optional[ITAsset]:
        """Saisir, modifier ou effacer l'URL de gestion d'un équipement.

        Une URL saisie manuellement est prioritaire : la détection automatique
        ne l'écrasera jamais. L'effacement (champ vide) passe par cette
        méthode dédiée — le verrou « update n'applique jamais None » du
        service générique reste inchangé.
        """
        from app.services.web_detect import validate_management_url

        asset = await self.get_it_asset(asset_id)
        if not asset:
            return None

        normalized = validate_management_url(url)  # lève ValueError si invalide
        old_url = asset.management_url

        if normalized:
            asset.management_url = normalized
            asset.management_url_source = "manual"
            asset.management_url_status = "to_check"
            asset.management_url_detected_at = None
        else:
            asset.management_url = None
            asset.management_url_source = None
            asset.management_url_status = None
            asset.management_url_detected_at = None

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="it_asset",
                user=self.current_user,
                object_type="it_asset",
                object_id=asset.id,
                object_repr=f"{asset.reference} - {asset.name}",
                old_values={"management_url": old_url},
                new_values={"management_url": asset.management_url},
                status="success",
            )

        if old_url != asset.management_url:
            await self._log_history(asset_id, "management_url", old_url, asset.management_url)

        try:
            await self.db.commit()
            await self.db.refresh(asset)
        except IntegrityError:
            await self.db.rollback()
            return None
        return await self.get_it_asset(asset.id)

    async def probe_management_interface(
        self,
        detector,
        ip_address: Optional[str],
        asset_type,
        management_url: Optional[str] = None,
        management_url_source: Optional[str] = None,
    ) -> Tuple[dict, bool]:
        """Choisir la probe adaptée à l'état de l'URL (aucune écriture DB).

        Retourne ``(probe, update_url)`` :
        - URL manuelle → on vérifie SON état (l'URL n'est jamais modifiée) ;
        - sinon → détection sur l'IP de l'équipement (URL auto écrivable).
        """
        from app.services.web_detect import STATUS_TO_CHECK

        if management_url and management_url_source == "manual":
            probe = await detector.probe_url(management_url)
            return probe, False

        if not ip_address:
            return {
                "checked_at": datetime.now(UTC).isoformat(),
                "ip": None,
                "url": None,
                "status": STATUS_TO_CHECK,
                "http_detected": False,
                "error": "aucune adresse IP configurée",
            }, False

        type_value = getattr(asset_type, "value", asset_type)
        probe = await detector.probe_asset(str(ip_address), str(type_value) if type_value else None)
        return probe, True

    async def record_management_probe(
        self,
        asset_id: int,
        probe: dict,
        update_url: bool = True,
    ) -> Optional[ITAsset]:
        """Conserver le résultat d'une probe HTTP(S).

        - met à jour le statut et l'horodatage de dernière vérification ;
        - fusionne les détails dans ``discovery_data["web"]`` (JSON existant,
          aucune colonne supplémentaire) ;
        - n'écrit ``management_url`` (source « auto ») que si ``update_url``
          est autorisé ET que l'URL n'a pas été saisie manuellement ;
        - l'historique n'est alimenté que si la valeur de l'URL change, pour
          ne pas le remplir à chaque re-vérification périodique.
        """
        asset = await self.get_it_asset(asset_id)
        if not asset:
            return None

        probe = dict(probe or {})
        status = probe.get("status")
        old_url = asset.management_url
        is_manual = bool(asset.management_url and asset.management_url_source == "manual")

        # Une URL n'est écrite que si l'interface est réellement confirmée
        # (réponse HTTP ou certificat TLS signalé) : un timeout ou un port
        # fermé ne doit pas laisser passer l'URL simplement tentée.
        from app.services.web_detect import STATUS_TLS_UNTRUSTED

        url_candidate = probe.get("url")
        url_confirmed = bool(probe.get("http_detected")) or status == STATUS_TLS_UNTRUSTED
        if url_candidate and url_confirmed and update_url and not is_manual:
            asset.management_url = url_candidate
            asset.management_url_source = "auto"

        if status:
            asset.management_url_status = status
        asset.management_url_detected_at = datetime.now(UTC)

        discovery_data = dict(asset.discovery_data or {})
        discovery_data["web"] = probe
        asset.discovery_data = discovery_data

        if old_url != asset.management_url:
            await self._log_history(asset_id, "management_url", old_url, asset.management_url)
            if self.audit and self.current_user:
                await self.audit.log(
                    action="update",
                    module="it_asset",
                    user=self.current_user,
                    object_type="it_asset",
                    object_id=asset.id,
                    object_repr=f"{asset.reference} - {asset.name}",
                    old_values={"management_url": old_url},
                    new_values={"management_url": asset.management_url},
                    status="success",
                )

        try:
            await self.db.commit()
            await self.db.refresh(asset)
        except IntegrityError:
            await self.db.rollback()
            return None
        return await self.get_it_asset(asset.id)

    async def detect_management_url(self, asset_id: int, detector=None) -> Optional[ITAsset]:
        """Rechercher / actualiser l'interface web d'un équipement (action manuelle).

        ``detector`` permet d'injecter un ``WebInterfaceDetector`` (tests :
        magasin de confiance TLS personnalisé)."""
        from app.services.web_detect import WebInterfaceDetector

        asset = await self.get_it_asset(asset_id)
        if not asset:
            return None

        if detector is None:
            detector = WebInterfaceDetector(self.db)
        await detector.warmup()
        probe, update_url = await self.probe_management_interface(
            detector,
            asset.ip_address,
            asset.asset_type,
            asset.management_url,
            asset.management_url_source,
        )
        return await self.record_management_probe(asset_id, probe, update_url=update_url)

    async def check_management_url(self, asset_id: int, detector=None) -> Optional[ITAsset]:
        """Tester l'URL de gestion existante sans jamais la modifier.

        ``detector`` permet d'injecter un ``WebInterfaceDetector`` (tests)."""
        from app.services.web_detect import WebInterfaceDetector

        asset = await self.get_it_asset(asset_id)
        if not asset:
            return None
        if not asset.management_url:
            raise ValueError("Aucune URL de gestion à vérifier")

        if detector is None:
            detector = WebInterfaceDetector(self.db)
        await detector.warmup()
        probe = await detector.probe_url(asset.management_url)
        return await self.record_management_probe(asset_id, probe, update_url=False)

    async def refresh_due_management_urls(self) -> dict:
        """Re-vérifier périodiquement les URL déjà détectées (peu fréquent).

        Ne concerne QUE les équipements ayant déjà une URL, et seulement ceux
        dont la dernière vérification dépasse IT_WEB_DETECT_REFRESH_HOURS :
        aucun test HTTP en masse à chaque cycle de supervision de 5 minutes.
        """
        settings = get_settings()
        if not settings.IT_WEB_DETECT_ENABLED:
            return {"due": 0, "checked": 0, "failed": 0, "disabled": True}

        from app.db.session import AsyncSessionLocal

        cutoff = datetime.now(UTC) - timedelta(hours=settings.IT_WEB_DETECT_REFRESH_HOURS)
        result = await self.db.execute(
            select(ITAsset.id)
            .where(ITAsset.is_active == True)  # noqa: E712
            .where(ITAsset.management_url.isnot(None))
            .where(or_(
                ITAsset.management_url_detected_at.is_(None),
                ITAsset.management_url_detected_at <= cutoff,
            ))
            .order_by(ITAsset.management_url_detected_at.asc())
            .limit(settings.IT_WEB_DETECT_REFRESH_BATCH)
        )
        asset_ids = [row[0] for row in result.all()]
        if not asset_ids:
            return {"due": 0, "checked": 0, "failed": 0}

        async def _check_one(aid: int) -> Optional[ITAsset]:
            # Session dédiée par vérification (même pattern que check_all_assets)
            async with AsyncSessionLocal() as db:
                try:
                    return await ITAssetService(db).check_management_url(aid)
                except Exception as exc:
                    print(f"[WEB-DETECT] Erreur refresh asset {aid}: {exc}")
                    return None
                finally:
                    await db.close()

        results = await asyncio.gather(*[_check_one(aid) for aid in asset_ids])
        checked = sum(1 for item in results if item is not None)
        return {
            "due": len(asset_ids),
            "checked": checked,
            "failed": len(asset_ids) - checked,
        }

    async def delete_it_asset(self, asset_id: int) -> bool:
        asset = await self.get_it_asset(asset_id)
        if not asset:
            return False

        try:
            await self.db.delete(asset)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return False

        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="it_asset",
                user=self.current_user,
                object_type="it_asset",
                object_id=asset_id,
                object_repr=f"{asset.reference} - {asset.name}",
                status="success",
            )

        return True

    async def import_it_assets(
        self,
        items: List[dict],
        skip_duplicates: bool = True,
        update_existing: bool = False,
    ) -> dict:
        created = 0
        updated = 0
        skipped = 0
        errors = []

        for item in items:
            try:
                room_id = item.pop("room_id", None)
                if room_id is None:
                    room_ref = item.pop("room_reference", None)
                    room_name = item.pop("room_name", None)
                    building_ref = item.pop("building_reference", None)
                    building_name = item.pop("building_name", None)
                    site_ref = item.pop("site_reference", None)
                    site_name = item.pop("site_name", None)

                    if room_ref or room_name:
                        query = select(Room).join(Building).join(Site)
                        if site_ref:
                            query = query.where(Site.reference == site_ref)
                        elif site_name:
                            query = query.where(Site.name == site_name)
                        if building_ref:
                            query = query.where(Building.reference == building_ref)
                        elif building_name:
                            query = query.where(Building.name == building_name)
                        if room_ref:
                            query = query.where(Room.reference == room_ref)
                        elif room_name:
                            query = query.where(Room.name == room_name)

                        result = await self.db.execute(query)
                        room = result.scalar_one_or_none()
                        if room:
                            room_id = room.id

                if room_id is None:
                    errors.append(f"Pièce introuvable pour l'élément: {item.get('name')}")
                    skipped += 1
                    continue

                item["room_id"] = room_id

                existing = None
                if item.get("mac_address"):
                    existing = await self.get_it_asset_by_mac(item["mac_address"])
                if not existing and item.get("ip_address"):
                    existing = await self.get_it_asset_by_ip(item["ip_address"])
                if not existing and item.get("serial_number"):
                    result = await self.db.execute(
                        select(ITAsset).where(ITAsset.serial_number == item["serial_number"])
                    )
                    existing = result.scalar_one_or_none()

                if existing:
                    if update_existing:
                        await self.update_it_asset(existing.id, item)
                        updated += 1
                    elif skip_duplicates:
                        skipped += 1
                    else:
                        errors.append(f"Doublon détecté (MAC/IP/Serial): {item.get('name')}")
                        skipped += 1
                else:
                    await self.create_it_asset(item)
                    created += 1

            except Exception as e:
                errors.append(f"Erreur import {item.get('name', 'inconnu')}: {str(e)}")
                skipped += 1

        return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}

    # ============================================================
    # NETWORK RANGES
    # ============================================================

    async def search_network_ranges(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[NetworkRange], int]:
        query = select(NetworkRange).options(
            selectinload(NetworkRange.site),
            selectinload(NetworkRange.room),
        )
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    NetworkRange.name.ilike(search_term),
                    NetworkRange.cidr.ilike(search_term),
                    NetworkRange.description.ilike(search_term),
                )
            )

        if is_active is not None:
            conditions.append(NetworkRange.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "name": NetworkRange.name,
            "cidr": NetworkRange.cidr,
            "created_at": NetworkRange.created_at,
        }
        sort_column = allowed_sort_fields.get(sort_by, NetworkRange.created_at)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().unique().all())

        return items, total

    async def get_network_range(self, range_id: int) -> Optional[NetworkRange]:
        result = await self.db.execute(
            select(NetworkRange)
            .options(
                selectinload(NetworkRange.site),
                selectinload(NetworkRange.room),
            )
            .where(NetworkRange.id == range_id)
        )
        return result.scalar_one_or_none()

    async def create_network_range(self, data: dict) -> Optional[NetworkRange]:
        if data.get("cidr"):
            try:
                if ':' in data["cidr"]:
                    IPv6Network(data["cidr"], strict=False)
                else:
                    IPv4Network(data["cidr"], strict=False)
            except ValueError:
                return None

        network_range = NetworkRange(**data)
        self.db.add(network_range)
        try:
            await self.db.commit()
            await self.db.refresh(network_range)
        except IntegrityError:
            await self.db.rollback()
            return None

        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="it_asset",
                user=self.current_user,
                object_type="network_range",
                object_id=network_range.id,
                object_repr=network_range.name,
                new_values=data,
                status="success",
            )

        return await self.get_network_range(network_range.id)

    async def update_network_range(self, range_id: int, data: dict) -> Optional[NetworkRange]:
        network_range = await self.get_network_range(range_id)
        if not network_range:
            return None

        if data.get("cidr"):
            try:
                if ':' in data["cidr"]:
                    IPv6Network(data["cidr"], strict=False)
                else:
                    IPv4Network(data["cidr"], strict=False)
            except ValueError:
                return None

        old_values = {k: getattr(network_range, k) for k in data.keys() if hasattr(network_range, k)}

        for key, value in data.items():
            if hasattr(network_range, key):
                setattr(network_range, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(network_range)
        except IntegrityError:
            await self.db.rollback()
            return None

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="it_asset",
                user=self.current_user,
                object_type="network_range",
                object_id=network_range.id,
                object_repr=network_range.name,
                old_values=old_values,
                new_values=data,
                status="success",
            )

        return await self.get_network_range(network_range.id)

    async def delete_network_range(self, range_id: int) -> bool:
        network_range = await self.get_network_range(range_id)
        if not network_range:
            return False

        try:
            await self.db.delete(network_range)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return False

        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="it_asset",
                user=self.current_user,
                object_type="network_range",
                object_id=range_id,
                object_repr=network_range.name,
                status="success",
            )

        return True

    # ============================================================
    # DISCOVERY LOGS
    # ============================================================

    async def create_discovery_log(self, network_range_id: int) -> DiscoveryLog:
        log = DiscoveryLog(
            network_range_id=network_range_id,
            status="running",
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def update_discovery_log_progress(
        self,
        log_id: int,
        hosts_scanned: int = 0,
        hosts_found: int = 0,
        assets_created: int = 0,
        assets_updated: int = 0,
    ) -> None:
        """Mettre à jour les compteurs d'un scan en cours (suivi en direct)."""
        log = await self.db.get(DiscoveryLog, log_id)
        if not log:
            return
        log.hosts_scanned = hosts_scanned
        log.hosts_found = hosts_found
        log.assets_created = assets_created
        log.assets_updated = assets_updated
        await self.db.commit()

    async def complete_discovery_log(
        self,
        log_id: int,
        status: str,
        hosts_scanned: int = 0,
        hosts_found: int = 0,
        assets_created: int = 0,
        assets_updated: int = 0,
        errors: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> Optional[DiscoveryLog]:
        log = await self.db.get(DiscoveryLog, log_id)
        if not log:
            return None

        log.status = status
        log.completed_at = datetime.now(UTC)
        log.hosts_scanned = hosts_scanned
        log.hosts_found = hosts_found
        log.assets_created = assets_created
        log.assets_updated = assets_updated
        log.errors = errors
        if details is not None:
            log.details = details

        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def get_discovery_logs(
        self,
        network_range_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[DiscoveryLog]:
        query = select(DiscoveryLog).order_by(DiscoveryLog.started_at.desc())
        if network_range_id:
            query = query.where(DiscoveryLog.network_range_id == network_range_id)
        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ============================================================
    # OBSERVATIONS
    # ============================================================

    async def create_observation(
        self,
        asset_id: int,
        status: str,
        response_time_ms: Optional[int] = None,
        check_method: str = "ping",
        details: Optional[dict] = None,
    ) -> AssetObservation:
        observation = AssetObservation(
            asset_id=asset_id,
            status=status,
            response_time_ms=response_time_ms,
            check_method=check_method,
            details=details,
        )
        self.db.add(observation)
        await self.db.commit()
        await self.db.refresh(observation)
        return observation

    async def get_asset_observations(
        self,
        asset_id: int,
        limit: int = 100,
    ) -> List[AssetObservation]:
        result = await self.db.execute(
            select(AssetObservation)
            .where(AssetObservation.asset_id == asset_id)
            .order_by(AssetObservation.checked_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ============================================================
    # ALERTS
    # ============================================================

    async def create_alert(
        self,
        asset_id: int,
        alert_type: str,
        severity: str,
        message: str,
        details: Optional[dict] = None,
    ) -> ITAlert:
        # Une supervision peut être déclenchée simultanément par le contrôle
        # manuel et la boucle automatique. Une seule alerte ouverte doit
        # exister pour un équipement et un type donné.
        existing_result = await self.db.execute(
            select(ITAlert)
            .where(
                ITAlert.asset_id == asset_id,
                ITAlert.alert_type == alert_type,
                ITAlert.resolved.is_(False),
            )
            .order_by(ITAlert.created_at.desc())
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            existing.severity = severity
            existing.message = message
            existing.details = details
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        alert = ITAlert(
            asset_id=asset_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            details=details,
        )
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def get_asset_alerts(
        self,
        asset_id: int,
        resolved: Optional[bool] = None,
    ) -> List[ITAlert]:
        query = select(ITAlert).where(ITAlert.asset_id == asset_id)
        if resolved is not None:
            query = query.where(ITAlert.resolved == resolved)
        query = query.order_by(ITAlert.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def acknowledge_alert(
        self,
        alert_id: int,
        user: User,
    ) -> Optional[ITAlert]:
        alert = await self.db.get(ITAlert, alert_id)
        if not alert:
            return None

        alert.acknowledged = True
        alert.acknowledged_by = user.id
        alert.acknowledged_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def resolve_alert(self, alert_id: int) -> Optional[ITAlert]:
        alert = await self.db.get(ITAlert, alert_id)
        if not alert:
            return None

        alert.resolved = True
        alert.resolved_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def resolve_active_unreachable_alerts(self, asset_id: int) -> int:
        """Résout automatiquement les alertes de non-disponibilité ouvertes pour cet équipement."""
        unreachable_types = [ITAlertType.UNREACHABLE, ITAlertType.STATUS_CHANGE]
        result = await self.db.execute(
            select(ITAlert)
            .where(
                ITAlert.asset_id == asset_id,
                ITAlert.resolved.is_(False),
                ITAlert.alert_type.in_(unreachable_types),
            )
        )
        alerts = list(result.scalars().all())
        now = datetime.now(UTC)
        for alert in alerts:
            alert.resolved = True
            alert.resolved_at = now
            details = dict(alert.details or {})
            details["auto_resolved"] = True
            details["recovered_at"] = now.isoformat()
            alert.details = details

        if alerts:
            await self.db.commit()
            for alert in alerts:
                await self.db.refresh(alert)
        return len(alerts)

    async def search_alerts(
        self,
        page: int = 1,
        page_size: int = 20,
        resolved: Optional[bool] = None,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        asset_id: Optional[int] = None,
        room_id: Optional[int] = None,
        site_id: Optional[int] = None,
        sort_order: str = "desc",
    ) -> Tuple[List[ITAlert], int]:
        """Recherche globale et filtrage des alertes de supervision du parc."""
        query = select(ITAlert)
        conditions = []

        if resolved is not None:
            conditions.append(ITAlert.resolved == resolved)

        if severity is not None:
            conditions.append(ITAlert.severity == severity)

        if alert_type is not None:
            conditions.append(ITAlert.alert_type == alert_type)

        if asset_id is not None:
            conditions.append(ITAlert.asset_id == asset_id)

        need_asset_join = room_id is not None or site_id is not None
        if need_asset_join:
            query = query.join(ITAsset, ITAlert.asset_id == ITAsset.id)
            if room_id is not None:
                conditions.append(ITAsset.room_id == room_id)
            if site_id is not None:
                query = query.join(Room, ITAsset.room_id == Room.id).join(Building, Room.building_id == Building.id)
                conditions.append(Building.site_id == site_id)

        if conditions:
            query = query.where(and_(*conditions))

        if sort_order == "desc":
            query = query.order_by(ITAlert.created_at.desc())
        else:
            query = query.order_by(ITAlert.created_at.asc())

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    # ============================================================
    # HISTORY
    # ============================================================

    async def get_asset_history(
        self,
        asset_id: int,
        limit: int = 100,
    ) -> List[ITAssetHistory]:
        result = await self.db.execute(
            select(ITAssetHistory)
            .where(ITAssetHistory.asset_id == asset_id)
            .order_by(ITAssetHistory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


settings = get_settings()


class NetworkDiscoveryService:
    def __init__(
        self,
        db: AsyncSession,
        audit: AuditService = None,
        current_user: User = None,
    ):
        self.db = db
        self.audit = audit
        self.current_user = current_user
        self.asset_service = ITAssetService(db, audit, current_user)
        self._semaphore = asyncio.Semaphore(20)
        # Verrou DB : les écritures concurrentes (gather) partagent la même
        # session, un commit simultané ferait échouer le scan
        self._db_lock = asyncio.Lock()

    async def _ping_host(self, ip: str, timeout: float = 2.0) -> Tuple[bool, Optional[float]]:
        system = platform.system().lower()
        if system == "windows":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]

        try:
            start = datetime.now(UTC)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=timeout + 1)
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            return proc.returncode == 0, elapsed if proc.returncode == 0 else None
        except asyncio.TimeoutError:
            return False, None
        except Exception:
            return False, None

    async def _get_mac_from_arp(self, ip: str) -> Optional[str]:
        try:
            system = platform.system().lower()
            if system == "windows":
                cmd = ["arp", "-a", ip]
            else:
                cmd = ["arp", "-n", ip]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            import re
            mac_pattern = r'([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})'
            match = re.search(mac_pattern, output)
            if match:
                return match.group(0).replace('-', ':').lower()
        except Exception:
            pass
        return None

    async def _get_snmp_info(
        self,
        ip: str,
        community: str,
        version: str = "2c",
        timeout: float = 2.0,
        retries: int = 1,
        port: int = 161,
        max_total_timeout: float = 4.0,
    ) -> Optional[dict]:
        """Collecter des informations SNMP depuis un équipement avec gestion stricte des timeouts."""
        from pysnmp.hlapi.asyncio import (
            SnmpEngine,
            CommunityData,
            UdpTransportTarget,
            ContextData,
            ObjectType,
            ObjectIdentity,
            get_cmd,
            next_cmd,
        )

        async def _do_collect():
            snmp_engine = SnmpEngine()
            try:
                mp_model = 0 if str(version).strip().lower().lstrip("v").startswith("1") else 1
                auth_data = CommunityData(community, mpModel=mp_model)
                transport = await UdpTransportTarget.create(
                    (ip, port),
                    timeout=timeout,
                    retries=retries,
                )
                context = ContextData()

                oids = [
                    "1.3.6.1.2.1.1.1.0",  # sysDescr
                    "1.3.6.1.2.1.1.2.0",  # sysObjectID
                    "1.3.6.1.2.1.1.3.0",  # sysUpTime
                    "1.3.6.1.2.1.1.4.0",  # sysContact
                    "1.3.6.1.2.1.1.5.0",  # sysName
                    "1.3.6.1.2.1.1.6.0",  # sysLocation
                    "1.3.6.1.2.1.1.8.0",  # ifNumber
                ]
                if ":" not in ip:
                    oids.append(f"1.3.6.1.2.1.4.22.1.2.{'.'.join(ip.split('.'))}")

                def _snmp_value_to_str(oid: str, val) -> str:
                    try:
                        if '.4.22.1.2.' in oid or '.2.2.1.6.' in oid or oid.endswith('.2.2.1.6'):
                            raw = val.asOctets()
                            if len(raw) == 6:
                                return ':'.join(f'{b:02x}' for b in raw)
                    except Exception:
                        pass
                    return str(val)

                results = {}
                error_indication, error_status, error_index, var_binds = await get_cmd(
                    snmp_engine,
                    auth_data,
                    transport,
                    context,
                    *[ObjectType(ObjectIdentity(o)) for o in oids],
                )

                # Si erreur de transport/timeout, abandonner immédiatement (pas de cascade d'OIDs unitaires)
                if error_indication:
                    return None

                if not error_status and var_binds:
                    for name, val in var_binds:
                        s = _snmp_value_to_str(str(name), val)
                        if s:
                            results[str(name)] = s

                if results:
                    err_ind, err_stat, _, binds = await next_cmd(
                        snmp_engine,
                        auth_data,
                        transport,
                        context,
                        ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.6')),
                    )
                    if not err_ind and not err_stat and binds:
                        for name, val in binds:
                            s = _snmp_value_to_str(str(name), val)
                            if s and s != '00:00:00:00:00:00':
                                results[str(name)] = s
                                break

                return results if results else None
            finally:
                if hasattr(snmp_engine, "close_dispatcher"):
                    snmp_engine.close_dispatcher()
                elif hasattr(snmp_engine, "closeDispatcher"):
                    snmp_engine.closeDispatcher()

        try:
            return await asyncio.wait_for(_do_collect(), timeout=max_total_timeout)
        except (asyncio.TimeoutError, Exception):
            return None

    async def _snmp_walk_column(
        self,
        ip: str,
        column_oid: str,
        community: str,
        version: str = "2c",
        timeout: float = 2.0,
        retries: int = 1,
        port: int = 161,
    ) -> dict:
        """Walk d'une colonne SNMP (ex. table ARP) -> {index de ligne: valeur}.

        Les adresses physiques (ipNetToMediaPhysAddress) sont converties en
        notation aa:bb:cc:dd:ee:ff. Timeout et erreurs SNMP retournent une
        table partielle ou vide : jamais d'exception vers l'appelant.
        """
        from pysnmp.hlapi.asyncio import (
            SnmpEngine,
            CommunityData,
            UdpTransportTarget,
            ContextData,
            ObjectType,
            ObjectIdentity,
            next_cmd,
        )

        is_phys_column = column_oid == _IPNETTOMEDIA_PHYS
        mp_model = 0 if str(version).strip().lower().lstrip("v").startswith("1") else 1
        # Nombre de sub-identifiants du préfixe de colonne (ex. 10 pour
        # 1.3.6.1.2.1.4.22.1.2) : l'index de la ligne suit dans l'OID.
        col_tuple = tuple(int(x) for x in column_oid.split("."))
        prefix_len = len(col_tuple)

        values: dict = {}
        snmp_engine = SnmpEngine()
        try:
            transport = await UdpTransportTarget.create(
                (ip, port), timeout=timeout, retries=retries,
            )
            # Marche SNMP : next_cmd (pysnmp 7) avance d'une seule OI par appel,
            # on boucle jusqu'à sortir de la table ou manquer de réponses.
            current_oid = column_oid
            while current_oid:
                error_indication, error_status, _error_index, var_binds = await next_cmd(
                    snmp_engine,
                    CommunityData(community, mpModel=mp_model),
                    transport,
                    ContextData(),
                    ObjectType(ObjectIdentity(current_oid)),
                )
                if error_indication or error_status:
                    break
                if not var_binds:
                    break
                next_oid = None
                for name, val in var_binds:
                    name_tuple = tuple(name)
                    if len(name_tuple) <= prefix_len or name_tuple[:prefix_len] != col_tuple:
                        break  # sortie de la table
                    # On repasse par une string OID 100 % numérique (les
                    # sub-identifiants binaires de l'index IMPLIED ne doivent
                    # jamais être repris via str() : chars illisibles).
                    next_oid = ".".join(str(s) for s in name_tuple)
                    # L'index de ligne peut être binaire (index IMPLIED des
                    # agents BSD/pfSense : 4 octets d'IP encodés en sub-IDs) :
                    # on le stabilise via le tuple numérique, jamais via str().
                    index = ".".join(str(s) for s in name_tuple[prefix_len:])
                    if is_phys_column:
                        try:
                            mac = _parse_mac_octets(val.asOctets())
                        except Exception:
                            mac = _parse_snmp_mac(str(val))
                        if mac:
                            values[index] = mac
                    else:
                        # ipNetToMediaAddress est une IpAddress (4 octets bruts)
                        try:
                            raw = val.asOctets()
                            s = ".".join(str(b) for b in raw) if len(raw) == 4 else str(val)
                        except Exception:
                            s = str(val)
                        s = s.strip()
                        if s:
                            values[index] = s
                current_oid = next_oid
        except Exception as e:
            print(f"[SNMP-ARP] Erreur collecte colonne {column_oid} via {ip}: {e}")
        finally:
            if hasattr(snmp_engine, "close_dispatcher"):
                snmp_engine.close_dispatcher()
            elif hasattr(snmp_engine, "closeDispatcher"):
                snmp_engine.closeDispatcher()

        return values

    def _build_arp_resolver(self, community: str) -> Optional[ArpTableResolver]:
        """Construire le résolveur ARP (routeur) si configuré, sinon None.

        Activé uniquement via IT_ARP_RESOLVER_ENABLED + IT_ARP_RESOLVER_HOST
        (désactivé par défaut : aucun environnement n'est impacté sans
        configuration explicite). La communauté du routeur est celle des
        paramètres, à défaut celle de la plage scannée — jamais codée en dur.
        """
        settings = get_settings()
        if not settings.IT_ARP_RESOLVER_ENABLED or not settings.IT_ARP_RESOLVER_HOST:
            return None

        host = settings.IT_ARP_RESOLVER_HOST
        version = settings.IT_ARP_RESOLVER_VERSION
        port = settings.IT_ARP_RESOLVER_PORT

        async def _fetch_table() -> dict:
            # La table ARP est récupérée en une seule passe (puis mise en cache) :
            # pfSense hors-ligne ou timeout ne font que produire une table vide,
            # sans jamais faire échouer le scan (get_mac isole les exceptions).
            phys = await self._snmp_walk_column(
                host, _IPNETTOMEDIA_PHYS, community, version=version, port=port,
            )
            addrs = await self._snmp_walk_column(
                host, _IPNETTOMEDIA_ADDR, community, version=version, port=port,
            )
            return _arp_columns_to_map(phys, addrs)

        return ArpTableResolver(
            host,
            community,
            version=version,
            port=port,
            cache_ttl=settings.IT_ARP_RESOLVER_CACHE_TTL,
            fetch_table=_fetch_table,
        )

    async def _build_dhcp_resolver(self) -> Optional[DhcpLeaseResolver]:
        """Construire le résolveur DHCP.

        Priorité :
        1. Fichier local Kea (IT_DHCP_KEA_LEASE_FILE) si configuré et lisible
        2. API HTTP pfSense (IT_DHCP_RESOLVER_URL) si configurée
        3. None sinon

        Retourne un objet compatible avec l'interface get_lease/get_hostname/get_mac.
        """
        settings = get_settings()

        # 1. Fichier local Kea (priorité haute : fichier copié via SCP cron)
        kea_file = settings.IT_DHCP_KEA_LEASE_FILE
        if kea_file:
            try:
                # Vérifier que le fichier existe et est lisible
                import os
                if os.path.isfile(kea_file) and os.access(kea_file, os.R_OK):
                    return KeaLeaseFileResolver(
                        kea_file,
                        cache_ttl=settings.IT_DHCP_KEA_CACHE_TTL,
                    )
                else:
                    print(f"[DHCP] Fichier Kea configuré mais introuvable ou illisible : {kea_file}")
            except Exception as e:
                print(f"[DHCP] Erreur initialisation résolveur Kea local : {e}")

        # 2. Fallback : API HTTP pfSense (existant)
        if not settings.IT_DHCP_RESOLVER_ENABLED or not settings.IT_DHCP_RESOLVER_URL:
            return None

        async def _fetch_leases() -> dict:
            """Récupérer les baux DHCP depuis pfSense."""
            import aiohttp
            import ssl

            url = settings.IT_DHCP_RESOLVER_URL
            headers = {}
            auth = None

            if settings.IT_DHCP_RESOLVER_API_KEY:
                headers["Authorization"] = f"Bearer {settings.IT_DHCP_RESOLVER_API_KEY}"
            elif settings.IT_DHCP_RESOLVER_USER and settings.IT_DHCP_RESOLVER_PASSWORD:
                auth = aiohttp.BasicAuth(
                    settings.IT_DHCP_RESOLVER_USER,
                    settings.IT_DHCP_RESOLVER_PASSWORD,
                )

            # Désactiver la vérification SSL si auto-signé (commun sur pfSense local)
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            leases: dict = {}
            try:
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=ssl_ctx),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as session:
                    async with session.get(url, headers=headers, auth=auth) as resp:
                        if resp.status != 200:
                            print(f"[DHCP] Erreur HTTP {resp.status} depuis {url}")
                            return leases

                        content_type = resp.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            data = await resp.json()
                            # Format attendu: liste d'objets {ip, mac, hostname, ...}
                            for entry in data if isinstance(data, list) else []:
                                ip = entry.get("ip") or entry.get("IP")
                                mac = entry.get("mac") or entry.get("MAC") or entry.get("hardware_address")
                                hostname = entry.get("hostname") or entry.get("host_name") or entry.get("name")
                                if ip and mac:
                                    leases[ip] = {"mac": mac.lower().replace("-", ":"), "hostname": hostname}
                        else:
                            # Fallback HTML parsing basique (page status_dhcp_leases.php)
                            text = await resp.text()
                            import re
                            # Pattern: <tr>...<td>IP</td><td>MAC</td><td>hostname</td>...
                            rows = re.findall(
                                r"<tr[^>]*>.*?<td[^>]*>([0-9.]+)</td>.*?<td[^>]*>([0-9a-fA-F:]{17})</td>.*?<td[^>]*>([^<]*)</td>",
                                text,
                                re.DOTALL | re.IGNORECASE,
                            )
                            for ip, mac, hostname in rows:
                                leases[ip.strip()] = {
                                    "mac": mac.strip().lower(),
                                    "hostname": hostname.strip() if hostname else None,
                                }
            except Exception as e:
                print(f"[DHCP] Erreur collecte baux depuis {url}: {e}")

            return leases

        return DhcpLeaseResolver(
            settings.IT_DHCP_RESOLVER_URL,
            api_key=settings.IT_DHCP_RESOLVER_API_KEY,
            user=settings.IT_DHCP_RESOLVER_USER,
            password=settings.IT_DHCP_RESOLVER_PASSWORD,
            cache_ttl=settings.IT_DHCP_RESOLVER_CACHE_TTL,
            fetch_leases=_fetch_leases,
        )

    async def _build_dns_resolver(self) -> Optional[DnsResolver]:
        """Construire le résolveur DNS (AD) si configuré, sinon None."""
        settings = get_settings()
        if not settings.IT_DNS_RESOLVER_ENABLED or not settings.IT_DNS_RESOLVER_SERVER:
            return None

        return DnsResolver(
            settings.IT_DNS_RESOLVER_SERVER,
            port=settings.IT_DNS_RESOLVER_PORT,
            timeout=settings.IT_DNS_RESOLVER_TIMEOUT,
            cache_ttl=settings.IT_DNS_RESOLVER_CACHE_TTL,
        )

    async def scan_network_range(self, network_range_id: int, log: Optional[DiscoveryLog] = None) -> dict:
        network_range = await self.asset_service.get_network_range(network_range_id)
        if not network_range:
            return {"error": "Plage réseau non trouvée"}

        if log is None:
            log = await self.asset_service.create_discovery_log(network_range_id)

        # Snapshot des scalaires ORM : après commit, les objets expirent et un
        # accès concurrent depuis gather déclencherait des lazy-load en conflit
        log_id = log.id
        cidr = network_range.cidr
        network_range_room_id = network_range.room_id
        snmp_enabled = network_range.snmp_enabled
        snmp_community = network_range.snmp_community
        snmp_version = network_range.snmp_version
        snmp_port = network_range.snmp_port

        # Résolution MAC croisée via routeur (ex. pfSense) : configurée par
        # settings, désactivée par défaut. Construite une fois pour tout le scan.
        arp_resolver = self._build_arp_resolver(snmp_community or "public")

        # Résolution DHCP (baux pfSense) : hostname + MAC fallback
        dhcp_resolver = await self._build_dhcp_resolver()

        # Résolution DNS (AD) : hostname via PTR
        dns_resolver = await self._build_dns_resolver()

        # Détection de l'interface web d'administration : construite et
        # « réchauffée » (autorise-liste inventaire + plages) UNE fois avant les
        # tâches parallèles, pour ne jamais requêter la session en concurrence.
        # Lecture tolérante : un stub de settings partiel (tests) désactive la
        # détection plutôt que de faire échouer le scan.
        web_detector = None
        if getattr(get_settings(), "IT_WEB_DETECT_ENABLED", False):
            from app.services.web_detect import WebInterfaceDetector
            try:
                web_detector = WebInterfaceDetector(self.db)
                await web_detector.warmup()
            except Exception:
                # La détection web ne doit jamais faire échouer un scan.
                web_detector = None

        try:
            network = IPv4Network(cidr, strict=False) if ':' not in cidr else IPv6Network(cidr, strict=False)
            hosts = [str(ip) for ip in network.hosts()]
            total_hosts = len(hosts)

            hosts_scanned = 0
            hosts_found = 0
            assets_created = 0
            assets_updated = 0
            scan_errors: List[str] = []

            async def scan_host(ip: str):
                nonlocal hosts_scanned, hosts_found, assets_created, assets_updated
                async with self._semaphore:
                    reachable, response_time = await self._ping_host(ip)
                    hosts_scanned += 1

                    if reachable:
                        hosts_found += 1
                        mac = await self._get_mac_from_arp(ip)
                        existing = None

                        discovery_data = {"response_time_ms": response_time}
                        snmp_fields = {}
                        snmp_mac = None
                        inferred_type = None

                        if snmp_enabled:
                            snmp_raw = await self._get_snmp_info(
                                ip,
                                snmp_community or "public",
                                snmp_version or "2c",
                                retries=1,
                                port=snmp_port or 161,
                            )
                            if snmp_raw:
                                parsed = _parse_snmp_results(snmp_raw)
                                discovery_data["snmp"] = {**parsed, "raw": snmp_raw}
                                snmp_mac = _parse_snmp_mac(parsed.get("ip_media_phys_address")) or \
                                    _parse_snmp_mac(parsed.get("if_phys_address"))
                                inferred_type = _infer_asset_type(parsed.get("sys_descr"))

                                def _snmp_set(field: str, value):
                                    if value:
                                        snmp_fields[field] = value

                                _snmp_set("snmp_manufacturer", parsed.get("vendor"))
                                _snmp_set("snmp_contact", parsed.get("sys_contact"))
                                _snmp_set("snmp_location", parsed.get("sys_location"))

                        # ARP ne fonctionne qu'en L2 : repli sur la MAC SNMP (ifPhysAddress/ipNetToMedia)
                        if not mac and snmp_mac:
                            mac = snmp_mac

                        # Dernier repli : table ARP du routeur (ex. pfSense) —
                        # uniquement si la MAC reste inconnue, jamais par-dessus
                        # une MAC déjà découverte. Timeout/routeur indisponible
                        # : get_mac retourne None sans faire échouer le scan.
                        if not mac and arp_resolver is not None:
                            resolved = await arp_resolver.get_mac(ip)
                            if resolved:
                                mac = resolved

                        # Repli additionnel : baux DHCP pfSense — MAC si toujours absente
                        if not mac and dhcp_resolver is not None:
                            dhcp_mac = await dhcp_resolver.get_mac(ip)
                            if dhcp_mac:
                                mac = dhcp_mac

                        # Toutes les écritures DB sont sérialisées (verrou) car les
                        # tâches concurrentes partagent la même session SQLAlchemy
                        web_target = None
                        async with self._db_lock:
                            if mac:
                                existing = await self.asset_service.get_it_asset_by_mac(mac)
                            if not existing:
                                existing = await self.asset_service.get_it_asset_by_ip(ip)

                            # Priorité Manuel > SNMP : ne jamais écraser une valeur déjà saisie
                            if existing:
                                for f in list(snmp_fields):
                                    if getattr(existing, f, None) is not None:
                                        del snmp_fields[f]

                            asset_data = {
                                "ip_address": ip,
                                "status": "online",
                                "discovery_source": "network_scan",
                                "discovery_data": discovery_data,
                                "last_seen": datetime.now(UTC),
                                "last_check": datetime.now(UTC),
                                **snmp_fields,
                            }

                            # Détermination du nom : priorité SNMP sys_name > DHCP hostname > DNS PTR > IP
                            snmp_name = (discovery_data.get("snmp") or {}).get("sys_name")
                            dhcp_hostname = None
                            if dhcp_resolver is not None:
                                dhcp_hostname = await dhcp_resolver.get_hostname(ip)
                            dns_ptr_name = None
                            if not dhcp_hostname and dns_resolver is not None:
                                dns_ptr_name = await dns_resolver.resolve_ptr(ip)

                            chosen_name = snmp_name or dhcp_hostname or dns_ptr_name or f"Host {ip}"

                            if existing:
                                # Priorité Manuel > scan : préserver un nom/type saisi manuellement
                                if existing.name.startswith("Host ") or not existing.name:
                                    asset_data["name"] = chosen_name
                                    if inferred_type and existing.asset_type in (None, "other", ITAssetType.OTHER):
                                        asset_data["asset_type"] = inferred_type
                                if existing.mac_address is None and mac:
                                    asset_data["mac_address"] = mac
                                if existing.room_id is None and network_range_room_id:
                                    asset_data["room_id"] = network_range_room_id
                                await self.asset_service.update_it_asset(existing.id, asset_data)
                                assets_updated += 1
                                asset_for_obs = existing
                            else:
                                asset_data["name"] = chosen_name
                                asset_data["asset_type"] = inferred_type or "other"
                                asset_data["mac_address"] = mac
                                asset_data["room_id"] = network_range_room_id
                                asset_for_obs = await self.asset_service.create_it_asset(asset_data)
                                if asset_for_obs:
                                    assets_created += 1

                            if asset_for_obs:
                                # Snapshot pour la détection web (probe hors
                                # verrou) : après commit, les attributs expirent
                                # et un accès concurrent forcerait un lazy-load.
                                web_target = {
                                    "id": asset_for_obs.id,
                                    "ip_address": asset_for_obs.ip_address,
                                    "asset_type": asset_for_obs.asset_type,
                                    "management_url": asset_for_obs.management_url,
                                    "management_url_source": asset_for_obs.management_url_source,
                                }
                                try:
                                    await self.asset_service.create_observation(
                                        asset_for_obs.id,
                                        "online",
                                        response_time,
                                        "ping",
                                        {"ip": ip, "mac": mac},
                                    )
                                except Exception as obs_err:
                                    # Ne pas faire échouer tout le scan pour une observation
                                    await self.db.rollback()
                                    scan_errors.append(f"{ip}: observation: {obs_err}"[:300])

                        # Détection de l'interface web d'administration :
                        # réseau HORS verrou (non bloquant, timeouts courts),
                        # écriture DB sérialisée dans le verrou.
                        if web_detector is not None and web_target is not None:
                            try:
                                web_probe, web_update = await self.asset_service.probe_management_interface(
                                    web_detector,
                                    web_target["ip_address"],
                                    web_target["asset_type"],
                                    web_target["management_url"],
                                    web_target["management_url_source"],
                                )
                                async with self._db_lock:
                                    await self.asset_service.record_management_probe(
                                        web_target["id"], web_probe, update_url=web_update
                                    )
                            except Exception as web_err:
                                # La détection web ne doit jamais faire échouer le scan.
                                async with self._db_lock:
                                    try:
                                        await self.db.rollback()
                                    except Exception:
                                        pass
                                    scan_errors.append(f"{ip}: interface web: {web_err}"[:300])
                    # Suivi en direct : publier la progression toutes les 5 hôtes
                    # scannés, et immédiatement lorsqu'un hôte est trouvé
                    if reachable or hosts_scanned % 5 == 0:
                        async with self._db_lock:
                            await self.asset_service.update_discovery_log_progress(
                                log_id,
                                hosts_scanned=hosts_scanned,
                                hosts_found=hosts_found,
                                assets_created=assets_created,
                                assets_updated=assets_updated,
                            )

            await asyncio.gather(*[scan_host(ip) for ip in hosts])

            await self.asset_service.complete_discovery_log(
                log_id,
                "success",
                hosts_scanned=hosts_scanned,
                hosts_found=hosts_found,
                assets_created=assets_created,
                assets_updated=assets_updated,
                errors="; ".join(scan_errors[:5]) or None,
            )

            network_range.last_scan_at = datetime.now(UTC)
            network_range.last_scan_status = "success"
            await self.db.commit()

            return {
                "hosts_scanned": hosts_scanned,
                "hosts_found": hosts_found,
                "assets_created": assets_created,
                "assets_updated": assets_updated,
            }

        except Exception as e:
            # Rollback obligatoire : une exception en cours de flush laisse la
            # session dans l'état "pending rollback", les écritures suivantes échoueraient
            try:
                await self.db.rollback()
                await self.asset_service.complete_discovery_log(
                    log_id,
                    "failed",
                    errors=str(e)[:500],
                )
            except Exception:
                pass
            try:
                network_range.last_scan_at = datetime.now(UTC)
                network_range.last_scan_status = "failed"
                await self.db.commit()
            except Exception:
                pass
            return {"error": str(e)}


class AssetMonitoringService:
    def __init__(
        self,
        db: AsyncSession,
        audit: AuditService = None,
        current_user: User = None,
    ):
        self.db = db
        self.audit = audit
        self.current_user = current_user
        self.asset_service = ITAssetService(db, audit, current_user)
        self.discovery_service = NetworkDiscoveryService(db, audit, current_user)
        self._semaphore = asyncio.Semaphore(100)

    async def refresh_due_management_urls(self) -> dict:
        """Actualiser périodiquement les URL de gestion périmées (délégué)."""
        return await self.asset_service.refresh_due_management_urls()

    async def check_asset(self, asset_id: int) -> dict:
        asset = await self.asset_service.get_it_asset(asset_id)
        if not asset:
            return {"error": "Asset non trouvé"}

        now = datetime.now(UTC)

        # Équipement sans IP : ne pas pinguer ni modifier le statut
        if not asset.ip_address:
            await self.asset_service.update_it_asset(asset_id, {
                "last_check": now,
            })
            return {"status": asset.status, "message": "Aucune adresse IP configurée"}

        old_status_raw = asset.status
        old_status_str = str(old_status_raw.value if hasattr(old_status_raw, "value") else old_status_raw).lower()
        is_maintenance = old_status_str == "maintenance"
        threshold = getattr(settings, "IT_MONITORING_FAILURE_THRESHOLD", 2)

        reachable, response_time = await self.discovery_service._ping_host(asset.ip_address)

        # Enregistrer l'observation technique
        await self.asset_service.create_observation(
            asset_id,
            "online" if reachable else "offline",
            response_time,
            "ping",
            {"ip": asset.ip_address},
        )

        # 1. Règle Maintenance : le statut reste "maintenance", aucune alerte générée
        if is_maintenance:
            update_data = {"last_check": now}
            if reachable:
                update_data["last_seen"] = now
                update_data["consecutive_failures"] = 0
            await self.asset_service.update_it_asset(asset_id, update_data)
            return {
                "status": "maintenance",
                "reachable": reachable,
                "response_time_ms": response_time,
            }

        # 2. Équipement joignable
        if reachable:
            update_data = {
                "status": "online",
                "consecutive_failures": 0,
                "last_seen": now,
                "last_check": now,
            }
            await self.asset_service.update_it_asset(asset_id, update_data)

            # Auto-résolution des alertes d'injoignabilité ouvertes
            await self.asset_service.resolve_active_unreachable_alerts(asset_id)

            return {
                "status": "online",
                "response_time_ms": response_time,
                "consecutive_failures": 0,
            }

        # 3. Équipement injoignable (échec)
        failures = (asset.consecutive_failures or 0) + 1
        update_data = {
            "consecutive_failures": failures,
            "last_check": now,
        }

        # Hystérésis : basculement hors ligne uniquement si le seuil est atteint
        if failures >= threshold:
            update_data["status"] = "offline"
            await self.asset_service.update_it_asset(asset_id, update_data)

            # Créer ou mettre à jour (déduplication) l'alerte de panne
            severity = "critical" if failures >= 3 else "warning"
            await self.asset_service.create_alert(
                asset_id,
                "unreachable",
                severity,
                f"Équipement {asset.name} ({asset.ip_address}) injoignable ({failures} échecs consécutifs)",
                {
                    "old_status": old_status_str,
                    "new_status": "offline",
                    "consecutive_failures": failures,
                    "ip": asset.ip_address,
                },
            )
            return {
                "status": "offline",
                "response_time_ms": None,
                "consecutive_failures": failures,
            }
        else:
            # Seuil non atteint : l'équipement conserve son statut précédent
            await self.asset_service.update_it_asset(asset_id, update_data)
            return {
                "status": old_status_str,
                "response_time_ms": None,
                "consecutive_failures": failures,
            }

    async def check_all_assets(self, batch_size: int = 20) -> dict:
        from app.db.session import AsyncSessionLocal

        result = await self.db.execute(
            select(ITAsset.id)
            .where(ITAsset.is_active == True)
            .where(ITAsset.ip_address.isnot(None))
        )
        asset_ids = [row[0] for row in result.all()]

        checked = 0
        online = 0
        offline = 0

        async def _check_one(aid: int) -> dict:
            # Session dédiée par vérification pour éviter les conflits concurrents
            async with AsyncSessionLocal() as db:
                try:
                    svc = AssetMonitoringService(db)
                    return await svc.check_asset(aid)
                except Exception as e:
                    print(f"[MONITORING] Erreur check asset {aid}: {e}")
                    return {"error": str(e)}
                finally:
                    await db.close()

        for i in range(0, len(asset_ids), batch_size):
            batch = asset_ids[i:i + batch_size]
            tasks = [_check_one(aid) for aid in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, dict) and "status" in r:
                    checked += 1
                    if r["status"] == "online":
                        online += 1
                    else:
                        offline += 1

        return {
            "checked": checked,
            "online": online,
            "offline": offline,
        }

    async def monitoring_loop(self, interval_seconds: int = 300):
        while True:
            try:
                async for db in self._get_db():
                    service = AssetMonitoringService(db)
                    await service.check_all_assets()
                    break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[IT-MONITORING] Erreur: {e}")
            await asyncio.sleep(interval_seconds)

    async def _get_db(self):
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()


async def get_it_asset_service(
    db: AsyncSession,
    current_user: User,
) -> ITAssetService:
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    return ITAssetService(db, audit=audit, current_user=current_user)


async def get_network_discovery_service(
    db: AsyncSession,
    current_user: User,
) -> NetworkDiscoveryService:
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    return NetworkDiscoveryService(db, audit=audit, current_user=current_user)


async def get_asset_monitoring_service(
    db: AsyncSession,
    current_user: User,
) -> AssetMonitoringService:
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    return AssetMonitoringService(db, audit=audit, current_user=current_user)
