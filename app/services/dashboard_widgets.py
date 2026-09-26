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
        from app.models.housing import Housing, Occupancy, Cleaning
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

        to_clean = (await db.execute(
            select(func.count(Cleaning.id)).where(Cleaning.status == "planned")
        )).scalar_one()

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


def _get_agenda_stats():
    async def loader(db):
        from sqlalchemy import select, func
        from app.models.agenda import AgendaPresence
        from datetime import date

        today = date.today()

        today_count = (await db.execute(
            select(func.count(AgendaPresence.id)).where(
                AgendaPresence.presence_date == today
            )
        )).scalar_one()

        meals_today = (await db.execute(
            select(func.count(AgendaPresence.id)).where(
                AgendaPresence.presence_date == today,
                AgendaPresence.needs_meal == True,
            )
        )).scalar_one()

        return {
            "today_count": today_count,
            "meals_today": meals_today,
        }
    return loader


def _get_volunteers_stats():
    async def loader(db):
        from sqlalchemy import select, func
        from app.models.volunteer import Volunteer

        active = (await db.execute(
            select(func.count(Volunteer.id)).where(Volunteer.is_active == True)
        )).scalar_one()

        return {"active": active}
    return loader


def _get_sport_stats():
    async def loader(db):
        from sqlalchemy import select, func
        from app.models.sport import SportActivity
        from datetime import datetime, timedelta

        since = datetime.utcnow() - timedelta(days=7)

        week_activities = (await db.execute(
            select(func.count(SportActivity.id)).where(
                SportActivity.started_at >= since
            )
        )).scalar_one()

        return {"week_activities": week_activities}
    return loader


def _get_administrative_stats():
    async def loader(db):
        from sqlalchemy import select, func
        from app.models.administrative import AdministrativeMonthlySession
        from datetime import date

        today = date.today()

        month_sessions = (await db.execute(
            select(func.count(AdministrativeMonthlySession.id)).where(
                AdministrativeMonthlySession.year == today.year,
                AdministrativeMonthlySession.month == today.month,
            )
        )).scalar_one()

        return {"month_sessions": month_sessions}
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
        link="/housing/planning",
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
        link="/housing/planning",
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
        link="/housing/planning",
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

    # ---- Agenda ----
    WidgetDefinition(
        id="agenda.today",
        module="agenda",
        title="Présences aujourd’hui",
        description="Personnes inscrites aujourd’hui",
        permission="agenda.access",
        widget_type="counter",
        width="sm",
        order=0,
        data_loader=_get_agenda_stats(),
        link="/agenda",
        icon="calendar-days",
    ),
    WidgetDefinition(
        id="agenda.meals",
        module="agenda",
        title="Repas à prévoir",
        description="Repas à organiser aujourd’hui",
        permission="agenda.access",
        widget_type="alert",
        width="sm",
        order=1,
        data_loader=_get_agenda_stats(),
        link="/agenda",
        icon="calendar-days",
    ),

    # ---- Volontaires ----
    WidgetDefinition(
        id="volunteers.active",
        module="volunteers",
        title="Volontaires actifs",
        description="Volontaires disponibles actuellement",
        permission="volunteers.view",
        widget_type="counter",
        width="sm",
        order=0,
        data_loader=_get_volunteers_stats(),
        link="/volunteers",
        icon="users",
    ),

    # ---- Sport ----
    WidgetDefinition(
        id="sport.week",
        module="sport",
        title="Activités (7 jours)",
        description="Entraînements et sorties sur 7 jours",
        permission="sport.access",
        widget_type="counter",
        width="sm",
        order=0,
        data_loader=_get_sport_stats(),
        link="/sport",
        icon="run",
    ),

    # ---- Administratif ----
    WidgetDefinition(
        id="administrative.sessions",
        module="administratif",
        title="Sessions du mois",
        description="Sessions programmées ce mois-ci",
        permission="administration.programs.view",
        widget_type="counter",
        width="sm",
        order=0,
        data_loader=_get_administrative_stats(),
        link="/administratif",
        icon="clipboard",
    ),
]


def register_all_widget_providers():
    for widget in MODULE_WIDGETS:
        dashboard_registry.register(widget)
