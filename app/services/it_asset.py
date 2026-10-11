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

from app.models import ITAsset, NetworkRange, DiscoveryLog, AssetObservation, ITAlert, ITAssetHistory, Room, Building, Site
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
    for hint, vendor in _SNMP_VENDOR_HINTS:
        if hint in descr:
            parsed["vendor"] = vendor
            break
    return parsed


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
        self._semaphore = asyncio.Semaphore(50)

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
        from pysnmp.hlapi import (
            SnmpEngine,
            CommunityData,
            UdpTransportTarget,
            ContextData,
            ObjectType,
            ObjectIndex,
            getCmd,
            nextCmd,
        )

        try:
            mp_model = 1 if str(version).strip().lower().lstrip("v").startswith("1") else 2
            auth_data = CommunityData(community, mpModel=mp_model)

            transport = UdpTransportTarget(
                (ip, port),
                timeout=timeout,
                retries=retries,
            )

            # OID de base pour les informations de l'équipement
            oids = [
                "1.3.6.1.2.1.1.1",  # sysDescr (description du système)
                "1.3.6.1.2.1.1.2",  # sysObjectID
                "1.3.6.1.2.1.1.3",  # sysUpTime
                "1.3.6.1.2.1.1.4",  # sysContact
                "1.3.6.1.2.1.1.5",  # sysName
                "1.3.6.1.2.1.1.6",  # sysLocation
                "1.3.6.1.2.1.1.8",  # ifNumber
            ]

            results = {}

            # Essayer d'abord getCmd (single request)
            error_indication, error_status, error_index, var_binds = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: getCmd(
                    SnmpEngine(),
                    auth_data,
                    transport,
                    ContextData(),
                    * [ObjectType(ObjectIndex(o)) for o in oids],
                ),
            )

            if error_indication:
                # Échec getCmd, essayer nextCmd (walk)
                for oid in oids:
                    error_indication, error_status, error_index, var_binds = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: nextCmd(
                            SnmpEngine(),
                            auth_data,
                            transport,
                            ContextData(),
                            ObjectType(ObjectIndex(oid)),
                        ),
                    )
                    for name, val in var_binds:
                        if error_status:
                            break
                        results[oid] = str(val)
            else:
                for name, val in var_binds:
                    results[str(name)] = str(val)

            return results if results else None

        except Exception as e:
            # Erreur SNMP - ne pas faire planter la boucle
            print(f"[SNMP] Erreur collecte depuis {ip}: {e}")
            return None

    async def scan_network_range(self, network_range_id: int) -> dict:
        network_range = await self.asset_service.get_network_range(network_range_id)
        if not network_range:
            return {"error": "Plage réseau non trouvée"}

        log = await self.asset_service.create_discovery_log(network_range_id)

        try:
            network = IPv4Network(network_range.cidr, strict=False) if ':' not in network_range.cidr else IPv6Network(network_range.cidr, strict=False)
            hosts = [str(ip) for ip in network.hosts()]
            total_hosts = len(hosts)

            hosts_scanned = 0
            hosts_found = 0
            assets_created = 0
            assets_updated = 0

            async def scan_host(ip: str):
                nonlocal hosts_scanned, hosts_found, assets_created, assets_updated
                async with self._semaphore:
                    reachable, response_time = await self._ping_host(ip)
                    hosts_scanned += 1

                    if reachable:
                        hosts_found += 1
                        mac = await self._get_mac_from_arp(ip)

                        existing = None
                        if mac:
                            existing = await self.asset_service.get_it_asset_by_mac(mac)
                        if not existing:
                            existing = await self.asset_service.get_it_asset_by_ip(ip)

                        discovery_data = {"response_time_ms": response_time}
                        snmp_fields = {}

                        if network_range.snmp_enabled:
                            snmp_raw = await self._get_snmp_info(
                                ip,
                                network_range.snmp_community or "public",
                                network_range.snmp_version or "2c",
                                retries=1,
                                port=network_range.snmp_port or 161,
                            )
                            if snmp_raw:
                                parsed = _parse_snmp_results(snmp_raw)
                                discovery_data["snmp"] = {**parsed, "raw": snmp_raw}

                                def _snmp_set(field: str, value):
                                    # Priorité Manuel > SNMP : ne jamais écraser une valeur existante
                                    if not value:
                                        return
                                    if existing is not None and getattr(existing, field, None) is not None:
                                        return
                                    snmp_fields[field] = value

                                _snmp_set("snmp_manufacturer", parsed.get("vendor"))
                                _snmp_set("snmp_contact", parsed.get("sys_contact"))
                                _snmp_set("snmp_location", parsed.get("sys_location"))

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
                                asset_data["name"] = f"Host {ip}"
                            if existing.mac_address is None and mac:
                                asset_data["mac_address"] = mac
                            await self.asset_service.update_it_asset(existing.id, asset_data)
                            assets_updated += 1
                        else:
                            asset_data["name"] = (
                                (discovery_data.get("snmp") or {}).get("sys_name") or f"Host {ip}"
                            )
                            asset_data["asset_type"] = "other"
                            asset_data["mac_address"] = mac
                            asset_data["room_id"] = 1
                            await self.asset_service.create_it_asset(asset_data)
                            assets_created += 1

                        await self.asset_service.create_observation(
                            existing.id if existing else 0,
                            "online",
                            response_time,
                            "ping",
                            {"ip": ip, "mac": mac},
                        )

            await asyncio.gather(*[scan_host(ip) for ip in hosts])

            await self.asset_service.complete_discovery_log(
                log.id,
                "success",
                hosts_scanned=hosts_scanned,
                hosts_found=hosts_found,
                assets_created=assets_created,
                assets_updated=assets_updated,
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
            await self.asset_service.complete_discovery_log(
                log.id,
                "failed",
                errors=str(e),
            )
            network_range.last_scan_at = datetime.now(UTC)
            network_range.last_scan_status = "failed"
            await self.db.commit()
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