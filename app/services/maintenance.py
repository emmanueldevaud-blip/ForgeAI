from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.maintenance import (
    MaintenanceProvider,
    MaintenanceContract,
    ContractEquipment,
    MaintenancePart,
    MaintenanceRequest,
    MaintenanceWorkOrder,
    MaintenanceIntervenant,
    MaintenanceIntervention,
    MaintenancePlan,
    MaintenancePlanChecklist,
    WorkOrderPart,
    MaintenanceCost,
    MaintenanceStatusHistory,
)
from app.models.equipment import Equipment
from app.models.user import User
from app.models.buildings import Room, Building, Site
from app.services.audit import AuditService


VALID_REQUEST_STATUSES = [
    "nouvelle", "a_qualifier", "planifiee", "en_cours",
    "en_attente", "terminee", "cloturee", "annulee",
]

VALID_REQUEST_PRIORITIES = [
    "basse", "normale", "haute", "urgente", "critique",
]

VALID_WORK_ORDER_STATUSES = [
    "nouveau", "planifie", "en_cours", "en_attente",
    "termine", "cloture", "annule",
]

VALID_MAINTENANCE_TYPES = [
    "corrective", "preventive", "conditionnelle",
    "predictive", "ameliorative",
]

VALID_FREQUENCIES = [
    "quotidienne", "hebdomadaire", "mensuelle",
    "trimestrielle", "semestrielle", "annuelle",
]

VALID_COST_TYPES = [
    "main_doeuvre", "pieces", "consommables",
    "prestataire", "autres",
]


def _generate_request_number() -> str:
    now = datetime.now(timezone.utc)
    return f"DM-{now.strftime('%Y%m')}-{now.strftime('%H%M%S')}"


def _generate_work_order_number() -> str:
    now = datetime.now(timezone.utc)
    return f"OT-{now.strftime('%Y%m')}-{now.strftime('%H%M%S')}"


async def _build_location_summary(db: AsyncSession, equipment_id: int | None) -> str | None:
    if not equipment_id:
        return None
    result = await db.execute(
        select(Equipment)
        .where(Equipment.id == equipment_id)
    )
    equipment = result.scalar_one_or_none()
    if not equipment or not equipment.room_id:
        return None
    result = await db.execute(
        select(Room)
        .options(
            selectinload(Room.building).selectinload(Building.site)
        )
        .where(Room.id == equipment.room_id)
    )
    room = result.scalar_one_or_none()
    if not room:
        return None
    parts = []
    if room.building and room.building.site:
        parts.append(room.building.site.name)
    if room.building:
        parts.append(room.building.name)
    parts.append(room.name)
    return " > ".join(parts)


async def _get_equipment_summary(db: AsyncSession, equipment_id: int) -> dict | None:
    result = await db.execute(
        select(Equipment)
        .options(
            selectinload(Equipment.equipment_type),
            selectinload(Equipment.room)
        )
        .where(Equipment.id == equipment_id)
    )
    eq = result.scalar_one_or_none()
    if not eq:
        return None
    return {
        "id": eq.id,
        "reference": eq.reference,
        "name": eq.name,
        "status": eq.status,
        "type_name": eq.equipment_type.name if eq.equipment_type else None,
        "room_name": eq.room.name if eq.room else None,
    }


async def _get_user_summary(db: AsyncSession, user_id: int) -> dict | None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


async def _record_status_change(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    old_status: str | None,
    new_status: str,
    changed_by: int | None,
    comment: str | None = None,
):
    history = MaintenanceStatusHistory(
        entity_type=entity_type,
        entity_id=entity_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comment=comment,
    )
    db.add(history)


class MaintenanceService:
    def __init__(self, db: AsyncSession, audit: AuditService, current_user: User):
        self.db = db
        self.audit = audit
        self.current_user = current_user

    # ============================================================
    # PROVIDERS
    # ============================================================

    async def search_providers(
        self, *, page=1, page_size=20, search=None,
        is_active=None, sort_by="created_at", sort_order="desc"
    ):
        query = select(MaintenanceProvider)
        count_query = select(func.count(MaintenanceProvider.id))

        if search:
            pattern = f"%{search}%"
            condition = or_(
                MaintenanceProvider.name.ilike(pattern),
                MaintenanceProvider.contact_name.ilike(pattern),
                MaintenanceProvider.email.ilike(pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        if is_active is not None:
            query = query.where(MaintenanceProvider.is_active == is_active)
            count_query = count_query.where(MaintenanceProvider.is_active == is_active)

        total = (await self.db.execute(count_query)).scalar_one()

        sort_col = getattr(MaintenanceProvider, sort_by, MaintenanceProvider.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        query = query.limit(page_size).offset((page - 1) * page_size)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_provider(self, provider_id: int):
        result = await self.db.execute(
            select(MaintenanceProvider).where(MaintenanceProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def create_provider(self, data: dict):
        provider = MaintenanceProvider(**data)
        self.db.add(provider)
        await self.db.flush()
        await self.audit.log(
            action="provider_create", module="maintenance",
            user=self.current_user, object_type="provider",
            object_id=str(provider.id), object_repr=provider.name,
            new_values=data,
        )
        return provider

    async def update_provider(self, provider_id: int, data: dict):
        provider = await self.get_provider(provider_id)
        if not provider:
            return None
        old_values = {k: getattr(provider, k) for k in data if hasattr(provider, k)}
        for key, value in data.items():
            if value is not None and hasattr(provider, key):
                setattr(provider, key, value)
        await self.db.flush()
        await self.audit.log(
            action="provider_update", module="maintenance",
            user=self.current_user, object_type="provider",
            object_id=str(provider.id), object_repr=provider.name,
            old_values=old_values, new_values=data,
        )
        return provider

    # ============================================================
    # PARTS
    # ============================================================

    async def search_parts(
        self, *, page=1, page_size=20, search=None,
        is_active=None, sort_by="created_at", sort_order="desc"
    ):
        query = select(MaintenancePart)
        count_query = select(func.count(MaintenancePart.id))

        if search:
            pattern = f"%{search}%"
            condition = or_(
                MaintenancePart.reference.ilike(pattern),
                MaintenancePart.name.ilike(pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        if is_active is not None:
            query = query.where(MaintenancePart.is_active == is_active)
            count_query = count_query.where(MaintenancePart.is_active == is_active)

        total = (await self.db.execute(count_query)).scalar_one()

        sort_col = getattr(MaintenancePart, sort_by, MaintenancePart.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        query = query.limit(page_size).offset((page - 1) * page_size)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_part(self, part_id: int):
        result = await self.db.execute(
            select(MaintenancePart).where(MaintenancePart.id == part_id)
        )
        return result.scalar_one_or_none()

    async def create_part(self, data: dict):
        part = MaintenancePart(**data)
        self.db.add(part)
        await self.db.flush()
        await self.audit.log(
            action="part_create", module="maintenance",
            user=self.current_user, object_type="part",
            object_id=str(part.id), object_repr=part.name,
            new_values=data,
        )
        return part

    async def update_part(self, part_id: int, data: dict):
        part = await self.get_part(part_id)
        if not part:
            return None
        old_values = {k: getattr(part, k) for k in data if hasattr(part, k)}
        for key, value in data.items():
            if value is not None and hasattr(part, key):
                setattr(part, key, value)
        await self.db.flush()
        await self.audit.log(
            action="part_update", module="maintenance",
            user=self.current_user, object_type="part",
            object_id=str(part.id), object_repr=part.name,
            old_values=old_values, new_values=data,
        )
        return part

    # ============================================================
    # CONTRACTS
    # ============================================================

    async def search_contracts(
        self, *, page=1, page_size=20, search=None,
        provider_id=None, is_active=None, sort_by="created_at", sort_order="desc"
    ):
        query = select(MaintenanceContract).options(
            selectinload(MaintenanceContract.provider),
            selectinload(MaintenanceContract.equipment_links),
        )
        count_query = select(func.count(MaintenanceContract.id))

        if search:
            pattern = f"%{search}%"
            condition = or_(
                MaintenanceContract.reference.ilike(pattern),
                MaintenanceContract.subject.ilike(pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        if provider_id is not None:
            query = query.where(MaintenanceContract.provider_id == provider_id)
            count_query = count_query.where(MaintenanceContract.provider_id == provider_id)

        if is_active is not None:
            query = query.where(MaintenanceContract.is_active == is_active)
            count_query = count_query.where(MaintenanceContract.is_active == is_active)

        total = (await self.db.execute(count_query)).scalar_one()

        sort_col = getattr(MaintenanceContract, sort_by, MaintenanceContract.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        query = query.limit(page_size).offset((page - 1) * page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().unique().all())
        return items, total

    async def get_contract(self, contract_id: int):
        result = await self.db.execute(
            select(MaintenanceContract)
            .options(
                selectinload(MaintenanceContract.provider),
                selectinload(MaintenanceContract.equipment_links)
                    .selectinload(ContractEquipment.equipment),
            )
            .where(MaintenanceContract.id == contract_id)
        )
        return result.scalar_one_or_none()

    async def create_contract(self, data: dict):
        equipment_ids = data.pop("equipment_ids", [])
        contract = MaintenanceContract(**data)
        self.db.add(contract)
        await self.db.flush()

        for eq_id in equipment_ids:
            link = ContractEquipment(contract_id=contract.id, equipment_id=eq_id)
            self.db.add(link)
        await self.db.flush()

        await self.audit.log(
            action="contract_create", module="maintenance",
            user=self.current_user, object_type="contract",
            object_id=str(contract.id), object_repr=contract.reference,
            new_values={**data, "equipment_ids": equipment_ids},
        )
        return contract

    async def update_contract(self, contract_id: int, data: dict):
        contract = await self.get_contract(contract_id)
        if not contract:
            return None
        equipment_ids = data.pop("equipment_ids", None)
        old_values = {k: getattr(contract, k) for k in data if hasattr(contract, k)}
        for key, value in data.items():
            if value is not None and hasattr(contract, key):
                setattr(contract, key, value)

        if equipment_ids is not None:
            for link in contract.equipment_links:
                await self.db.delete(link)
            for eq_id in equipment_ids:
                link = ContractEquipment(contract_id=contract.id, equipment_id=eq_id)
                self.db.add(link)

        await self.db.flush()
        await self.audit.log(
            action="contract_update", module="maintenance",
            user=self.current_user, object_type="contract",
            object_id=str(contract.id), object_repr=contract.reference,
            old_values=old_values, new_values=data,
        )
        return contract

    # ============================================================
    # MAINTENANCE REQUESTS
    # ============================================================

    async def search_requests(
        self, *, page=1, page_size=20, search=None,
        status=None, priority=None, equipment_id=None,
        requested_by=None, sort_by="created_at", sort_order="desc"
    ):
        query = select(MaintenanceRequest)
        count_query = select(func.count(MaintenanceRequest.id))

        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(or_(
                MaintenanceRequest.number.ilike(pattern),
                MaintenanceRequest.title.ilike(pattern),
            ))
        if status:
            conditions.append(MaintenanceRequest.status == status)
        if priority:
            conditions.append(MaintenanceRequest.priority == priority)
        if equipment_id:
            conditions.append(MaintenanceRequest.equipment_id == equipment_id)
        if requested_by:
            conditions.append(MaintenanceRequest.requested_by == requested_by)

        for c in conditions:
            query = query.where(c)
            count_query = count_query.where(c)

        total = (await self.db.execute(count_query)).scalar_one()

        sort_col = getattr(MaintenanceRequest, sort_by, MaintenanceRequest.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        query = query.limit(page_size).offset((page - 1) * page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def get_request(self, request_id: int):
        result = await self.db.execute(
            select(MaintenanceRequest).where(MaintenanceRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def create_request(self, data: dict):
        number = _generate_request_number()
        data["number"] = number
        data["requested_by"] = self.current_user.id

        if data.get("equipment_id"):
            data["location_summary"] = await _build_location_summary(
                self.db, data["equipment_id"]
            )

        request = MaintenanceRequest(**data)
        self.db.add(request)
        await self.db.flush()

        await _record_status_change(
            self.db, "request", request.id, None, "nouvelle", self.current_user.id
        )
        await self.audit.log(
            action="request_create", module="maintenance",
            user=self.current_user, object_type="request",
            object_id=str(request.id), object_repr=f"{request.number} - {request.title}",
            new_values=data,
        )
        return request

    async def update_request(self, request_id: int, data: dict):
        request = await self.get_request(request_id)
        if not request:
            return None

        comment = data.pop("comment", None)
        new_status = data.pop("status", None)
        old_status = request.status

        old_values = {}
        for k in data:
            if hasattr(request, k):
                old_values[k] = getattr(request, k)

        for key, value in data.items():
            if value is not None and hasattr(request, key):
                setattr(request, key, value)

        if data.get("equipment_id") and data["equipment_id"] != request.equipment_id:
            request.location_summary = await _build_location_summary(
                self.db, data["equipment_id"]
            )

        if new_status and new_status != old_status:
            if new_status not in VALID_REQUEST_STATUSES:
                raise ValueError(f"Statut invalide: {new_status}")
            request.status = new_status
            await _record_status_change(
                self.db, "request", request.id, old_status, new_status,
                self.current_user.id, comment
            )

        await self.db.flush()
        await self.audit.log(
            action="request_update", module="maintenance",
            user=self.current_user, object_type="request",
            object_id=str(request.id), object_repr=f"{request.number} - {request.title}",
            old_values=old_values, new_values=data,
        )
        return request

    # ============================================================
    # WORK ORDERS
    # ============================================================

    async def search_work_orders(
        self, *, page=1, page_size=20, search=None,
        status=None, priority=None, maintenance_type=None,
        equipment_id=None, responsible_id=None,
        sort_by="created_at", sort_order="desc"
    ):
        query = select(MaintenanceWorkOrder)
        count_query = select(func.count(MaintenanceWorkOrder.id))

        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(or_(
                MaintenanceWorkOrder.number.ilike(pattern),
                MaintenanceWorkOrder.title.ilike(pattern),
            ))
        if status:
            conditions.append(MaintenanceWorkOrder.status == status)
        if priority:
            conditions.append(MaintenanceWorkOrder.priority == priority)
        if maintenance_type:
            conditions.append(MaintenanceWorkOrder.maintenance_type == maintenance_type)
        if equipment_id:
            conditions.append(MaintenanceWorkOrder.equipment_id == equipment_id)
        if responsible_id:
            conditions.append(MaintenanceWorkOrder.responsible_id == responsible_id)

        for c in conditions:
            query = query.where(c)
            count_query = count_query.where(c)

        total = (await self.db.execute(count_query)).scalar_one()

        sort_col = getattr(MaintenanceWorkOrder, sort_by, MaintenanceWorkOrder.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        query = query.limit(page_size).offset((page - 1) * page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def get_work_order(self, wo_id: int):
        result = await self.db.execute(
            select(MaintenanceWorkOrder)
            .options(
                selectinload(MaintenanceWorkOrder.equipment),
                selectinload(MaintenanceWorkOrder.request),
                selectinload(MaintenanceWorkOrder.provider),
                selectinload(MaintenanceWorkOrder.contract),
                selectinload(MaintenanceWorkOrder.responsible),
                selectinload(MaintenanceWorkOrder.intervenants).selectinload(MaintenanceIntervenant.user),
                selectinload(MaintenanceWorkOrder.interventions),
                selectinload(MaintenanceWorkOrder.parts_used).selectinload(WorkOrderPart.part),
                selectinload(MaintenanceWorkOrder.costs),
            )
            .where(MaintenanceWorkOrder.id == wo_id)
        )
        return result.scalar_one_or_none()

    async def create_work_order(self, data: dict):
        number = _generate_work_order_number()
        data["number"] = number

        if data.get("equipment_id"):
            data["location_summary"] = await _build_location_summary(
                self.db, data["equipment_id"]
            )

        wo = MaintenanceWorkOrder(**data)
        self.db.add(wo)
        await self.db.flush()

        await _record_status_change(
            self.db, "work_order", wo.id, None, "nouveau", self.current_user.id
        )
        await self.audit.log(
            action="work_order_create", module="maintenance",
            user=self.current_user, object_type="work_order",
            object_id=str(wo.id), object_repr=f"{wo.number} - {wo.title}",
            new_values=data,
        )
        return wo

    async def update_work_order(self, wo_id: int, data: dict):
        wo = await self.get_work_order(wo_id)
        if not wo:
            return None

        comment = data.pop("comment", None)
        new_status = data.pop("status", None)
        old_status = wo.status

        old_values = {}
        for k in data:
            if hasattr(wo, k):
                old_values[k] = getattr(wo, k)

        for key, value in data.items():
            if value is not None and hasattr(wo, key):
                setattr(wo, key, value)

        if data.get("equipment_id") and data["equipment_id"] != wo.equipment_id:
            wo.location_summary = await _build_location_summary(
                self.db, data["equipment_id"]
            )

        if new_status and new_status != old_status:
            if new_status not in VALID_WORK_ORDER_STATUSES:
                raise ValueError(f"Statut invalide: {new_status}")
            wo.status = new_status
            await _record_status_change(
                self.db, "work_order", wo.id, old_status, new_status,
                self.current_user.id, comment
            )

        await self.db.flush()
        await self.audit.log(
            action="work_order_update", module="maintenance",
            user=self.current_user, object_type="work_order",
            object_id=str(wo.id), object_repr=f"{wo.number} - {wo.title}",
            old_values=old_values, new_values=data,
        )
        return wo

    async def create_work_order_from_request(self, request_id: int, data: dict | None = None):
        request = await self.get_request(request_id)
        if not request:
            return None

        wo_data = {
            "title": request.title,
            "description": request.description,
            "equipment_id": request.equipment_id,
            "request_id": request.id,
            "priority": request.priority,
            "maintenance_type": "corrective",
        }
        if data:
            wo_data.update(data)

        wo = await self.create_work_order(wo_data)

        if request.status == "nouvelle":
            await self.update_request(request_id, {"status": "a_qualifier"})

        return wo

    # ============================================================
    # INTERVENANTS
    # ============================================================

    async def add_intervenant(self, wo_id: int, data: dict):
        wo = await self.get_work_order(wo_id)
        if not wo:
            return None
        intervenant = MaintenanceIntervenant(work_order_id=wo_id, **data)
        self.db.add(intervenant)
        await self.db.flush()
        return intervenant

    async def update_intervenant(self, intervenant_id: int, data: dict):
        result = await self.db.execute(
            select(MaintenanceIntervenant).where(MaintenanceIntervenant.id == intervenant_id)
        )
        intervenant = result.scalar_one_or_none()
        if not intervenant:
            return None
        for key, value in data.items():
            if value is not None and hasattr(intervenant, key):
                setattr(intervenant, key, value)
        await self.db.flush()
        return intervenant

    async def remove_intervenant(self, intervenant_id: int):
        result = await self.db.execute(
            select(MaintenanceIntervenant).where(MaintenanceIntervenant.id == intervenant_id)
        )
        intervenant = result.scalar_one_or_none()
        if not intervenant:
            return False
        await self.db.delete(intervenant)
        await self.db.flush()
        return True

    # ============================================================
    # INTERVENTIONS
    # ============================================================

    async def add_intervention(self, wo_id: int, data: dict):
        wo = await self.get_work_order(wo_id)
        if not wo:
            return None
        intervention = MaintenanceIntervention(work_order_id=wo_id, **data)
        self.db.add(intervention)
        await self.db.flush()
        return intervention

    # ============================================================
    # WORK ORDER PARTS
    # ============================================================

    async def add_wo_part(self, wo_id: int, data: dict):
        wo = await self.get_work_order(wo_id)
        if not wo:
            return None
        part_link = WorkOrderPart(work_order_id=wo_id, **data)
        self.db.add(part_link)
        await self.db.flush()
        return part_link

    async def remove_wo_part(self, part_link_id: int):
        result = await self.db.execute(
            select(WorkOrderPart).where(WorkOrderPart.id == part_link_id)
        )
        link = result.scalar_one_or_none()
        if not link:
            return False
        await self.db.delete(link)
        await self.db.flush()
        return True

    # ============================================================
    # COSTS
    # ============================================================

    async def add_cost(self, wo_id: int, data: dict):
        wo = await self.get_work_order(wo_id)
        if not wo:
            return None
        cost = MaintenanceCost(work_order_id=wo_id, **data)
        self.db.add(cost)
        await self.db.flush()
        return cost

    async def get_wo_costs_total(self, wo_id: int) -> Decimal:
        result = await self.db.execute(
            select(func.coalesce(func.sum(MaintenanceCost.amount), 0))
            .where(MaintenanceCost.work_order_id == wo_id)
        )
        return result.scalar_one()

    # ============================================================
    # PLANS (Préventif)
    # ============================================================

    async def search_plans(
        self, *, page=1, page_size=20, search=None,
        equipment_id=None, frequency=None, is_active=None,
        sort_by="created_at", sort_order="desc"
    ):
        query = select(MaintenancePlan).options(
            selectinload(MaintenancePlan.checklist_items),
            selectinload(MaintenancePlan.equipment),
        )
        count_query = select(func.count(MaintenancePlan.id))

        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(MaintenancePlan.title.ilike(pattern))
        if equipment_id:
            conditions.append(MaintenancePlan.equipment_id == equipment_id)
        if frequency:
            conditions.append(MaintenancePlan.frequency == frequency)
        if is_active is not None:
            conditions.append(MaintenancePlan.is_active == is_active)

        for c in conditions:
            query = query.where(c)
            count_query = count_query.where(c)

        total = (await self.db.execute(count_query)).scalar_one()

        sort_col = getattr(MaintenancePlan, sort_by, MaintenancePlan.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        query = query.limit(page_size).offset((page - 1) * page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().unique().all())
        return items, total

    async def get_plan(self, plan_id: int):
        result = await self.db.execute(
            select(MaintenancePlan)
            .options(
                selectinload(MaintenancePlan.checklist_items),
                selectinload(MaintenancePlan.equipment),
            )
            .where(MaintenancePlan.id == plan_id)
        )
        return result.scalar_one_or_none()

    async def create_plan(self, data: dict):
        checklist_items = data.pop("checklist_items", [])
        plan = MaintenancePlan(**data)
        self.db.add(plan)
        await self.db.flush()

        for item_data in checklist_items:
            item = MaintenancePlanChecklist(plan_id=plan.id, **item_data)
            self.db.add(item)
        await self.db.flush()

        await self.audit.log(
            action="plan_create", module="maintenance",
            user=self.current_user, object_type="plan",
            object_id=str(plan.id), object_repr=plan.title,
            new_values=data,
        )
        return plan

    async def update_plan(self, plan_id: int, data: dict):
        plan = await self.get_plan(plan_id)
        if not plan:
            return None
        checklist_items = data.pop("checklist_items", None)
        old_values = {k: getattr(plan, k) for k in data if hasattr(plan, k)}
        for key, value in data.items():
            if value is not None and hasattr(plan, key):
                setattr(plan, key, value)

        if checklist_items is not None:
            for item in plan.checklist_items:
                await self.db.delete(item)
            for item_data in checklist_items:
                item = MaintenancePlanChecklist(plan_id=plan.id, **item_data)
                self.db.add(item)

        await self.db.flush()
        await self.audit.log(
            action="plan_update", module="maintenance",
            user=self.current_user, object_type="plan",
            object_id=str(plan.id), object_repr=plan.title,
            old_values=old_values, new_values=data,
        )
        return plan

    # ============================================================
    # DASHBOARD
    # ============================================================

    async def get_dashboard(self):
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year_start = month_start.replace(month=1)

        open_requests = (await self.db.execute(
            select(func.count(MaintenanceRequest.id))
            .where(MaintenanceRequest.status.notin_(["terminee", "cloturee", "annulee"]))
        )).scalar_one()

        open_work_orders = (await self.db.execute(
            select(func.count(MaintenanceWorkOrder.id))
            .where(MaintenanceWorkOrder.status.notin_(["termine", "cloture", "annule"]))
        )).scalar_one()

        overdue_work_orders = (await self.db.execute(
            select(func.count(MaintenanceWorkOrder.id))
            .where(and_(
                MaintenanceWorkOrder.planned_date < date.today(),
                MaintenanceWorkOrder.status.notin_(["termine", "cloture", "annule"]),
            ))
        )).scalar_one()

        planned_interventions = (await self.db.execute(
            select(func.count(MaintenanceWorkOrder.id))
            .where(and_(
                MaintenanceWorkOrder.planned_date >= date.today(),
                MaintenanceWorkOrder.status.in_(["nouveau", "planifie"]),
            ))
        )).scalar_one()

        preventive_due_soon = (await self.db.execute(
            select(func.count(MaintenancePlan.id))
            .where(and_(
                MaintenancePlan.is_active == True,
                MaintenancePlan.next_due_date <= date.today() + timedelta(days=30),
                MaintenancePlan.next_due_date >= date.today(),
            ))
        )).scalar_one()

        equipment_in_breakdown = (await self.db.execute(
            select(func.count(Equipment.id))
            .where(Equipment.status == "en_panne")
        )).scalar_one()

        total_cost_month_result = (await self.db.execute(
            select(func.coalesce(func.sum(MaintenanceCost.amount), 0))
            .join(MaintenanceWorkOrder)
            .where(MaintenanceWorkOrder.created_at >= month_start)
        )).scalar_one()

        total_cost_year_result = (await self.db.execute(
            select(func.coalesce(func.sum(MaintenanceCost.amount), 0))
            .join(MaintenanceWorkOrder)
            .where(MaintenanceWorkOrder.created_at >= year_start)
        )).scalar_one()

        corrective_count = (await self.db.execute(
            select(func.count(MaintenanceWorkOrder.id))
            .where(and_(
                MaintenanceWorkOrder.maintenance_type == "corrective",
                MaintenanceWorkOrder.created_at >= month_start,
            ))
        )).scalar_one()

        preventive_count = (await self.db.execute(
            select(func.count(MaintenanceWorkOrder.id))
            .where(and_(
                MaintenanceWorkOrder.maintenance_type == "preventive",
                MaintenanceWorkOrder.created_at >= month_start,
            ))
        )).scalar_one()

        avg_hours_result = (await self.db.execute(
            select(func.coalesce(func.avg(MaintenanceWorkOrder.actual_duration_hours), 0))
            .where(MaintenanceWorkOrder.actual_duration_hours.isnot(None))
        )).scalar_one()

        return {
            "open_requests": open_requests,
            "open_work_orders": open_work_orders,
            "overdue_work_orders": overdue_work_orders,
            "planned_interventions": planned_interventions,
            "preventive_due_soon": preventive_due_soon,
            "equipment_in_breakdown": equipment_in_breakdown,
            "total_cost_month": Decimal(str(total_cost_month_result)),
            "total_cost_year": Decimal(str(total_cost_year_result)),
            "corrective_count_month": corrective_count,
            "preventive_count_month": preventive_count,
            "avg_intervention_hours": Decimal(str(avg_hours_result)),
        }
