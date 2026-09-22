import re
from datetime import UTC, datetime
from typing import Optional, List

from sqlalchemy import select, func, or_, and_, text, Integer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.buildings import (
    Building,
    Room,
    RoomType,
    Site,
    UsageType,
)
from app.models.user import User
from app.services.audit import AuditService


def slugify(text: str, max_length: int = 50) -> str:
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[\s_-]+', '_', text)
    text = text.strip('_')
    return text[:max_length]


class BuildingService:
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
    # CODE GENERATION
    # ============================================================

    async def _generate_site_code(self) -> str:
        result = await self.db.execute(select(func.count()).select_from(Site))
        count = (result.scalar() or 0) + 1
        ref = f"SITE-{count:04d}"
        while (await self.db.execute(select(Site.id).where(Site.reference == ref))).scalar_one_or_none():
            count += 1
            ref = f"SITE-{count:04d}"
        return ref

    async def _generate_building_code(self, site_id: int) -> str:
        result = await self.db.execute(
            select(func.count()).select_from(Building).where(Building.site_id == site_id)
        )
        count = (result.scalar() or 0) + 1
        ref = f"BAT-{count:04d}"
        while (await self.db.execute(
            select(Building.id).where(Building.site_id == site_id, Building.reference == ref)
        )).scalar_one_or_none():
            count += 1
            ref = f"BAT-{count:04d}"
        return ref

    async def _generate_room_code(self, building_id: int) -> str:
        result = await self.db.execute(
            select(func.count()).select_from(Room).where(Room.building_id == building_id)
        )
        count = (result.scalar() or 0) + 1
        ref = f"LOC-{count:04d}"
        while (await self.db.execute(
            select(Room.id).where(Room.building_id == building_id, Room.reference == ref)
        )).scalar_one_or_none():
            count += 1
            ref = f"LOC-{count:04d}"
        return ref

    async def _generate_referential_code(self, name: str, table_class) -> str:
        base_code = slugify(name, max_length=30).upper()
        if not base_code:
            base_code = "REF"
        code = base_code
        count = 1
        while (await self.db.execute(
            select(table_class.id).where(table_class.code == code)
        )).scalar_one_or_none():
            count += 1
            code = f"{base_code}-{count}"
        return code

    # ============================================================
    # USAGE TYPES
    # ============================================================

    async def search_usage_types(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "sort_order",
        sort_order: str = "asc",
    ) -> tuple[List[UsageType], int]:
        query = select(UsageType)
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    UsageType.code.ilike(search_term),
                    UsageType.name.ilike(search_term),
                )
            )

        if is_active is not None:
            conditions.append(UsageType.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "code": UsageType.code,
            "name": UsageType.name,
            "sort_order": UsageType.sort_order,
            "is_active": UsageType.is_active,
            "created_at": UsageType.created_at,
        }
        sort_column = allowed_sort_fields.get(sort_by, UsageType.sort_order)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        count_query = select(func.count()).select_from(UsageType)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_usage_type(self, usage_type_id: int) -> Optional[UsageType]:
        result = await self.db.execute(
            select(UsageType).where(UsageType.id == usage_type_id)
        )
        return result.scalar_one_or_none()

    async def create_usage_type(self, data: dict) -> Optional[UsageType]:
        data["code"] = await self._generate_referential_code(data["name"], UsageType)
        usage_type = UsageType(**data)
        self.db.add(usage_type)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return None
        await self.db.refresh(usage_type)

        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="buildings",
                user=self.current_user,
                object_type="usage_type",
                object_id=str(usage_type.id),
                object_repr=usage_type.name,
                new_values={"code": usage_type.code, "name": usage_type.name},
                status="success",
            )

        return usage_type

    async def update_usage_type(self, usage_type_id: int, data: dict) -> Optional[UsageType]:
        usage_type = await self.get_usage_type(usage_type_id)
        if not usage_type:
            return None

        # Code cannot be modified after creation
        if "code" in data and data["code"] is not None:
            data.pop("code")

        old_values = {"name": usage_type.name, "is_active": usage_type.is_active}

        for key, value in data.items():
            if value is not None and hasattr(usage_type, key) and key != "code":
                setattr(usage_type, key, value)

        await self.db.commit()
        await self.db.refresh(usage_type)

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="buildings",
                user=self.current_user,
                object_type="usage_type",
                object_id=str(usage_type.id),
                object_repr=usage_type.name,
                old_values=old_values,
                new_values={"name": usage_type.name, "is_active": usage_type.is_active},
                status="success",
            )

        return usage_type

    # ============================================================
    # ROOM TYPES
    # ============================================================

    async def search_room_types(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "sort_order",
        sort_order: str = "asc",
    ) -> tuple[List[RoomType], int]:
        query = select(RoomType)
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    RoomType.code.ilike(search_term),
                    RoomType.name.ilike(search_term),
                )
            )

        if is_active is not None:
            conditions.append(RoomType.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "code": RoomType.code,
            "name": RoomType.name,
            "sort_order": RoomType.sort_order,
            "is_active": RoomType.is_active,
            "created_at": RoomType.created_at,
        }
        sort_column = allowed_sort_fields.get(sort_by, RoomType.sort_order)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        count_query = select(func.count()).select_from(RoomType)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_room_type(self, room_type_id: int) -> Optional[RoomType]:
        result = await self.db.execute(
            select(RoomType).where(RoomType.id == room_type_id)
        )
        return result.scalar_one_or_none()

    async def create_room_type(self, data: dict) -> Optional[RoomType]:
        data["code"] = await self._generate_referential_code(data["name"], RoomType)
        room_type = RoomType(**data)
        self.db.add(room_type)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return None
        await self.db.refresh(room_type)

        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="buildings",
                user=self.current_user,
                object_type="room_type",
                object_id=str(room_type.id),
                object_repr=room_type.name,
                new_values={"code": room_type.code, "name": room_type.name},
                status="success",
            )

        return room_type

    async def update_room_type(self, room_type_id: int, data: dict) -> Optional[RoomType]:
        room_type = await self.get_room_type(room_type_id)
        if not room_type:
            return None

        old_values = {"name": room_type.name, "is_active": room_type.is_active}

        for key, value in data.items():
            if value is not None and hasattr(room_type, key):
                setattr(room_type, key, value)

        await self.db.commit()
        await self.db.refresh(room_type)

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="buildings",
                user=self.current_user,
                object_type="room_type",
                object_id=str(room_type.id),
                object_repr=room_type.name,
                old_values=old_values,
                new_values={"name": room_type.name, "is_active": room_type.is_active},
                status="success",
            )

        return room_type

    async def delete_room_type(self, room_type_id: int) -> Optional[str]:
        room_type = await self.get_room_type(room_type_id)
        if not room_type:
            return "Type de pièce non trouvé"

        room_count = await self._count_rooms_for_room_type(room_type_id)
        if room_count > 0:
            return (
                f"Impossible de supprimer le type de pièce « {room_type.name} » : "
                f"il est utilisé par {room_count} local(aux)."
            )

        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="buildings",
                user=self.current_user,
                object_type="room_type",
                object_id=str(room_type.id),
                object_repr=room_type.name,
                new_values={"code": room_type.code, "name": room_type.name},
                status="success",
            )

        await self.db.delete(room_type)
        await self.db.commit()
        return None

    # ============================================================
    # SITES
    # ============================================================

    async def search_sites(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Site], int]:
        query = select(Site).options(selectinload(Site.buildings))
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    Site.reference.ilike(search_term),
                    Site.name.ilike(search_term),
                    Site.city.ilike(search_term),
                )
            )

        if is_active is not None:
            conditions.append(Site.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "reference": Site.reference,
            "name": Site.name,
            "city": Site.city,
            "is_active": Site.is_active,
            "created_at": Site.created_at,
            "updated_at": Site.updated_at,
        }
        sort_column = allowed_sort_fields.get(sort_by, Site.created_at)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        count_query = select(func.count()).select_from(Site)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().unique().all())

        return items, total

    async def get_site(self, site_id: int) -> Optional[Site]:
        result = await self.db.execute(
            select(Site)
            .options(selectinload(Site.buildings))
            .where(Site.id == site_id)
        )
        return result.scalar_one_or_none()

    async def create_site(self, data: dict) -> Optional[Site]:
        data["reference"] = await self._generate_site_code()
        site = Site(**data)
        self.db.add(site)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return None
        await self.db.refresh(site)

        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="buildings",
                user=self.current_user,
                object_type="site",
                object_id=str(site.id),
                object_repr=site.name,
                new_values={"reference": site.reference, "name": site.name},
                status="success",
            )

        return site

    async def update_site(self, site_id: int, data: dict) -> Optional[Site]:
        site = await self.get_site(site_id)
        if not site:
            return None

        old_values = {"name": site.name, "is_active": site.is_active}

        for key, value in data.items():
            if value is not None and hasattr(site, key):
                setattr(site, key, value)

        await self.db.commit()
        await self.db.refresh(site)

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="buildings",
                user=self.current_user,
                object_type="site",
                object_id=str(site.id),
                object_repr=site.name,
                old_values=old_values,
                new_values={"name": site.name, "is_active": site.is_active},
                status="success",
            )

        return site

    # ============================================================
    # BUILDINGS
    # ============================================================

    async def search_buildings(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        site_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Building], int]:
        query = select(Building).options(
            selectinload(Building.site),
            selectinload(Building.rooms),
        )
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    Building.reference.ilike(search_term),
                    Building.name.ilike(search_term),
                )
            )

        if site_id is not None:
            conditions.append(Building.site_id == site_id)

        if is_active is not None:
            conditions.append(Building.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "reference": Building.reference,
            "name": Building.name,
            "is_active": Building.is_active,
            "created_at": Building.created_at,
            "updated_at": Building.updated_at,
        }
        sort_column = allowed_sort_fields.get(sort_by, Building.created_at)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        count_query = select(func.count()).select_from(Building)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().unique().all())

        return items, total

    async def get_building(self, building_id: int) -> Optional[Building]:
        result = await self.db.execute(
            select(Building)
            .options(
                selectinload(Building.site),
                selectinload(Building.rooms).selectinload(Room.room_type),
                selectinload(Building.rooms).selectinload(Room.usage_type),
            )
            .where(Building.id == building_id)
        )
        return result.scalar_one_or_none()

    async def create_building(self, data: dict) -> Optional[Building]:
        data["reference"] = await self._generate_building_code(data["site_id"])
        building = Building(**data)
        self.db.add(building)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return None
        await self.db.refresh(building)

        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="buildings",
                user=self.current_user,
                object_type="building",
                object_id=str(building.id),
                object_repr=building.name,
                new_values={"reference": building.reference, "name": building.name, "site_id": building.site_id},
                status="success",
            )

        return building

    async def update_building(self, building_id: int, data: dict) -> Optional[Building]:
        building = await self.get_building(building_id)
        if not building:
            return None

        old_values = {"name": building.name, "is_active": building.is_active}

        for key, value in data.items():
            if value is not None and hasattr(building, key):
                setattr(building, key, value)

        await self.db.commit()
        await self.db.refresh(building)

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="buildings",
                user=self.current_user,
                object_type="building",
                object_id=str(building.id),
                object_repr=building.name,
                old_values=old_values,
                new_values={"name": building.name, "is_active": building.is_active},
                status="success",
            )

        return building

    # ============================================================
    # ROOMS
    # ============================================================

    async def search_rooms(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        building_id: Optional[int] = None,
        room_type_id: Optional[int] = None,
        usage_type_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        used_for_accommodation: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Room], int]:
        query = select(Room).options(
            selectinload(Room.building),
            selectinload(Room.room_type),
            selectinload(Room.usage_type),
        )
        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    Room.reference.ilike(search_term),
                    Room.name.ilike(search_term),
                )
            )

        if building_id is not None:
            conditions.append(Room.building_id == building_id)

        if room_type_id is not None:
            conditions.append(Room.room_type_id == room_type_id)

        if usage_type_id is not None:
            conditions.append(Room.usage_type_id == usage_type_id)

        if is_active is not None:
            conditions.append(Room.is_active == is_active)

        if used_for_accommodation is not None:
            conditions.append(Room.used_for_accommodation == used_for_accommodation)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "reference": Room.reference,
            "name": Room.name,
            "area": Room.area,
            "is_active": Room.is_active,
            "created_at": Room.created_at,
            "updated_at": Room.updated_at,
        }
        sort_column = allowed_sort_fields.get(sort_by, Room.created_at)

        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        count_query = select(func.count()).select_from(Room)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().unique().all())

        return items, total

    async def get_room(self, room_id: int) -> Optional[Room]:
        result = await self.db.execute(
            select(Room)
            .options(
                selectinload(Room.building),
                selectinload(Room.room_type),
                selectinload(Room.usage_type),
            )
            .where(Room.id == room_id)
        )
        return result.scalar_one_or_none()

    async def create_room(self, data: dict) -> Optional[Room]:
        data["reference"] = await self._generate_room_code(data["building_id"])
        room = Room(**data)
        self.db.add(room)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return None

        if data.get("used_for_accommodation"):
            await self._auto_create_housing(room.id)

        await self.db.commit()

        if self.audit and self.current_user:
            await self.audit.log(
                action="create",
                module="buildings",
                user=self.current_user,
                object_type="room",
                object_id=str(room.id),
                object_repr=room.name,
                new_values={"name": room.name, "building_id": room.building_id, "reference": room.reference},
                status="success",
            )

        return await self.get_room(room.id)

    async def update_room(self, room_id: int, data: dict) -> Optional[Room]:
        room = await self.get_room(room_id)
        if not room:
            return None

        old_values = {"name": room.name, "is_active": room.is_active, "used_for_accommodation": room.used_for_accommodation}

        was_accommodation = room.used_for_accommodation

        for key, value in data.items():
            if value is not None and hasattr(room, key):
                setattr(room, key, value)

        if not was_accommodation and room.used_for_accommodation:
            await self._auto_create_housing(room.id)

        await self.db.commit()

        if self.audit and self.current_user:
            await self.audit.log(
                action="update",
                module="buildings",
                user=self.current_user,
                object_type="room",
                object_id=str(room.id),
                object_repr=room.name,
                old_values=old_values,
                new_values={"name": room.name, "is_active": room.is_active, "used_for_accommodation": room.used_for_accommodation},
                status="success",
            )

        return await self.get_room(room.id)

    # ============================================================
    # AUTO HOUSING
    # ============================================================

    async def _auto_create_housing(self, room_id: int):
        from app.models.housing import Housing
        result = await self.db.execute(select(Housing).where(Housing.room_id == room_id))
        if not result.scalar_one_or_none():
            housing = Housing(room_id=room_id, capacity=1)
            self.db.add(housing)

    # ============================================================
    # COUNT HELPERS
    # ============================================================

    async def _count_buildings_for_site(self, site_id: int) -> int:
        stmt = select(func.count(Building.id)).where(Building.site_id == site_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def _count_rooms_for_building(self, building_id: int) -> int:
        stmt = select(func.count(Room.id)).where(Room.building_id == building_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def _count_equipment_for_room(self, room_id: int) -> int:
        from app.models.equipment import Equipment
        stmt = select(func.count(Equipment.id)).where(Equipment.room_id == room_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    # ============================================================
    # DELETE
    # ============================================================

    async def delete_site(self, site_id: int) -> Optional[str]:
        site = await self.get_site(site_id)
        if not site:
            return "Site non trouvé"

        building_count = await self._count_buildings_for_site(site_id)
        if building_count > 0:
            return (
                f"Impossible de supprimer le site « {site.name} » : "
                f"il contient {building_count} bâtiment(s)."
            )

        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="buildings",
                user=self.current_user,
                object_type="site",
                object_id=str(site.id),
                object_repr=site.name,
                new_values={"reference": site.reference, "name": site.name},
                status="success",
            )

        await self.db.delete(site)
        await self.db.commit()
        return None

    async def delete_building(self, building_id: int) -> Optional[str]:
        building = await self.get_building(building_id)
        if not building:
            return "Bâtiment non trouvé"

        room_count = await self._count_rooms_for_building(building_id)
        if room_count > 0:
            return (
                f"Impossible de supprimer le bâtiment « {building.name} » : "
                f"il contient {room_count} local(aux)."
            )

        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="buildings",
                user=self.current_user,
                object_type="building",
                object_id=str(building.id),
                object_repr=building.name,
                new_values={"reference": building.reference, "name": building.name},
                status="success",
            )

        await self.db.delete(building)
        await self.db.commit()
        return None

    async def _count_occupancies_for_room(self, room_id: int) -> int:
        from app.models.housing import Housing, Occupancy
        stmt = (
            select(func.count(Occupancy.id))
            .join(Housing, Occupancy.housing_id == Housing.id)
            .where(Housing.room_id == room_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def delete_room(self, room_id: int) -> Optional[str]:
        room = await self.get_room(room_id)
        if not room:
            return "Local non trouvé"

        equipment_count = await self._count_equipment_for_room(room_id)
        if equipment_count > 0:
            return (
                f"Impossible de supprimer le local « {room.name} » : "
                f"il contient {equipment_count} équipement(s)."
            )

        occupancy_count = await self._count_occupancies_for_room(room_id)
        if occupancy_count > 0:
            return (
                f"Impossible de supprimer le local « {room.name} » : "
                f"il est lié à {occupancy_count} réservation(s) / occupation(s) d'hébergement."
            )

        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="buildings",
                user=self.current_user,
                object_type="room",
                object_id=str(room.id),
                object_repr=room.name,
                new_values={"reference": room.reference, "name": room.name},
                status="success",
            )

        await self.db.delete(room)
        await self.db.commit()
        return None

    async def delete_usage_type(self, usage_type_id: int) -> Optional[str]:
        usage_type = await self.get_usage_type(usage_type_id)
        if not usage_type:
            return "Type d'utilisation non trouvé"

        room_count = await self._count_rooms_for_usage_type(usage_type_id)
        if room_count > 0:
            return (
                f"Impossible de supprimer le type d'utilisation « {usage_type.name} » : "
                f"il est utilisé par {room_count} local(aux)."
            )

        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="buildings",
                user=self.current_user,
                object_type="usage_type",
                object_id=str(usage_type.id),
                object_repr=usage_type.name,
                new_values={"code": usage_type.code, "name": usage_type.name},
                status="success",
            )

        await self.db.delete(usage_type)
        await self.db.commit()
        return None

    async def _count_rooms_for_usage_type(self, usage_type_id: int) -> int:
        stmt = select(func.count(Room.id)).where(Room.usage_type_id == usage_type_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def _count_rooms_for_room_type(self, room_type_id: int) -> int:
        stmt = select(func.count(Room.id)).where(Room.room_type_id == room_type_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()
