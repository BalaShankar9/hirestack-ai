"""
Billing routes — Stripe checkout, portal, webhooks, plan info
"""
from typing import Dict, Any
from urllib.parse import urlparse

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator

import os as _os

from app.services.billing import BillingService
from app.api.deps import get_current_user
import structlog

logger = structlog.get_logger()
router = APIRouter()

# Dynamic frontend URL: prefer FRONTEND_URL env, fall back to first CORS origin
_FRONTEND_URL = _os.getenv("FRONTEND_URL", "https://hirestack.tech")

# Allowed redirect domains for checkout URLs (prevents open redirect attacks)
_ALLOWED_REDIRECT_HOSTS = {
    urlparse(_FRONTEND_URL).hostname or "hirestack.tech",
    "hirestack.tech",
    "www.hirestack.tech",
}

class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "enterprise"
    success_url: str = f"{_FRONTEND_URL}/settings/billing?success=true"
    cancel_url: str = f"{_FRONTEND_URL}/settings/billing?canceled=true"

    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_redirect_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("https", "http"):
            raise ValueError("Redirect URL must use http or https")
        if parsed.hostname not in _ALLOWED_REDIRECT_HOSTS:
            raise ValueError("Redirect URL must be on an allowed domain")
        return v


@limiter.limit("20/minute")
@router.get("/status")
async def get_billing_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get current plan, usage, and limits.
    TESTING MODE: returns pro plan with unlimited limits if no org/sub found."""
    from app.services.org import OrgService
    org_service = OrgService()
    try:
        orgs = await org_service.get_user_orgs(current_user["id"])
    except Exception:
        orgs = []
    if not orgs:
        # No org yet — return free defaults (conservative limits)
        return {
            "plan": "free", "plan_name": "Free",
            "usage": {}, "limits": {"applications": 3, "exports": 5, "ats_scans": 5, "ai_calls": 20, "members": 1, "candidates": 10},
            "status": "active",
        }

    billing = BillingService()
    try:
        return await billing.get_plan_info(orgs[0]["id"])
    except Exception:
        return {
            "plan": "free", "plan_name": "Free",
            "usage": {}, "limits": {"applications": 3, "exports": 5, "ats_scans": 5, "ai_calls": 20, "members": 1, "candidates": 10},
            "status": "active",
        }


@limiter.limit("20/minute")
@router.post("/checkout")
async def create_checkout(
    request: Request,
    req: CheckoutRequest, current_user: Dict[str, Any] = Depends(get_current_user
)):
    """Create a Stripe checkout session for upgrading."""
    if req.plan not in ("pro", "enterprise"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan")

    from app.services.org import OrgService
    org_service = OrgService()
    orgs = await org_service.get_user_orgs(current_user["id"])
    if not orgs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Create an organization first")

    org = orgs[0]
    membership = await org_service.get_membership(org["id"], current_user["id"])
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can manage billing")

    billing = BillingService()
    url = await billing.create_checkout_session(org["id"], req.plan, req.success_url, req.cancel_url)
    if not url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing service unavailable. Configure STRIPE_SECRET_KEY.")
    return {"url": url}


@limiter.limit("20/minute")
@router.post("/portal")
async def create_portal(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Open Stripe billing portal for managing subscription."""
    from app.services.org import OrgService
    org_service = OrgService()
    orgs = await org_service.get_user_orgs(current_user["id"])
    if not orgs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No organization found")

    billing = BillingService()
    url = await billing.create_portal_session(orgs[0]["id"], f"{_FRONTEND_URL}/settings/billing")
    if not url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing portal unavailable")
    return {"url": url}


@limiter.limit("100/minute")
@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    import os
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    billing = BillingService()
    stripe = billing._get_stripe()

    if not stripe or not webhook_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Webhook error: {str(e)[:100]}")

    try:
        await billing.handle_webhook(event["type"], event["data"]["object"])
    except Exception as e:
        logger.error("stripe_webhook_processing_failed", event_type=event.get("type"), error=str(e)[:200])
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook processing failed")
    return {"status": "processed"}


class RecordUsageRequest(BaseModel):
    feature: str = "exports"


@limiter.limit("20/minute")
@router.post("/record-export")
async def record_export(
    request: Request,
    req: RecordUsageRequest, current_user: Dict[str, Any] = Depends(get_current_user
)):
    """Record a feature usage (export, application, etc.)."""
    from app.services.org import OrgService
    org_service = OrgService()
    orgs = await org_service.get_user_orgs(current_user["id"])
    org_id = orgs[0]["id"] if orgs else current_user["id"]

    billing = BillingService()
    await billing.record_usage(org_id, current_user["id"], req.feature)
    plan_info = await billing.get_plan_info(org_id) if orgs else {"usage": {req.feature: 1}}
    return {"recorded": True, "usage": plan_info.get("usage", {})}


@limiter.limit("20/minute")
@router.get("/quota-check")
async def quota_check(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Lightweight quota check for the download gate."""
    from app.services.org import OrgService
    org_service = OrgService()
    orgs = await org_service.get_user_orgs(current_user["id"])
    org_id = orgs[0]["id"] if orgs else current_user["id"]

    billing = BillingService()
    info = await billing.get_plan_info(org_id) if orgs else {
        "plan": "free", "usage": {}, "limits": {"exports": 5, "applications": 5}
    }
    return info
