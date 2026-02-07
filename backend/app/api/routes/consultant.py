"""
Career Consultant routes - Roadmaps and recommendations (Firestore)
"""
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.roadmap import RoadmapService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/roadmap")
async def generate_roadmap(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a career improvement roadmap."""
    service = RoadmapService()
    try:
        return await service.generate_roadmap(
            user_id=current_user["id"],
            gap_report_id=request.get("gap_report_id"),
            title=request.get("title"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/roadmaps")
async def list_roadmaps(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's roadmaps."""
    service = RoadmapService()
    return await service.get_user_roadmaps(current_user["id"])


@router.get("/roadmap/{roadmap_id}")
async def get_roadmap(
    roadmap_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific roadmap."""
    service = RoadmapService()
    roadmap = await service.get_roadmap(roadmap_id, current_user["id"])
    if not roadmap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")
    return roadmap


@router.put("/roadmap/{roadmap_id}/progress")
async def update_progress(
    roadmap_id: str,
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update milestone progress in a roadmap."""
    service = RoadmapService()
    updated = await service.update_milestone_progress(
        roadmap_id, current_user["id"], request.get("milestone_id", ""), request.get("status", "")
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap or milestone not found")
    return {"message": "Progress updated"}


@router.delete("/roadmap/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_roadmap(
    roadmap_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a roadmap."""
    service = RoadmapService()
    deleted = await service.delete_roadmap(roadmap_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")
