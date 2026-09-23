from typing import Optional, List
import json

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.administrative import AdministrativeAssignment
from app.models.housing import Cleaning
from app.models.volunteer import Volunteer
from app.schemas.volunteer import VolunteerCreate, VolunteerUpdate


class VolunteerService:
    """Service layer for volunteer operations."""
    
    async def list_volunteers(self, db: AsyncSession, skip: int = 0, limit: int = 100, usage_type: str | None = None, is_active: bool | None = None) -> List[Volunteer]:
        filters = []
        if usage_type:
            filters.append(Volunteer.usage_type.like(f"%{usage_type}%"))
        if is_active is not None:
            filters.append(Volunteer.is_active == is_active)
        result = await db.execute(
            select(Volunteer).where(*filters).offset(skip).limit(limit).order_by(Volunteer.last_name)
        )
        return result.scalars().all()
    
    async def get_volunteer(self, db: AsyncSession, volunteer_id: int) -> Volunteer | None:
        result = await db.execute(select(Volunteer).where(Volunteer.id == volunteer_id))
        return result.scalar_one_or_none()
    
    async def create_volunteer(self, db: AsyncSession, volunteer_in: VolunteerCreate) -> Volunteer:
        result = await db.execute(select(Volunteer).where(
            Volunteer.first_name == volunteer_in.first_name,
            Volunteer.last_name == volunteer_in.last_name,
        ))
        if result.scalar_one_or_none():
            raise ValueError("Un volontaire avec ce nom et ce prénom existe déjà")
        
        volunteer = Volunteer(
            first_name=volunteer_in.first_name,
            last_name=volunteer_in.last_name,
            email=volunteer_in.email,
            phone=volunteer_in.phone,
            usage_type=volunteer_in.usage_type,
            communication_preference=volunteer_in.communication_preference,
            is_active=volunteer_in.is_active,
        )
        db.add(volunteer)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValueError("Un volontaire avec ce nom et ce prénom existe déjà") from exc
        await db.refresh(volunteer)
        return volunteer
    
    async def update_volunteer(self, db: AsyncSession, volunteer_id: int, volunteer_in: VolunteerUpdate) -> Volunteer | None:
        volunteer = await self.get_volunteer(db, volunteer_id)
        if not volunteer:
            return None

        update_data = volunteer_in.model_dump(exclude_unset=True)
        if "first_name" in update_data or "last_name" in update_data:
            first_name = update_data.get("first_name", volunteer.first_name)
            last_name = update_data.get("last_name", volunteer.last_name)
            result = await db.execute(
                select(Volunteer.id).where(
                    Volunteer.first_name == first_name,
                    Volunteer.last_name == last_name,
                    Volunteer.id != volunteer_id,
                ).limit(1)
            )
            if result.scalar_one_or_none() is not None:
                raise ValueError("Un volontaire avec ce nom et ce prénom existe déjà")

        for field, value in update_data.items():
            setattr(volunteer, field, value)

        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValueError("Un volontaire avec ce nom et ce prénom existe déjà") from exc
        await db.refresh(volunteer)
        return volunteer
    
    async def delete_volunteer(self, db: AsyncSession, volunteer_id: int) -> bool:
        volunteer = await self.get_volunteer(db, volunteer_id)
        if not volunteer:
            return False

        # Les affectations administratives sont historiques et ne sont pas en cascade.
        await db.execute(
            delete(AdministrativeAssignment).where(
                AdministrativeAssignment.volunteer_id == volunteer_id
            )
        )

        # Les volontaires retenus sont aussi stockés dans ce JSON sans clé étrangère.
        cleanings_result = await db.execute(
            select(Cleaning).where(Cleaning.selected_volunteer_ids_json.is_not(None))
        )
        for cleaning in cleanings_result.scalars():
            selected_ids = json.loads(cleaning.selected_volunteer_ids_json or "[]")
            filtered_ids = [
                selected_id for selected_id in selected_ids
                if str(selected_id) != str(volunteer_id)
            ]
            if filtered_ids != selected_ids:
                cleaning.selected_volunteer_ids_json = json.dumps(filtered_ids)

        await db.delete(volunteer)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValueError(
                "Ce volontaire possède encore une utilisation liée et ne peut pas être supprimé"
            ) from exc
        return True
    
    async def toggle_volunteer_status(self, db: AsyncSession, volunteer_id: int) -> Volunteer | None:
        volunteer = await self.get_volunteer(db, volunteer_id)
        if not volunteer:
            return None
        volunteer.is_active = not volunteer.is_active
        await db.commit()
        await db.refresh(volunteer)
        return volunteer


volunteer_service = VolunteerService()
