import math
from datetime import UTC, datetime
from typing import Optional, List

from sqlalchemy import select, func, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.buildings import Building, Level, Room, Site
from app.models.equipment import Equipment, EquipmentType
from app.models.user import User
from app.services.audit import AuditService


async def _generate_reference(db: AsyncSession) -> str:
    now = datetime.now(UTC)
    prefix = f"EQ-{now.strftime('%Y%m')}-"

    result = await db.execute(
        select(Equipment.reference)
        .where(Equipment.reference.like(f"{prefix}%"))
        .order_by(Equipment.reference.desc())
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


async def _generate_type_code(db: AsyncSession) -> str:
    result = await db.execute(
        select(EquipmentType.code)
        .where(EquipmentType.code.op('REGEXP')('^[0-9]{6}$'))
        .order_by(EquipmentType.code.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()

    if last:
        seq = int(last) + 1
    else:
        seq = 1

    return f"{seq:06d}"


class EquipmentService:
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
    # EQUIPMENT TYPES
    # ============================================================

    async def search_equipment_types(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "sort_order",
        sort_order: str = "asc",
    ) -> tuple[List[EquipmentType], int]:
        query = select(EquipmentType)
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    EquipmentType.code.ilike(search_term),
                    EquipmentType.name.ilike(search_term),
                )
            )

        if is_active is not None:
            conditions.append(EquipmentType.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "code": EquipmentType.code,
            "name": EquipmentType.name,
            "sort_order": EquipmentType.sort_order,
            "is_active": EquipmentType.is_active,
            "created_at": EquipmentType.created_at,
        }
        sort_column = allowed_sort_fields.get(sort_by, EquipmentType.sort_order)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_equipment_type(self, equipment_type_id: int) -> Optional[EquipmentType]:
        return await self.db.get(EquipmentType, equipment_type_id)

    async def get_equipment_type_by_code(self, code: str) -> Optional[EquipmentType]:
        result = await self.db.execute(
            select(EquipmentType).where(EquipmentType.code == code)
        )
        return result.scalar_one_or_none()

    async def create_equipment_type(self, data: dict) -> Optional[EquipmentType]:
        if not data.get("code"):
            data["code"] = await _generate_type_code(self.db)
        equipment_type = EquipmentType(**data)
        self.db.add(equipment_type)
        try:
            await self.db.commit()
            await self.db.refresh(equipment_type)
        except IntegrityError:
            await self.db.rollback()
            return None
        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="equipment",
                user=self.current_user,
                object_type="equipment_type",
                object_id=equipment_type.id,
                object_repr=equipment_type.name,
                new_values=data,
                status="success",
            )
        return equipment_type

    async def update_equipment_type(self, equipment_type_id: int, data: dict) -> Optional[EquipmentType]:
        equipment_type = await self.get_equipment_type(equipment_type_id)
        if not equipment_type:
            return None

        old_values = {k: getattr(equipment_type, k) for k in data.keys() if hasattr(equipment_type, k)}

        for key, value in data.items():
            if value is not None and hasattr(equipment_type, key):
                setattr(equipment_type, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(equipment_type)
        except IntegrityError:
            await self.db.rollback()
            return None

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="equipment",
                user=self.current_user,
                object_type="equipment_type",
                object_id=equipment_type.id,
                object_repr=equipment_type.name,
                old_values=old_values,
                new_values=data,
                status="success",
            )
        return equipment_type

    # ============================================================
    # EQUIPMENTS
    # ============================================================

    async def search_equipments(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        equipment_type_id: Optional[int] = None,
        status: Optional[str] = None,
        room_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Equipment], int]:
        query = select(Equipment).options(
            selectinload(Equipment.equipment_type),
            selectinload(Equipment.room).selectinload(Room.level).selectinload(Level.building).selectinload(Building.site),
        )
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    Equipment.reference.ilike(search_term),
                    Equipment.name.ilike(search_term),
                    Equipment.manufacturer.ilike(search_term),
                    Equipment.serial_number.ilike(search_term),
                )
            )

        if equipment_type_id is not None:
            conditions.append(Equipment.equipment_type_id == equipment_type_id)

        if status is not None:
            conditions.append(Equipment.status == status)

        if room_id is not None:
            conditions.append(Equipment.room_id == room_id)

        if is_active is not None:
            conditions.append(Equipment.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "reference": Equipment.reference,
            "name": Equipment.name,
            "status": Equipment.status,
            "created_at": Equipment.created_at,
            "updated_at": Equipment.updated_at,
        }
        sort_column = allowed_sort_fields.get(sort_by, Equipment.created_at)

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

    async def get_equipment(self, equipment_id: int) -> Optional[Equipment]:
        result = await self.db.execute(
            select(Equipment)
            .options(
                selectinload(Equipment.equipment_type),
                selectinload(Equipment.room).selectinload(Room.level).selectinload(Level.building).selectinload(Building.site),
            )
            .where(Equipment.id == equipment_id)
        )
        return result.scalar_one_or_none()

    async def get_equipment_by_reference(self, reference: str) -> Optional[Equipment]:
        result = await self.db.execute(
            select(Equipment).where(Equipment.reference == reference)
        )
        return result.scalar_one_or_none()

    async def create_equipment(self, data: dict) -> Optional[Equipment]:
        data["reference"] = await _generate_reference(self.db)
        equipment = Equipment(**data)
        self.db.add(equipment)
        try:
            await self.db.commit()
            await self.db.refresh(equipment)
        except IntegrityError:
            await self.db.rollback()
            return None

        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="equipment",
                user=self.current_user,
                object_type="equipment",
                object_id=equipment.id,
                object_repr=f"{equipment.reference} - {equipment.name}",
                new_values=data,
                status="success",
            )

        return await self.get_equipment(equipment.id)

    async def update_equipment(self, equipment_id: int, data: dict) -> Optional[Equipment]:
        equipment = await self.get_equipment(equipment_id)
        if not equipment:
            return None

        data.pop("reference", None)

        old_values = {k: getattr(equipment, k) for k in data.keys() if hasattr(equipment, k)}

        for key, value in data.items():
            if value is not None and hasattr(equipment, key):
                setattr(equipment, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(equipment)
        except IntegrityError:
            await self.db.rollback()
            return None

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="equipment",
                user=self.current_user,
                object_type="equipment",
                object_id=equipment.id,
                object_repr=f"{equipment.reference} - {equipment.name}",
                old_values=old_values,
                new_values=data,
                status="success",
            )

        return await self.get_equipment(equipment.id)

    async def deactivate_equipment(self, equipment_id: int) -> Optional[Equipment]:
        equipment = await self.get_equipment(equipment_id)
        if not equipment:
            return None

        old_values = {"is_active": equipment.is_active, "status": equipment.status}
        equipment.is_active = False

        try:
            await self.db.commit()
            await self.db.refresh(equipment)
        except IntegrityError:
            await self.db.rollback()
            return None

        if self.audit and self.current_user:
            await self.audit.log(
                action="deactivate",
                module="equipment",
                user=self.current_user,
                object_type="equipment",
                object_id=equipment.id,
                object_repr=f"{equipment.reference} - {equipment.name}",
                old_values=old_values,
                new_values={"is_active": False},
                status="success",
            )

        return await self.get_equipment(equipment.id)

    async def delete_equipment(self, equipment_id: int) -> bool:
        equipment = await self.get_equipment(equipment_id)
        if not equipment:
            return False

        try:
            await self.db.delete(equipment)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return False

        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="equipment",
                user=self.current_user,
                object_type="equipment",
                object_id=equipment_id,
                object_repr=f"{equipment.reference} - {equipment.name}",
                status="success",
            )

        return True
