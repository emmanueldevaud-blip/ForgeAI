import math
import asyncio
import socket
import subprocess
import platform
from datetime import UTC, datetime
from ipaddress import IPv4Network, IPv6Network, IPv4Address, IPv6Address
from typing import Optional, List, Tuple

from sqlalchemy import select, func, or_, and_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ITAsset, ITAssetType, NetworkRange, DiscoveryLog, AssetObservation, ITAlert, ITAssetHistory, Room, Building, Site
from app.models.user import User
from app.services.audit import AuditService
from app.core.config import get_settings


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
        query = select(NetworkRange).options(selectinload(NetworkRange.site))
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
            .options(selectinload(NetworkRange.site))
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

        return network_range

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
            if value is not None and hasattr(network_range, key):
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

        return network_range

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
        retries: int = 3,
        port: int = 161,
    ) -> Optional[dict]:
        """Collecter des informations SNMP depuis un équipement."""
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

        try:
            # CommunityData : mpModel 0 = SNMPv1, 1 = SNMPv2c (2 = USM/v3, invalide ici)
            mp_model = 0 if str(version).strip().lower().lstrip("v").startswith("1") else 1
            auth_data = CommunityData(community, mpModel=mp_model)

            transport = await UdpTransportTarget.create(
                (ip, port),
                timeout=timeout,
                retries=retries,
            )
            context = ContextData()

            # OID de base pour les informations de l'équipement
            # IMPORTANT : les scalaires SNMP exigent l'instance ".0",
            # sans elle l'agent répond NoSuchInstance (valeur vide)
            oids = [
                "1.3.6.1.2.1.1.1.0",  # sysDescr (description du système)
                "1.3.6.1.2.1.1.2.0",  # sysObjectID
                "1.3.6.1.2.1.1.3.0",  # sysUpTime
                "1.3.6.1.2.1.1.4.0",  # sysContact
                "1.3.6.1.2.1.1.5.0",  # sysName
                "1.3.6.1.2.1.1.6.0",  # sysLocation
                "1.3.6.1.2.1.1.8.0",  # ifNumber
            ]
            if ":" not in ip:
                # ipNetToMediaPhysAddress pour l'IP scannée (MAC de l'équipement)
                oids.append(f"1.3.6.1.2.1.4.22.1.2.{'.'.join(ip.split('.'))}")

            def _snmp_value_to_str(oid: str, val) -> str:
                """Les adresses physiques sont binaires : les convertir en aa:bb:cc:dd:ee:ff."""
                try:
                    if '.4.22.1.2.' in oid or '.2.2.1.6.' in oid or oid.endswith('.2.2.1.6'):
                        raw = val.asOctets()
                        if len(raw) == 6:
                            return ':'.join(f'{b:02x}' for b in raw)
                except Exception:
                    pass
                return str(val)

            results = {}

            # getCmd (requête simple) — les valeurs partielles sont conservées
            error_indication, error_status, error_index, var_binds = await get_cmd(
                SnmpEngine(),
                auth_data,
                transport,
                context,
                *[ObjectType(ObjectIdentity(o)) for o in oids],
            )
            for name, val in var_binds:
                s = _snmp_value_to_str(str(name), val)
                if s:
                    results[str(name)] = s

            if results:
                # Walk ifPhysAddress : première MAC réelle (ifIndex 1 est
                # souvent la loopback sans adresse)
                error_indication, error_status, error_index, var_binds = await next_cmd(
                    SnmpEngine(),
                    auth_data,
                    transport,
                    context,
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.6')),
                )
                if not error_indication:
                    for name, val in var_binds:
                        s = _snmp_value_to_str(str(name), val)
                        if s and s != '00:00:00:00:00:00':
                            results[str(name)] = s
                            break

            if not results and error_indication:
                # Repli : marche (walk) OID par OID
                for oid in oids:
                    error_indication, error_status, error_index, var_binds = await next_cmd(
                        SnmpEngine(),
                        auth_data,
                        transport,
                        context,
                        ObjectType(ObjectIdentity(oid)),
                    )
                    if error_indication:
                        continue
                    for name, val in var_binds:
                        s = _snmp_value_to_str(str(name), val)
                        if s:
                            results[str(name)] = s

            return results if results else None

        except Exception as e:
            # Erreur SNMP - ne pas faire planter la boucle
            print(f"[SNMP] Erreur collecte depuis {ip}: {e}")
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
        try:
            transport = await UdpTransportTarget.create(
                (ip, port), timeout=timeout, retries=retries,
            )
            # Marche SNMP : next_cmd (pysnmp 7) avance d'une seule OI par appel,
            # on boucle jusqu'à sortir de la table ou manquer de réponses.
            current_oid = column_oid
            while current_oid:
                error_indication, error_status, _error_index, var_binds = await next_cmd(
                    SnmpEngine(),
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
        snmp_enabled = network_range.snmp_enabled
        snmp_community = network_range.snmp_community
        snmp_version = network_range.snmp_version
        snmp_port = network_range.snmp_port

        # Résolution MAC croisée via routeur (ex. pfSense) : configurée par
        # settings, désactivée par défaut. Construite une fois pour tout le scan.
        arp_resolver = self._build_arp_resolver(snmp_community or "public")

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

                        # Toutes les écritures DB sont sérialisées (verrou) car les
                        # tâches concurrentes partagent la même session SQLAlchemy
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

                            if existing:
                                # Priorité Manuel > scan : préserver un nom/type saisi manuellement
                                if existing.name.startswith("Host ") or not existing.name:
                                    asset_data["name"] = (
                                        (discovery_data.get("snmp") or {}).get("sys_name") or f"Host {ip}"
                                    )
                                    if inferred_type and existing.asset_type in (None, "other", ITAssetType.OTHER):
                                        asset_data["asset_type"] = inferred_type
                                if existing.mac_address is None and mac:
                                    asset_data["mac_address"] = mac
                                await self.asset_service.update_it_asset(existing.id, asset_data)
                                assets_updated += 1
                                asset_for_obs = existing
                            else:
                                asset_data["name"] = (
                                    (discovery_data.get("snmp") or {}).get("sys_name") or f"Host {ip}"
                                )
                                asset_data["asset_type"] = inferred_type or "other"
                                asset_data["mac_address"] = mac
                                asset_data["room_id"] = 1
                                asset_for_obs = await self.asset_service.create_it_asset(asset_data)
                                if asset_for_obs:
                                    assets_created += 1

                            if asset_for_obs:
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

    async def check_asset(self, asset_id: int) -> dict:
        asset = await self.asset_service.get_it_asset(asset_id)
        if not asset or not asset.ip_address:
            return {"error": "Asset non trouvé ou sans IP"}

        reachable, response_time = await self.discovery_service._ping_host(asset.ip_address)
        new_status = "online" if reachable else "offline"
        old_status = asset.status

        await self.asset_service.create_observation(
            asset_id,
            new_status,
            response_time,
            "ping",
            {"ip": asset.ip_address},
        )

        if new_status != old_status:
            await self.asset_service.update_it_asset(asset_id, {
                "status": new_status,
                "last_seen": datetime.now(UTC) if reachable else asset.last_seen,
                "last_check": datetime.now(UTC),
            })

            if new_status == "offline":
                await self.asset_service.create_alert(
                    asset_id,
                    "status_change",
                    "warning",
                    f"Asset {asset.name} ({asset.ip_address}) est passé offline",
                    {"old_status": old_status, "new_status": new_status},
                )
            elif old_status == "offline" and new_status == "online":
                await self.asset_service.create_alert(
                    asset_id,
                    "status_change",
                    "info",
                    f"Asset {asset.name} ({asset.ip_address}) est revenu online",
                    {"old_status": old_status, "new_status": new_status},
                )

        return {"status": new_status, "response_time_ms": response_time}

    async def check_all_assets(self, batch_size: int = 100) -> dict:
        result = await self.db.execute(
            select(ITAsset.id)
            .where(ITAsset.is_active == True)
            .where(ITAsset.ip_address.isnot(None))
        )
        asset_ids = [row[0] for row in result.all()]

        checked = 0
        online = 0
        offline = 0
        alerts_created = 0

        for i in range(0, len(asset_ids), batch_size):
            batch = asset_ids[i:i + batch_size]
            async with self._semaphore:
                tasks = [self.check_asset(aid) for aid in batch]
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