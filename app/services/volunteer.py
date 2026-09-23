from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        # Check if email already exists
        result = await db.execute(select(Volunteer).where(Volunteer.email == volunteer_in.email))
        if result.scalar_one_or_none():
            raise ValueError("Un volontaire avec cet email existe déjà")
        
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
        await db.commit()
        await db.refresh(volunteer)
        return volunteer
    
    async def update_volunteer(self, db: AsyncSession, volunteer_id: int, volunteer_in: VolunteerUpdate) -> Volunteer | None:
        volunteer = await self.get_volunteer(db, volunteer_id)
        if not volunteer:
            return None
        
        update_data = volunteer_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(volunteer, field, value)
        
        await db.commit()
        await db.refresh(volunteer)
        return volunteer
    
    async def delete_volunteer(self, db: AsyncSession, volunteer_id: int) -> bool:
        volunteer = await self.get_volunteer(db, volunteer_id)
        if not volunteer:
            return False
        
        await db.delete(volunteer)
        await db.commit()
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
