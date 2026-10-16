"""Tests de la Phase 1 : fiabilisation du moteur de supervision IT.

Vérifications :
- Maintien du statut maintenance pendant la supervision (aucune alerte générée) ;
- Hystérésis : deux échecs consécutifs avant de déclarer un équipement offline ;
- Remise à zéro du compteur d'échecs après un contrôle réussi ;
- Déduplication d'alerte lors d'une panne persistante (une seule alerte ouverte) ;
- Résolution automatique de l'alerte d'injoignabilité lors du retour en ligne ;
- Fonctionnement de l'acquittement et de la résolution manuelle ;
- Gestion propre des équipements sans adresse IP ;
- Robustesse SNMP : timeout immédiat sans cascade d'OIDs unitaires ;
- API globale des alertes (GET /api/it-assets/alerts) avec filtres.
"""

import pytest
from datetime import UTC, datetime
from sqlalchemy import select

from app.models import ITAsset, ITAlert, ITAssetStatus, ITAlertType, ITAlertSeverity, Room, Building, Site
from app.models.user import User
from app.services.it_asset import (
    ITAssetService,
    AssetMonitoringService,
    NetworkDiscoveryService,
)


async def _setup_topology(db):
    """Créer site, bâtiment et local de test."""
    site = Site(reference="SITE-SUP", name="Site Supervision")
    db.add(site)
    await db.flush()

    building = Building(site_id=site.id, reference="BAT-A", name="Bâtiment A")
    db.add(building)
    await db.flush()

    room = Room(building_id=building.id, reference="LOC-01", name="Local Serveurs")
    db.add(room)
    await db.flush()

    return site, building, room


async def _create_test_user(db) -> User:
    user = User(
        username="admin_supervision",
        email="admin_sup@example.com",
        password_hash="hash",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


# ============================================================
# 1. Statut Maintenance & Équipements sans IP
# ============================================================


async def test_monitoring_maintains_maintenance_status_and_no_alert(db_session, monkeypatch):
    """Un équipement en maintenance doit conserver son statut et ne jamais générer d'alerte."""
    _, _, room = await _setup_topology(db_session)
    service = ITAssetService(db_session)

    asset = await service.create_it_asset({
        "name": "Serveur-Maintenance",
        "asset_type": "server",
        "ip_address": "10.0.0.10",
        "status": "maintenance",
        "room_id": room.id,
    })

    # Simuler le ping injoignable
    async def mock_ping(self, ip, timeout=2.0):
        return False, None

    monkeypatch.setattr(NetworkDiscoveryService, "_ping_host", mock_ping)

    monitor_svc = AssetMonitoringService(db_session)
    res = await monitor_svc.check_asset(asset.id)

    assert res["status"] == "maintenance"
    assert res["reachable"] is False

    # Vérifier l'état en base
    refreshed = await service.get_it_asset(asset.id)
    assert refreshed.status == ITAssetStatus.MAINTENANCE
    assert refreshed.last_check is not None

    # Aucune alerte ne doit exister
    alerts = await service.get_asset_alerts(asset.id)
    assert len(alerts) == 0


async def test_monitoring_asset_without_ip_handled_gracefully(db_session):
    """Un équipement sans IP ne doit pas lever d'erreur ni être marqué offline."""
    _, _, room = await _setup_topology(db_session)
    service = ITAssetService(db_session)

    asset = await service.create_it_asset({
        "name": "Switch-Non-Configure",
        "asset_type": "switch",
        "ip_address": None,
        "status": "online",
        "room_id": room.id,
    })

    monitor_svc = AssetMonitoringService(db_session)
    res = await monitor_svc.check_asset(asset.id)

    assert res["status"] == "online"
    assert "message" in res

    refreshed = await service.get_it_asset(asset.id)
    assert refreshed.status == ITAssetStatus.ONLINE
    assert refreshed.last_check is not None


# ============================================================
# 2. Hystérésis & Compteur d'échecs consécutifs
# ============================================================


async def test_monitoring_hysteresis_two_failures_before_offline(db_session, monkeypatch):
    """Deux échecs consécutifs sont requis avant de déclarer l'équipement hors ligne."""
    _, _, room = await _setup_topology(db_session)
    service = ITAssetService(db_session)

    asset = await service.create_it_asset({
        "name": "Routeur-Frontal",
        "asset_type": "router",
        "ip_address": "10.0.0.1",
        "status": "online",
        "room_id": room.id,
    })
    assert asset.consecutive_failures == 0

    # Simuler échec de ping
    async def mock_ping_fail(self, ip, timeout=2.0):
        return False, None

    monkeypatch.setattr(NetworkDiscoveryService, "_ping_host", mock_ping_fail)

    monitor_svc = AssetMonitoringService(db_session)

    # 1er échec consécutif
    res1 = await monitor_svc.check_asset(asset.id)
    assert res1["status"] == "online"  # Conserve online grâce à l'hystérésis
    assert res1["consecutive_failures"] == 1

    asset_step1 = await service.get_it_asset(asset.id)
    assert asset_step1.status == ITAssetStatus.ONLINE
    assert asset_step1.consecutive_failures == 1

    # Aucune alerte ne doit être créée au premier échec
    alerts_step1 = await service.get_asset_alerts(asset.id)
    assert len(alerts_step1) == 0

    # 2ème échec consécutif -> seuil atteint (threshold = 2)
    res2 = await monitor_svc.check_asset(asset.id)
    assert res2["status"] == "offline"
    assert res2["consecutive_failures"] == 2

    asset_step2 = await service.get_it_asset(asset.id)
    assert asset_step2.status == ITAssetStatus.OFFLINE
    assert asset_step2.consecutive_failures == 2

    # Une alerte unreachable doit être créée
    alerts_step2 = await service.get_asset_alerts(asset.id, resolved=False)
    assert len(alerts_step2) == 1
    assert alerts_step2[0].alert_type == ITAlertType.UNREACHABLE
    assert alerts_step2[0].severity == ITAlertSeverity.WARNING

    # 3ème échec consécutif -> panne persistante, pas de doublon d'alerte
    res3 = await monitor_svc.check_asset(asset.id)
    assert res3["consecutive_failures"] == 3

    alerts_step3 = await service.get_asset_alerts(asset.id, resolved=False)
    assert len(alerts_step3) == 1  # Toujours une seule alerte ouverte (déduplication)
    assert alerts_step3[0].severity == ITAlertSeverity.CRITICAL


# ============================================================
# 3. Récupération & Auto-résolution d'alerte
# ============================================================


async def test_monitoring_recovery_resets_failures_and_resolves_alert(db_session, monkeypatch):
    """Un contrôle réussi réinitialise les échecs et résout automatiquement l'alerte de panne."""
    _, _, room = await _setup_topology(db_session)
    service = ITAssetService(db_session)

    asset = await service.create_it_asset({
        "name": "NAS-Backup",
        "asset_type": "server",
        "ip_address": "10.0.0.50",
        "status": "online",
        "room_id": room.id,
    })

    # 1. Provoquer la panne (2 échecs)
    async def mock_ping_fail(self, ip, timeout=2.0):
        return False, None

    monkeypatch.setattr(NetworkDiscoveryService, "_ping_host", mock_ping_fail)
    monitor_svc = AssetMonitoringService(db_session)

    await monitor_svc.check_asset(asset.id)
    await monitor_svc.check_asset(asset.id)

    asset_offline = await service.get_it_asset(asset.id)
    assert asset_offline.status == ITAssetStatus.OFFLINE

    open_alerts = await service.get_asset_alerts(asset.id, resolved=False)
    assert len(open_alerts) == 1
    alert_id = open_alerts[0].id

    # 2. Retour en ligne de l'équipement
    async def mock_ping_success(self, ip, timeout=2.0):
        return True, 12.5

    monkeypatch.setattr(NetworkDiscoveryService, "_ping_host", mock_ping_success)

    res = await monitor_svc.check_asset(asset.id)
    assert res["status"] == "online"
    assert res["consecutive_failures"] == 0

    asset_online = await service.get_it_asset(asset.id)
    assert asset_online.status == ITAssetStatus.ONLINE
    assert asset_online.consecutive_failures == 0

    # L'alerte doit être automatiquement résolue
    all_alerts = await service.get_asset_alerts(asset.id)
    assert len(all_alerts) == 1
    assert all_alerts[0].id == alert_id
    assert all_alerts[0].resolved is True
    assert all_alerts[0].resolved_at is not None
    assert all_alerts[0].details.get("auto_resolved") is True


# ============================================================
# 4. Acquittement et Résolution Manuelle
# ============================================================


async def test_manual_alert_acknowledge_and_resolve(db_session):
    """Vérifier que l'acquittement et la résolution manuelle fonctionnent avec les bons champs."""
    _, _, room = await _setup_topology(db_session)
    user = await _create_test_user(db_session)
    service = ITAssetService(db_session, current_user=user)

    asset = await service.create_it_asset({
        "name": "Switch-Core",
        "asset_type": "switch",
        "ip_address": "10.0.0.2",
        "status": "online",
        "room_id": room.id,
    })

    alert = await service.create_alert(
        asset.id,
        "high_latency",
        "warning",
        "Latence anormale mesurée",
    )
    assert alert.acknowledged is False
    assert alert.resolved is False

    # Acquittement manuel
    ack_alert = await service.acknowledge_alert(alert.id, user)
    assert ack_alert.acknowledged is True
    assert ack_alert.acknowledged_by == user.id
    assert ack_alert.acknowledged_at is not None
    assert ack_alert.resolved is False

    # Résolution manuelle
    res_alert = await service.resolve_alert(alert.id)
    assert res_alert.resolved is True
    assert res_alert.resolved_at is not None


# ============================================================
# 5. Recherche globale et filtres des alertes
# ============================================================


async def test_search_alerts_global_filters(db_session):
    """Vérifier le filtrage des alertes (resolved, severity, type, room_id, site_id)."""
    site, _, room = await _setup_topology(db_session)
    service = ITAssetService(db_session)

    asset1 = await service.create_it_asset({
        "name": "Imprimante-Etage",
        "asset_type": "printer",
        "ip_address": "10.0.0.80",
        "room_id": room.id,
    })
    asset2 = await service.create_it_asset({
        "name": "Poste-01",
        "asset_type": "pc_windows",
        "ip_address": "10.0.0.101",
        "room_id": None,  # Hors local
    })

    # Alerte 1 sur asset1 : non résolue, warning
    a1 = await service.create_alert(asset1.id, "unreachable", "warning", "Panne 1")
    # Alerte 2 sur asset2 : résolue, critical
    a2 = await service.create_alert(asset2.id, "snmp_error", "critical", "Panne 2")
    await service.resolve_alert(a2.id)

    # 1. Filtre par non-résolue
    items, total = await service.search_alerts(resolved=False)
    assert total >= 1
    assert any(item.id == a1.id for item in items)
    assert not any(item.id == a2.id for item in items)

    # 2. Filtre par sévérité
    items, total = await service.search_alerts(severity="critical")
    assert any(item.id == a2.id for item in items)
    assert not any(item.id == a1.id for item in items)

    # 3. Filtre par type
    items, total = await service.search_alerts(alert_type="unreachable")
    assert any(item.id == a1.id for item in items)

    # 4. Filtre par local (room_id)
    items, total = await service.search_alerts(room_id=room.id)
    assert any(item.id == a1.id for item in items)
    assert not any(item.id == a2.id for item in items)

    # 5. Filtre par site (site_id)
    items, total = await service.search_alerts(site_id=site.id)
    assert any(item.id == a1.id for item in items)
    assert not any(item.id == a2.id for item in items)


# ============================================================
# 6. Robustesse SNMP
# ============================================================


async def test_snmp_get_info_abandons_immediately_on_timeout(db_session, monkeypatch):
    """En cas de timeout réseau, _get_snmp_info doit abandonner sans cascade d'OIDs unitaires."""
    discovery = NetworkDiscoveryService(db_session)
    call_counts = {"get_cmd": 0, "next_cmd": 0}

    # Simuler get_cmd qui échoue par timeout
    async def mock_get_cmd(*args, **kwargs):
        call_counts["get_cmd"] += 1
        return ("RequestTimedOut", 0, 0, [])

    async def mock_next_cmd(*args, **kwargs):
        call_counts["next_cmd"] += 1
        return (None, 0, 0, [])

    from pysnmp.hlapi import asyncio as hlapi_async
    monkeypatch.setattr(hlapi_async, "get_cmd", mock_get_cmd)
    monkeypatch.setattr(hlapi_async, "next_cmd", mock_next_cmd)

    res = await discovery._get_snmp_info("192.168.99.99", "public", max_total_timeout=1.0)
    assert res is None
    assert call_counts["get_cmd"] == 1
    # next_cmd ne doit PAS avoir été appelé (pas de boucle d'OIDs en cascade)
    assert call_counts["next_cmd"] == 0
