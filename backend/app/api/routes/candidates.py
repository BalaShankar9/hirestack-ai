"""
Candidate routes — CRUD, pipeline stage management
"""
from typing import Dict, Any, Optional

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel

from app.services.candidate import CandidateService
from app.services.org import OrgService
from app.api.deps import get_current_user
import structlog

logger = structlog.get_logger()
router = APIRouter()


class CreateCandidateRequest(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    client_company: Optional[str] = None
    pipeline_stage: str = "sourced"
    tags: list = []
    notes: Optional[str] = None
    resume_text: Optional[str] = None


class MoveStageRequest(BaseModel):
    stage: str


async def _get_user_org(current_user: Dict[str, Any]) -> Dict[str, Any]:
    """Get the user's first org or raise 404."""
    org_service = OrgService()
    orgs = await org_service.get_user_orgs(current_user["id"])
    if not orgs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Create an organization first")
    return orgs[0]


@limiter.limit("30/minute")
@router.get("")
async def list_candidates(
    request: Request,
    stage: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    org = await _get_user_org(current_user)
    service = CandidateService()
    return await service.list(org["id"], stage=stage)


@limiter.limit("30/minute")
@router.post("")
async def create_candidate(
    request: Request,
    req: CreateCandidateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user
),
):
    org = await _get_user_org(current_user)
    service = CandidateService()
    return await service.create(org["id"], req.model_dump(), current_user["id"])


@limiter.limit("30/minute")
@router.get("/stats")
async def pipeline_stats(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    org = await _get_user_org(current_user)
    service = CandidateService()
    return await service.get_pipeline_stats(org["id"])


@limiter.limit("30/minute")
@router.get("/{candidate_id}")
async def get_candidate(
    request: Request,
    candidate_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    org = await _get_user_org(current_user)
    service = CandidateService()
    c = await service.get(candidate_id, org["id"])
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return c


@limiter.limit("30/minute")
@router.put("/{candidate_id}")
async def update_candidate(
    request: Request,
    candidate_id: str, data: Dict[str, Any], current_user: Dict[str, Any] = Depends(get_current_user)):
    org = await _get_user_org(current_user)
    service = CandidateService()
    updated = await service.update(candidate_id, org["id"], data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return updated


@limiter.limit("30/minute")
@router.post("/{candidate_id}/move")
async def move_candidate(
    request: Request,
    candidate_id: str, req: MoveStageRequest, current_user: Dict[str, Any] = Depends(get_current_user
)):
    org = await _get_user_org(current_user)
    service = CandidateService()
    try:
        updated = await service.move_stage(candidate_id, org["id"], req.stage)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@limiter.limit("30/minute")
@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    request: Request,
    candidate_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    org = await _get_user_org(current_user)
    service = CandidateService()
    if not await service.delete(candidate_id, org["id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
