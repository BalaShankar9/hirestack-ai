"""
Organization routes — CRUD, members, invitations, audit, usage
"""
import re
from typing import Dict, Any

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from app.services.org import OrgService
from app.api.deps import get_current_user, validate_uuid
from app.core.database import TABLES
import structlog

logger = structlog.get_logger()

router = APIRouter()


class CreateOrgRequest(BaseModel):
    name: str
    slug: str = ""


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "member"


class ChangeRoleRequest(BaseModel):
    role: str


# ── Org CRUD ──────────────────────────────────────────────────────

@limiter.limit("30/minute")
@router.post("")
async def create_org(
    request: Request,
    req: CreateOrgRequest, current_user: Dict[str, Any] = Depends(get_current_user
)):
    """Create a new organization."""
    slug = req.slug or re.sub(r"[^a-z0-9-]", "", req.name.lower().replace(" ", "-"))[:50]
    service = OrgService()
    try:
        org = await service.create_org(current_user["id"], req.name, slug)
        return org
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization slug already taken")
        logger.error("create_org_failed", error=str(e), user_id=current_user["id"])
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create organization")


@limiter.limit("30/minute")
@router.get("")
async def list_orgs(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all organizations the user belongs to."""
    service = OrgService()
    return await service.get_user_orgs(current_user["id"])


@limiter.limit("30/minute")
@router.get("/{org_id}")
async def get_org(
    request: Request,
    org_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get org details (must be a member)."""
    validate_uuid(org_id, "org_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")
    org = await service.get_org(org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    org["member_role"] = membership["role"]
    return org


@limiter.limit("30/minute")
@router.put("/{org_id}")
async def update_org(
    request: Request,
    org_id: str, data: Dict[str, Any], current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update org settings (admin+ only)."""
    validate_uuid(org_id, "org_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return await service.update_org(org_id, data)


@limiter.limit("30/minute")
@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(
    request: Request,
    org_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Delete org (owner only)."""
    validate_uuid(org_id, "org_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership or membership["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    await service.delete_org(org_id)


# ── Members ───────────────────────────────────────────────────────

@limiter.limit("30/minute")
@router.get("/{org_id}/members")
async def list_members(
    request: Request,
    org_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    validate_uuid(org_id, "org_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")
    return await service.get_members(org_id)


@limiter.limit("30/minute")
@router.post("/{org_id}/members")
async def invite_member(
    request: Request,
    org_id: str, req: InviteMemberRequest, current_user: Dict[str, Any] = Depends(get_current_user
)):
    """Invite a new member to the org."""
    validate_uuid(org_id, "org_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    invitation = await service.invite_member(org_id, req.email, req.role, current_user["id"])
    return invitation


@limiter.limit("30/minute")
@router.put("/{org_id}/members/{user_id}")
async def change_member_role(
    request: Request,
    org_id: str, user_id: str, req: ChangeRoleRequest, current_user: Dict[str, Any] = Depends(get_current_user
)):
    validate_uuid(org_id, "org_id")
    validate_uuid(user_id, "user_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    if req.role not in ("admin", "recruiter", "member", "viewer"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    success = await service.change_role(org_id, user_id, req.role, current_user["id"])
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return {"status": "updated"}


@limiter.limit("30/minute")
@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    request: Request,
    org_id: str, user_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    validate_uuid(org_id, "org_id")
    validate_uuid(user_id, "user_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    success = await service.remove_member(org_id, user_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found or is owner")


# ── Invitations ───────────────────────────────────────────────────

@limiter.limit("30/minute")
@router.post("/invitations/accept")
async def accept_invitation(
    request: Request,
    token: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Accept an org invitation."""
    service = OrgService()
    org = await service.accept_invitation(token, current_user["id"])
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired invitation")
    return org


# ── Audit & Usage ─────────────────────────────────────────────────

@limiter.limit("30/minute")
@router.get("/{org_id}/audit")
async def get_audit_logs(
    request: Request,
    org_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    validate_uuid(org_id, "org_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return await service.get_audit_logs(org_id)


@limiter.limit("30/minute")
@router.get("/{org_id}/usage")
async def get_usage(
    request: Request,
    org_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    validate_uuid(org_id, "org_id")
    service = OrgService()
    membership = await service.get_membership(org_id, current_user["id"])
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    usage = await service.get_usage(org_id)
    # Get limits
    subs = await service.db.query(TABLES["subscriptions"], filters=[("org_id", "==", org_id)], limit=1)
    limits = subs[0].get("usage_limits", {}) if subs else {}
    return {"usage": usage, "limits": limits, "plan": subs[0].get("plan", "free") if subs else "free"}


