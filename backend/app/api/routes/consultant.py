"""
Career Consultant routes - Roadmaps and recommendations
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.schemas.roadmap import RoadmapCreate, RoadmapResponse
from app.services.roadmap import RoadmapService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/roadmap", response_model=RoadmapResponse)
async def generate_roadmap(
    request: RoadmapCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate a career improvement roadmap."""
    roadmap_service = RoadmapService(db)

    try:
        roadmap = await roadmap_service.generate_roadmap(
            user_id=current_user.id,
            gap_report_id=request.gap_report_id,
            title=request.title
        )
        return roadmap
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/roadmaps", response_model=List[RoadmapResponse])
async def list_roadmaps(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all user's roadmaps."""
    roadmap_service = RoadmapService(db)
    roadmaps = await roadmap_service.get_user_roadmaps(current_user.id)
    return roadmaps


@router.get("/roadmap/{roadmap_id}", response_model=RoadmapResponse)
async def get_roadmap(
    roadmap_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific roadmap."""
    roadmap_service = RoadmapService(db)
    roadmap = await roadmap_service.get_roadmap(roadmap_id, current_user.id)

    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roadmap not found"
        )
    return roadmap


@router.put("/roadmap/{roadmap_id}/progress")
async def update_progress(
    roadmap_id: UUID,
    milestone_id: str,
    status: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update milestone progress in a roadmap."""
    roadmap_service = RoadmapService(db)
    updated = await roadmap_service.update_milestone_progress(
        roadmap_id, current_user.id, milestone_id, status
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roadmap or milestone not found"
        )
    return {"message": "Progress updated"}


@router.delete("/roadmap/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_roadmap(
    roadmap_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a roadmap."""
    roadmap_service = RoadmapService(db)
    deleted = await roadmap_service.delete_roadmap(roadmap_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roadmap not found"
        )
