from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_active_user
from app.models.volunteer import Volunteer
from app.schemas.volunteer import VolunteerCreate, VolunteerUpdate, VolunteerResponse
from app.services.volunteer import VolunteerService

router = APIRouter(prefix="/volunteers", tags=["volunteers"])

volunteer_service = VolunteerService()


@router.get("/", response_model=list[VolunteerResponse])
async def list_volunteers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List all volunteers."""
    volunteers = await volunteer_service.list_volunteers(db, skip, limit)
    return [VolunteerResponse.model_validate(v) for v in volunteers]


@router.post("/", response_model=VolunteerResponse, status_code=status.HTTP_201_CREATED)
async def create_volunteer(
    volunteer_in: VolunteerCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new volunteer."""
    volunteer = await volunteer_service.create_volunteer(db, volunteer_in)
    return VolunteerResponse.model_validate(volunteer)


@router.get("/{volunteer_id}", response_model=VolunteerResponse)
async def get_volunteer(
    volunteer_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific volunteer by ID."""
    volunteer = await volunteer_service.get_volunteer(db, volunteer_id)
    if not volunteer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Volontaire non trouvé",
        )
    return VolunteerResponse.model_validate(volunteer)


@router.put("/{volunteer_id}", response_model=VolunteerResponse)
async def update_volunteer(
    volunteer_id: int,
    volunteer_in: VolunteerUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a volunteer."""
    volunteer = await volunteer_service.update_volunteer(db, volunteer_id, volunteer_in)
    if not volunteer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Volontaire non trouvé",
        )
    return VolunteerResponse.model_validate(volunteer)


@router.delete("/{volunteer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_volunteer(
    volunteer_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a volunteer."""
    success = await volunteer_service.delete_volunteer(db, volunteer_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Volontaire non trouvé",
        )
    return None
