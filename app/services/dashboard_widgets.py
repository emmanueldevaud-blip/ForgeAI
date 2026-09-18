from app.services.dashboard import dashboard_registry, WidgetDefinition


def _get_buildings_stats():
    async def loader(db):
        from sqlalchemy import select, func
        from app.models.buildings import Building, Room

        total = (await db.execute(
            select(func.count(Building.id)).where(Building.is_active == True)
        )).scalar_one()

        rooms = (await db.execute(
            select(func.count(Room.id)).where(Room.is_active == True)
        )).scalar_one()

        return {
            "total_buildings": total,
            "total_rooms": rooms,
        }
    return loader


def _get_equipment_stats():
    async def loader(db):
        from sqlalchemy import select, func
        from app.models.equipment import Equipment

        total = (await db.execute(
            select(func.count(Equipment.id)).where(Equipment.is_active == True)
        )).scalar_one()

        breakdown = (await db.execute(
            select(func.count(Equipment.id)).where(
                Equipment.is_active == True,
                Equipment.status == "en_panne",
            )
        )).scalar_one()

        inactive = (await db.execute(
            select(func.count(Equipment.id)).where(
                Equipment.is_active == True,
                Equipment.status == "hors_service",
            )
        )).scalar_one()

        return {
            "total": total,
            "breakdown": breakdown,
            "inactive": inactive,
        }
    return loader


def _get_housing_stats():
    async def loader(db):
        from sqlalchemy import select, func
        from app.models.housing import Housing, Occupancy
        from datetime import date, datetime

        today = date.today()
        now = datetime.utcnow()

        total = (await db.execute(
            select(func.count(Housing.id)).where(Housing.is_active == True)
        )).scalar_one()

        occupied = (await db.execute(
            select(func.count(func.distinct(Occupancy.housing_id))).where(
                Occupancy.status.in_(["confirmed", "in_progress"]),
                Occupancy.arrival_date <= now,
                Occupancy.departure_date >= now,
            )
        )).scalar_one()

        arrivals = (await db.execute(
            select(func.count(Occupancy.id)).where(
                Occupancy.status.in_(["confirmed", "in_progress"]),
                func.date(Occupancy.arrival_date) == today,
            )
        )).scalar_one()

        departures = (await db.execute(
            select(func.count(Occupancy.id)).where(
                Occupancy.status.in_(["confirmed", "in_progress", "completed"]),
                func.date(Occupancy.departure_date) == today,
            )
        )).scalar_one()

        to_clean = 0

        return {
            "total": total,
            "occupied": occupied,
            "free": max(0, total - occupied),
            "arrivals": arrivals,
            "departures": departures,
            "to_clean": to_clean,
            "occupancy_rate": round((occupied / total * 100) if total > 0 else 0, 1),
        }
    return loader


def _get_maintenance_stats():
    async def loader(db):
        from sqlalchemy import select, func, and_
        from app.models.maintenance import (
            MaintenanceRequest,
            MaintenanceWorkOrder,
            MaintenancePlan,
        )
        from datetime import date, timedelta

        today = date.today()

        open_requests = (await db.execute(
            select(func.count(MaintenanceRequest.id)).where(
                MaintenanceRequest.status.notin_(["terminee", "cloturee", "annulee"])
            )
        )).scalar_one()

        open_work_orders = (await db.execute(
            select(func.count(MaintenanceWorkOrder.id)).where(
                MaintenanceWorkOrder.status.notin_(["termine", "cloture", "annule"])
            )
        )).scalar_one()

        overdue = (await db.execute(
            select(func.count(MaintenanceWorkOrder.id)).where(and_(
                MaintenanceWorkOrder.planned_date < today,
                MaintenanceWorkOrder.status.notin_(["termine", "cloture", "annule"]),
            ))
        )).scalar_one()

        preventive_due = (await db.execute(
            select(func.count(MaintenancePlan.id)).where(and_(
                MaintenancePlan.is_active == True,
                MaintenancePlan.next_due_date <= today + timedelta(days=30),
                MaintenancePlan.next_due_date >= today,
            ))
        )).scalar_one()

        return {
            "open_requests": open_requests,
            "open_work_orders": open_work_orders,
            "overdue": overdue,
            "preventive_due": preventive_due,
        }
    return loader


MODULE_WIDGETS = [
    # ---- Bâtiments ----
    WidgetDefinition(
        id="building.total",
        module="buildings",
        title="Bâtiments",
        description="Nombre total de bâtiments actifs",
        permission="building.view",
        widget_type="counter",
        width="sm",
        order=0,
        data_loader=_get_buildings_stats(),
        link="/buildings",
        icon="building",
    ),
    WidgetDefinition(
        id="building.rooms",
        module="buildings",
        title="Pièces",
        description="Nombre total de pièces",
        permission="building.view",
        widget_type="counter",
        width="sm",
        order=1,
        data_loader=_get_buildings_stats(),
        link="/buildings",
        icon="building",
    ),

    # ---- Équipements ----
    WidgetDefinition(
        id="equipment.total",
        module="equipment",
        title="Équipements",
        description="Nombre total d'équipements actifs",
        permission="equipment.view",
        widget_type="counter",
        width="sm",
        order=0,
        data_loader=_get_equipment_stats(),
        link="/equipment",
        icon="tool",
    ),
    WidgetDefinition(
        id="equipment.breakdown",
        module="equipment",
        title="En panne",
        description="Équipements en état de panne",
        permission="equipment.view",
        widget_type="alert",
        width="sm",
        order=1,
        data_loader=_get_equipment_stats(),
        link="/equipment",
        icon="tool",
    ),
    WidgetDefinition(
        id="equipment.inactive",
        module="equipment",
        title="Hors service",
        description="Équipements hors service",
        permission="equipment.view",
        widget_type="alert",
        width="sm",
        order=2,
        data_loader=_get_equipment_stats(),
        link="/equipment",
        icon="tool",
    ),

    # ---- Hébergements ----
    WidgetDefinition(
        id="housing.occupied",
        module="housing",
        title="Occupés",
        description="Hébergements actuellement occupés",
        permission="housing.view",
        widget_type="counter",
        width="sm",
        order=0,
        data_loader=_get_housing_stats(),
        link="/housing/housings",
        icon="home",
    ),
    WidgetDefinition(
        id="housing.free",
        module="housing",
        title="Libres",
        description="Hébergements disponibles",
        permission="housing.view",
        widget_type="counter",
        width="sm",
        order=1,
        data_loader=_get_housing_stats(),
        link="/housing/housings",
        icon="home",
    ),
    WidgetDefinition(
        id="housing.arrivals",
        module="housing",
        title="Arrivées du jour",
        description="Arrivées prévues aujourd'hui",
        permission="housing.view",
        widget_type="counter",
        width="sm",
        order=2,
        data_loader=_get_housing_stats(),
        link="/housing/planning",
        icon="home",
    ),
    WidgetDefinition(
        id="housing.departures",
        module="housing",
        title="Départs du jour",
        description="Départs prévus aujourd'hui",
        permission="housing.view",
        widget_type="counter",
        width="sm",
        order=3,
        data_loader=_get_housing_stats(),
        link="/housing/planning",
        icon="home",
    ),
    WidgetDefinition(
        id="housing.to_clean",
        module="housing",
        title="À nettoyer",
        description="Hébergements en attente de nettoyage",
        permission="housing.view",
        widget_type="alert",
        width="sm",
        order=4,
        data_loader=_get_housing_stats(),
        link="/housing/cleaning",
        icon="sparkles",
    ),
    WidgetDefinition(
        id="housing.occupancy_rate",
        module="housing",
        title="Taux d'occupation",
        description="Pourcentage d'occupation global",
        permission="housing.view",
        widget_type="counter",
        width="sm",
        order=5,
        data_loader=_get_housing_stats(),
        link="/housing/housings",
        icon="home",
    ),

    # ---- Maintenance ----
    WidgetDefinition(
        id="maintenance.open_requests",
        module="maintenance",
        title="Demandes ouvertes",
        description="Demandes de maintenance en cours",
        permission="maintenance.view",
        widget_type="counter",
        width="sm",
        order=0,
        data_loader=_get_maintenance_stats(),
        link="/maintenance/requests",
        icon="wrench",
    ),
    WidgetDefinition(
        id="maintenance.open_work_orders",
        module="maintenance",
        title="OT ouverts",
        description="Ordres de travail en cours",
        permission="maintenance.view",
        widget_type="counter",
        width="sm",
        order=1,
        data_loader=_get_maintenance_stats(),
        link="/maintenance/work-orders",
        icon="wrench",
    ),
    WidgetDefinition(
        id="maintenance.overdue",
        module="maintenance",
        title="En retard",
        description="Ordres de travail en retard",
        permission="maintenance.view",
        widget_type="alert",
        width="sm",
        order=2,
        data_loader=_get_maintenance_stats(),
        link="/maintenance/work-orders",
        icon="wrench",
    ),
    WidgetDefinition(
        id="maintenance.preventive_due",
        module="maintenance",
        title="Préventif à venir",
        description="Maintenances préventives dans les 30 prochains jours",
        permission="maintenance.view",
        widget_type="counter",
        width="sm",
        order=3,
        data_loader=_get_maintenance_stats(),
        link="/maintenance/preventive",
        icon="wrench",
    ),
]


def register_all_widget_providers():
    for widget in MODULE_WIDGETS:
        dashboard_registry.register(widget)
