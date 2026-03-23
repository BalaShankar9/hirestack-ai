"""
Organization Service
Handles org CRUD, member management, invitations, and audit logging.
"""
import secrets
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()


class OrgService:
    """Service for organization operations."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    # ── Org CRUD ──────────────────────────────────────────────────

    async def create_org(self, user_id: str, name: str, slug: str) -> Dict[str, Any]:
        """Create a new organization and add creator as owner."""
        org_data = {
            "name": name,
            "slug": slug.lower().strip(),
            "tier": "free",
            "created_by": user_id,
        }
        org_id = await self.db.create(TABLES["organizations"], org_data)

        # Add creator as owner
        await self.db.create(TABLES["org_members"], {
            "org_id": org_id,
            "user_id": user_id,
            "role": "owner",
            "status": "active",
        })

        # Create default free subscription
        await self.db.create(TABLES["subscriptions"], {
            "org_id": org_id,
            "plan": "free",
            "status": "active",
            "usage_limits": {"applications": 5, "ats_scans": 10, "ai_calls": 50, "members": 2, "candidates": 10},
        })

        await self._audit(org_id, user_id, "org.created", "organization", org_id)
        return await self.db.get(TABLES["organizations"], org_id)

    async def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.get(TABLES["organizations"], org_id)

    async def get_user_orgs(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all orgs a user belongs to."""
        memberships = await self.db.query(TABLES["org_members"], filters=[("user_id", "==", user_id)])
        orgs = []
        for m in memberships:
            org = await self.db.get(TABLES["organizations"], m["org_id"])
            if org:
                org["member_role"] = m["role"]
                orgs.append(org)
        return orgs

    async def update_org(self, org_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        safe = {k: v for k, v in data.items() if k in ("name", "logo_url", "billing_email", "settings")}
        await self.db.update(TABLES["organizations"], org_id, safe)
        return await self.db.get(TABLES["organizations"], org_id)

    async def delete_org(self, org_id: str) -> bool:
        return await self.db.delete(TABLES["organizations"], org_id)

    # ── Members ───────────────────────────────────────────────────

    async def get_members(self, org_id: str) -> List[Dict[str, Any]]:
        members = await self.db.query(TABLES["org_members"], filters=[("org_id", "==", org_id)])
        for m in members:
            user = await self.db.get(TABLES["users"], m["user_id"])
            if user:
                m["user_name"] = user.get("full_name") or user.get("email", "")
                m["user_email"] = user.get("email", "")
                m["user_avatar"] = user.get("avatar_url")
        return members

    async def get_membership(self, org_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        members = await self.db.query(TABLES["org_members"], filters=[("org_id", "==", org_id), ("user_id", "==", user_id)], limit=1)
        return members[0] if members else None

    async def change_role(self, org_id: str, target_user_id: str, new_role: str, actor_id: str) -> bool:
        member = await self.get_membership(org_id, target_user_id)
        if not member:
            return False
        await self.db.update(TABLES["org_members"], member["id"], {"role": new_role})
        await self._audit(org_id, actor_id, "member.role_changed", "org_member", member["id"], {"new_role": new_role})
        return True

    async def remove_member(self, org_id: str, target_user_id: str, actor_id: str) -> bool:
        member = await self.get_membership(org_id, target_user_id)
        if not member or member["role"] == "owner":
            return False
        await self.db.delete(TABLES["org_members"], member["id"])
        await self._audit(org_id, actor_id, "member.removed", "org_member", member["id"])
        return True

    # ── Invitations ───────────────────────────────────────────────

    async def invite_member(self, org_id: str, email: str, role: str, invited_by: str) -> Dict[str, Any]:
        token = secrets.token_urlsafe(32)
        inv_id = await self.db.create(TABLES["org_invitations"], {
            "org_id": org_id,
            "email": email,
            "role": role,
            "invited_by": invited_by,
            "token": token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        })
        await self._audit(org_id, invited_by, "member.invited", "invitation", inv_id, {"email": email, "role": role})
        return {"id": inv_id, "token": token, "email": email, "role": role}

    async def accept_invitation(self, token: str, user_id: str) -> Optional[Dict[str, Any]]:
        invitations = await self.db.query(TABLES["org_invitations"], filters=[("token", "==", token)], limit=1)
        if not invitations:
            return None
        inv = invitations[0]
        if inv.get("accepted_at"):
            return None

        # Add member
        await self.db.create(TABLES["org_members"], {
            "org_id": inv["org_id"],
            "user_id": user_id,
            "role": inv.get("role", "member"),
            "invited_by": inv.get("invited_by"),
            "status": "active",
        })

        # Mark accepted
        await self.db.update(TABLES["org_invitations"], inv["id"], {"accepted_at": datetime.now(timezone.utc).isoformat()})
        await self._audit(inv["org_id"], user_id, "member.joined", "invitation", inv["id"])
        return await self.db.get(TABLES["organizations"], inv["org_id"])

    # ── Audit ─────────────────────────────────────────────────────

    async def _audit(self, org_id: str, user_id: str, action: str, resource_type: str = "", resource_id: str = "", changes: Dict = None):
        try:
            await self.db.create(TABLES["audit_logs"], {
                "org_id": org_id,
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "changes": changes or {},
            })
        except Exception:
            pass  # Audit logging should never break main flow

    async def get_audit_logs(self, org_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(TABLES["audit_logs"], filters=[("org_id", "==", org_id)], order_by="created_at", order_direction="DESCENDING", limit=limit)

    # ── Usage ─────────────────────────────────────────────────────

    async def record_usage(self, org_id: str, user_id: str, feature: str, quantity: int = 1):
        await self.db.create(TABLES["usage_records"], {
            "org_id": org_id,
            "user_id": user_id,
            "feature": feature,
            "quantity": quantity,
            "period_start": datetime.now(timezone.utc).strftime("%Y-%m-01"),
        })

    async def get_usage(self, org_id: str) -> Dict[str, int]:
        """Get current month's usage by feature."""
        period = datetime.now(timezone.utc).strftime("%Y-%m-01")
        records = await self.db.query(TABLES["usage_records"], filters=[("org_id", "==", org_id), ("period_start", "==", period)])
        usage: Dict[str, int] = {}
        for r in records:
            f = r.get("feature", "unknown")
            usage[f] = usage.get(f, 0) + r.get("quantity", 1)
        return usage

    async def check_limit(self, org_id: str, feature: str) -> bool:
        """Check if org can use a feature (within limits)."""
        subs = await self.db.query(TABLES["subscriptions"], filters=[("org_id", "==", org_id), ("status", "==", "active")], limit=1)
        if not subs:
            return True  # No subscription = no limits (backward compat)
        limits = subs[0].get("usage_limits", {})
        limit = limits.get(feature, -1)
        if limit == -1:
            return True  # Unlimited
        usage = await self.get_usage(org_id)
        return usage.get(feature, 0) < limit
