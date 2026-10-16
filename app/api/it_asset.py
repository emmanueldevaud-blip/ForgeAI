import math
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_module_enabled, require_permission
from app.db.session import get_db
from app.models import DiscoveryLog
from app.models.user import User
from app.schemas.it_asset import (
    AssetObservationResponse,
    ITAlertAcknowledge,
    ITAlertResponse,
    ITAlertListResponse,
    ITAssetCreate,
    ITAssetImportRequest,
    ITAssetImportResponse,
    ITAssetListParams,
    ITAssetListResponse,
    ITAssetResponse,
    ITAssetUpdate,
    ITAssetHistoryResponse,
    MessageResponse,
    NetworkRangeCreate,
    NetworkRangeListResponse,
    NetworkRangeResponse,
    NetworkRangeUpdate,
    DiscoveryLogResponse,
)
from app.services.audit import get_audit_service
from app.services.it_asset import (
    ITAssetService,
    NetworkDiscoveryService,
    get_it_asset_service,
    get_network_discovery_service,
)

router = APIRouter(
    prefix="/it-assets",
    tags=["it-assets"],
    dependencies=[Depends(require_module_enabled("it_asset"))],
)


def _build_asset_response(asset) -> ITAssetResponse:
    resp = ITAssetResponse.model_validate(asset)
    if asset.room:
        from app.schemas.it_asset import RoomSummaryResponse, BuildingSummaryResponse, SiteSummaryResponse
        resp.room = RoomSummaryResponse.model_validate(asset.room)
        if asset.room.building:
            resp.building = BuildingSummaryResponse.model_validate(asset.room.building)
            if asset.room.building.site:
                resp.site = SiteSummaryResponse.model_validate(asset.room.building.site)
    return resp


async def _get_asset_service(
    current_user: User = Depends(require_permission("it_asset.view")),
    db: AsyncSession = Depends(get_db),
) -> ITAssetService:
    audit = await get_audit_service(db)
    return ITAssetService(db, audit=audit, current_user=current_user)


async def _get_discovery_service(
    current_user: User = Depends(require_permission("it_asset.manage_discovery")),
    db: AsyncSession = Depends(get_db),
) -> NetworkDiscoveryService:
    audit = await get_audit_service(db)
    return NetworkDiscoveryService(db, audit=audit, current_user=current_user)


def _count_range_hosts(cidr: str) -> int:
    from ipaddress import IPv4Network
    try:
        if ':' in cidr:
            return 0  # IPv6 : trop d'hôtes, pas de barre de progression
        return max(IPv4Network(cidr, strict=False).num_addresses - 2, 0)
    except ValueError:
        return 0


async def _run_scan_background(range_id: int, log_id: int, current_user: Optional[User]) -> None:
    """Exécuter un scan réseau en tâche de fond avec sa propre session DB."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        audit = await get_audit_service(session)
        service = NetworkDiscoveryService(session, audit=audit, current_user=current_user)
        log = await session.get(DiscoveryLog, log_id)
        await service.scan_network_range(range_id, log=log)


async def _run_discover_background(scans: list, current_user: Optional[User]) -> None:
    """Exécuter plusieurs scans séquentiellement en tâche de fond."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        audit = await get_audit_service(session)
        for range_id, log_id in scans:
            service = NetworkDiscoveryService(session, audit=audit, current_user=current_user)
            log = await session.get(DiscoveryLog, log_id)
            await service.scan_network_range(range_id, log=log)


# ============================================================
# IT ASSETS
# ============================================================

@router.get("", response_model=ITAssetListResponse)
async def list_it_assets(
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
    service: ITAssetService = Depends(_get_asset_service),
):
    items, total = await service.search_it_assets(
        page=page,
        page_size=page_size,
        search=search,
        asset_type=asset_type,
        status=status,
        room_id=room_id,
        site_id=site_id,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return ITAssetListResponse(
        items=[_build_asset_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/network-ranges", response_model=NetworkRangeListResponse)
async def list_network_ranges(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    current_user: User = Depends(require_permission("it_asset.view")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)

    items, total = await service.search_network_ranges(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return NetworkRangeListResponse(
        items=[NetworkRangeResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/alerts", response_model=ITAlertListResponse)
async def list_all_alerts(
    page: int = 1,
    page_size: int = 20,
    resolved: Optional[bool] = None,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    asset_id: Optional[int] = None,
    room_id: Optional[int] = None,
    site_id: Optional[int] = None,
    sort_order: str = "desc",
    current_user: User = Depends(require_permission("it_asset.view")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)

    items, total = await service.search_alerts(
        page=page,
        page_size=page_size,
        resolved=resolved,
        severity=severity,
        alert_type=alert_type,
        asset_id=asset_id,
        room_id=room_id,
        site_id=site_id,
        sort_order=sort_order,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return ITAlertListResponse(
        items=[ITAlertResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{asset_id}", response_model=ITAssetResponse)
async def get_it_asset(
    asset_id: int,
    service: ITAssetService = Depends(_get_asset_service),
):
    asset = await service.get_it_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset IT non trouvé")
    return _build_asset_response(asset)


@router.post("", response_model=ITAssetResponse, status_code=status.HTTP_201_CREATED)
async def create_it_asset(
    data: ITAssetCreate,
    service: ITAssetService = Depends(_get_asset_service),
):
    from app.models.buildings import Room
    if data.room_id is not None:
        room = await service.db.get(Room, data.room_id)
        if not room:
            raise HTTPException(status_code=422, detail="La pièce spécifiée n'existe pas")

    if data.mac_address:
        existing = await service.get_it_asset_by_mac(data.mac_address)
        if existing:
            raise HTTPException(status_code=400, detail=f"Un asset avec cette adresse MAC existe déjà ({existing.reference})")

    if data.ip_address:
        existing = await service.get_it_asset_by_ip(data.ip_address)
        if existing:
            raise HTTPException(status_code=400, detail=f"Un asset avec cette adresse IP existe déjà ({existing.reference})")

    asset = await service.create_it_asset(data.model_dump(exclude_unset=True))
    if not asset:
        raise HTTPException(status_code=400, detail="Erreur lors de la création de l'asset")
    return _build_asset_response(asset)


@router.patch("/{asset_id}", response_model=ITAssetResponse)
async def update_it_asset(
    asset_id: int,
    data: ITAssetUpdate,
    service: ITAssetService = Depends(_get_asset_service),
):
    if data.room_id is not None:
        from app.models.buildings import Room
        room = await service.db.get(Room, data.room_id)
        if not room:
            raise HTTPException(status_code=422, detail="La pièce spécifiée n'existe pas")

    if data.mac_address is not None:
        existing = await service.get_it_asset_by_mac(data.mac_address)
        if existing and existing.id != asset_id:
            raise HTTPException(status_code=400, detail=f"Un asset avec cette adresse MAC existe déjà ({existing.reference})")

    if data.ip_address is not None:
        existing = await service.get_it_asset_by_ip(data.ip_address)
        if existing and existing.id != asset_id:
            raise HTTPException(status_code=400, detail=f"Un asset avec cette adresse IP existe déjà ({existing.reference})")

    asset = await service.update_it_asset(asset_id, data.model_dump(exclude_unset=True))
    if not asset:
        raise HTTPException(status_code=404, detail="Asset IT non trouvé")
    return _build_asset_response(asset)


@router.delete("/{asset_id}", response_model=MessageResponse)
async def delete_it_asset(
    asset_id: int,
    service: ITAssetService = Depends(_get_asset_service),
):
    success = await service.delete_it_asset(asset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Asset IT non trouvé")
    return MessageResponse(message="Asset IT supprimé")


@router.post("/import", response_model=ITAssetImportResponse)
async def import_it_assets(
    data: ITAssetImportRequest,
    service: ITAssetService = Depends(_get_asset_service),
):
    items = [item.model_dump(exclude_unset=True) for item in data.items]
    result = await service.import_it_assets(
        items,
        skip_duplicates=data.skip_duplicates,
        update_existing=data.update_existing,
    )
    return ITAssetImportResponse(**result)


@router.get("/{asset_id}/observations", response_model=list[AssetObservationResponse])
async def get_asset_observations(
    asset_id: int,
    limit: int = 100,
    service: ITAssetService = Depends(_get_asset_service),
):
    asset = await service.get_it_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset IT non trouvé")
    observations = await service.get_asset_observations(asset_id, limit)
    return [AssetObservationResponse.model_validate(o) for o in observations]


@router.get("/{asset_id}/alerts", response_model=list[ITAlertResponse])
async def get_asset_alerts(
    asset_id: int,
    resolved: Optional[bool] = None,
    service: ITAssetService = Depends(_get_asset_service),
):
    asset = await service.get_it_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset IT non trouvé")
    alerts = await service.get_asset_alerts(asset_id, resolved)
    return [ITAlertResponse.model_validate(a) for a in alerts]


@router.patch("/{asset_id}/alerts/{alert_id}/acknowledge", response_model=ITAlertResponse)
async def acknowledge_alert(
    asset_id: int,
    alert_id: int,
    data: ITAlertAcknowledge,
    current_user: User = Depends(require_permission("it_asset.manage_alerts")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)
    alert = await service.acknowledge_alert(alert_id, current_user)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return ITAlertResponse.model_validate(alert)


@router.patch("/{asset_id}/alerts/{alert_id}/resolve", response_model=ITAlertResponse)
async def resolve_alert(
    asset_id: int,
    alert_id: int,
    current_user: User = Depends(require_permission("it_asset.manage_alerts")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)
    alert = await service.resolve_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return ITAlertResponse.model_validate(alert)


@router.get("/{asset_id}/history", response_model=list[ITAssetHistoryResponse])
async def get_asset_history(
    asset_id: int,
    limit: int = 100,
    service: ITAssetService = Depends(_get_asset_service),
):
    asset = await service.get_it_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset IT non trouvé")
    history = await service.get_asset_history(asset_id, limit)
    return [ITAssetHistoryResponse.model_validate(h) for h in history]


# ============================================================
# NETWORK RANGES
# ============================================================

@router.get("/network-ranges/{range_id}", response_model=NetworkRangeResponse)
async def get_network_range(
    range_id: int,
    current_user: User = Depends(require_permission("it_asset.view")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)

    network_range = await service.get_network_range(range_id)
    if not network_range:
        raise HTTPException(status_code=404, detail="Plage réseau non trouvée")
    return NetworkRangeResponse.model_validate(network_range)


@router.post("/network-ranges", response_model=NetworkRangeResponse, status_code=status.HTTP_201_CREATED)
async def create_network_range(
    data: NetworkRangeCreate,
    current_user: User = Depends(require_permission("it_asset.manage_discovery")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)

    network_range = await service.create_network_range(data.model_dump(exclude_unset=True))
    if not network_range:
        raise HTTPException(status_code=400, detail="Erreur lors de la création (CIDR invalide ou doublon)")
    return NetworkRangeResponse.model_validate(network_range)


@router.patch("/network-ranges/{range_id}", response_model=NetworkRangeResponse)
async def update_network_range(
    range_id: int,
    data: NetworkRangeUpdate,
    current_user: User = Depends(require_permission("it_asset.manage_discovery")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)

    network_range = await service.update_network_range(range_id, data.model_dump(exclude_unset=True))
    if not network_range:
        raise HTTPException(status_code=404, detail="Plage réseau non trouvée")
    return NetworkRangeResponse.model_validate(network_range)


@router.delete("/network-ranges/{range_id}", response_model=MessageResponse)
async def delete_network_range(
    range_id: int,
    current_user: User = Depends(require_permission("it_asset.manage_discovery")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)

    success = await service.delete_network_range(range_id)
    if not success:
        raise HTTPException(status_code=404, detail="Plage réseau non trouvée")
    return MessageResponse(message="Plage réseau supprimée")


@router.post("/network-ranges/{range_id}/scan", response_model=dict)
async def scan_network_range(
    range_id: int,
    background_tasks: BackgroundTasks,
    discovery_service: NetworkDiscoveryService = Depends(_get_discovery_service),
):
    asset_service = discovery_service.asset_service
    network_range = await asset_service.get_network_range(range_id)
    if not network_range:
        raise HTTPException(status_code=404, detail="Plage réseau non trouvée")

    # Créer le log immédiatement pour pouvoir suivre la progression en direct
    log = await asset_service.create_discovery_log(range_id)
    total_hosts = _count_range_hosts(network_range.cidr)
    log.details = {"total_hosts": total_hosts}
    await discovery_service.db.commit()

    background_tasks.add_task(
        _run_scan_background, range_id, log.id, discovery_service.current_user
    )

    return {"log_id": log.id, "status": "running", "total_hosts": total_hosts}


@router.get("/network-ranges/{range_id}/logs", response_model=list[DiscoveryLogResponse])
async def get_discovery_logs(
    range_id: int,
    limit: int = 50,
    current_user: User = Depends(require_permission("it_asset.view")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)
    service = ITAssetService(db, audit=audit, current_user=current_user)

    logs = await service.get_discovery_logs(range_id, limit)
    return [DiscoveryLogResponse.model_validate(log) for log in logs]


# ============================================================
# DISCOVERY
# ============================================================

@router.post("/discover", response_model=dict)
async def discover_all_ranges(
    background_tasks: BackgroundTasks,
    discovery_service: NetworkDiscoveryService = Depends(_get_discovery_service),
):
    from app.models import NetworkRange
    from sqlalchemy import select

    db = discovery_service.db
    result = await db.execute(
        select(NetworkRange).where(NetworkRange.is_active == True, NetworkRange.scan_enabled == True)
    )
    ranges = result.scalars().all()

    scans = []
    for r in ranges:
        log = await discovery_service.asset_service.create_discovery_log(r.id)
        total_hosts = _count_range_hosts(r.cidr)
        log.details = {"total_hosts": total_hosts}
        await db.commit()
        scans.append({"range_id": r.id, "log_id": log.id, "total_hosts": total_hosts})

    if scans:
        background_tasks.add_task(
            _run_discover_background,
            [(s["range_id"], s["log_id"]) for s in scans],
            discovery_service.current_user,
        )

    return {"ranges_scanned": len(scans), "scans": scans}


# ============================================================
# MONITORING
# ============================================================

@router.post("/{asset_id}/check", response_model=dict)
async def check_asset(
    asset_id: int,
    current_user: User = Depends(require_permission("it_asset.manage_discovery")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    from app.services.it_asset import AssetMonitoringService

    audit = await get_audit_service(db)
    service = AssetMonitoringService(db, audit=audit, current_user=current_user)
    return await service.check_asset(asset_id)


@router.post("/monitor", response_model=dict)
async def monitor_all_assets(
    current_user: User = Depends(require_permission("it_asset.manage_discovery")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    from app.services.it_asset import AssetMonitoringService

    audit = await get_audit_service(db)
    service = AssetMonitoringService(db, audit=audit, current_user=current_user)
    return await service.check_all_assets()
