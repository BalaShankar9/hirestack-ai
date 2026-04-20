"""
Billing Service
Handles Stripe integration, plan management, and usage enforcement.
"""
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()

# Plan definitions
PLANS = {
    "free": {
        "name": "Free",
        "price_monthly": 0,
        "limits": {"applications": 5, "ats_scans": 10, "ai_calls": 50, "members": 2, "candidates": 10},
    },
    "pro": {
        "name": "Pro",
        "price_monthly": 49,
        "limits": {"applications": 50, "ats_scans": 200, "ai_calls": 1000, "members": 10, "candidates": 100},
    },
    "enterprise": {
        "name": "Enterprise",
        "price_monthly": 199,
        "limits": {"applications": -1, "ats_scans": -1, "ai_calls": -1, "members": -1, "candidates": -1},
    },
}


class BillingService:
    """Handles billing, subscriptions, and usage enforcement."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.stripe_key = os.getenv("STRIPE_SECRET_KEY", "")

    def _get_stripe(self):
        """Lazy-load Stripe SDK."""
        try:
            import stripe
            stripe.api_key = self.stripe_key
            return stripe
        except ImportError:
            logger.warning("stripe_not_installed")
            return None

    async def get_subscription(self, org_id: str) -> Optional[Dict[str, Any]]:
        """Get the active subscription for an org."""
        subs = await self.db.query(
            TABLES["subscriptions"],
            filters=[("org_id", "==", org_id), ("status", "==", "active")],
            limit=1,
        )
        return subs[0] if subs else None

    async def get_plan_info(self, org_id: str) -> Dict[str, Any]:
        """Get current plan with usage and limits."""
        sub = await self.get_subscription(org_id)
        plan_key = sub.get("plan", "free") if sub else "free"
        plan = PLANS.get(plan_key, PLANS["free"])
        limits = sub.get("usage_limits", plan["limits"]) if sub else plan["limits"]

        # Get current usage
        period = datetime.now(timezone.utc).strftime("%Y-%m-01")
        records = await self.db.query(
            TABLES["usage_records"],
            filters=[("org_id", "==", org_id), ("period_start", "==", period)],
        )
        usage: Dict[str, int] = {}
        for r in records:
            f = r.get("feature", "unknown")
            usage[f] = usage.get(f, 0) + r.get("quantity", 1)

        return {
            "plan": plan_key,
            "plan_name": plan["name"],
            "price": plan["price_monthly"],
            "limits": limits,
            "usage": usage,
            "subscription_id": sub.get("id") if sub else None,
            "status": sub.get("status", "none") if sub else "none",
            "current_period_end": sub.get("current_period_end") if sub else None,
        }

    async def check_limit(self, org_id: str, feature: str) -> bool:
        """Check if the org can use a feature (within plan limits)."""
        sub = await self.get_subscription(org_id)
        if not sub:
            # No subscription = free plan limits
            free_limits = PLANS["free"]["limits"]
            limit = free_limits.get(feature, -1)
            if limit == -1:
                return True
            period = datetime.now(timezone.utc).strftime("%Y-%m-01")
            records = await self.db.query(
                TABLES["usage_records"],
                filters=[("org_id", "==", org_id), ("feature", "==", feature), ("period_start", "==", period)],
            )
            current = sum(r.get("quantity", 1) for r in records)
            return current < limit
        limits = sub.get("usage_limits", {})
        limit = limits.get(feature, -1)
        if limit == -1:
            return True  # Unlimited

        period = datetime.now(timezone.utc).strftime("%Y-%m-01")
        records = await self.db.query(
            TABLES["usage_records"],
            filters=[("org_id", "==", org_id), ("feature", "==", feature), ("period_start", "==", period)],
        )
        current = sum(r.get("quantity", 1) for r in records)
        return current < limit

    async def record_usage(self, org_id: str, user_id: str, feature: str, quantity: int = 1):
        """Record usage of a feature."""
        await self.db.create(TABLES["usage_records"], {
            "org_id": org_id,
            "user_id": user_id,
            "feature": feature,
            "quantity": quantity,
            "period_start": datetime.now(timezone.utc).strftime("%Y-%m-01"),
        })

    async def create_checkout_session(self, org_id: str, plan: str, success_url: str, cancel_url: str) -> Optional[str]:
        """Create a Stripe checkout session."""
        stripe = self._get_stripe()
        if not stripe or not self.stripe_key:
            logger.warning("stripe_not_configured")
            return None

        plan_info = PLANS.get(plan)
        if not plan_info or plan_info["price_monthly"] == 0:
            return None

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": os.getenv(f"STRIPE_PRICE_{plan.upper()}", ""), "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"org_id": org_id, "plan": plan},
            )
            return session.url
        except Exception as e:
            logger.error("stripe_checkout_failed", error=str(e)[:200])
            return None

    async def create_portal_session(self, org_id: str, return_url: str) -> Optional[str]:
        """Create a Stripe billing portal session."""
        stripe = self._get_stripe()
        if not stripe or not self.stripe_key:
            return None

        sub = await self.get_subscription(org_id)
        if not sub or not sub.get("stripe_subscription_id"):
            return None

        # Get org's Stripe customer ID
        org = await self.db.get(TABLES["organizations"], org_id)
        if not org or not org.get("stripe_customer_id"):
            return None

        try:
            session = stripe.billing_portal.Session.create(
                customer=org["stripe_customer_id"],
                return_url=return_url,
            )
            return session.url
        except Exception as e:
            logger.error("stripe_portal_failed", error=str(e)[:200])
            return None

    async def handle_webhook(self, event_type: str, data: Dict[str, Any]):
        """Handle a Stripe webhook event with idempotency protection.

        Persists every event_id to ``processed_webhook_events`` BEFORE
        running the side effect. The PRIMARY KEY on event_id makes the
        insert atomic across instances and restarts — a duplicate insert
        raises and we early-return without re-running side effects.

        Falls back to in-memory subscription check if the ledger table
        is unavailable (graceful degradation, not silent skip).
        """
        _event_id = data.get("id") or data.get("object", {}).get("id", "")

        if _event_id:
            try:
                # Atomic claim: if another worker already processed this
                # event, the unique-PK insert raises and we bail.
                already = await self.db.get(TABLES["processed_webhook_events"], _event_id)
                if already:
                    logger.info(
                        "webhook_idempotent_skip",
                        event_id=_event_id,
                        event_type=event_type,
                    )
                    return
                await self.db.create(TABLES["processed_webhook_events"], {
                    "event_id": _event_id,
                    "event_type": event_type,
                    "org_id": data.get("metadata", {}).get("org_id") or "",
                })
            except Exception as e:
                # Race: a parallel worker won the insert. Treat as already-processed.
                _err = str(e).lower()
                if "duplicate" in _err or "unique" in _err or "primary key" in _err:
                    logger.info(
                        "webhook_idempotent_race_skip",
                        event_id=_event_id,
                        event_type=event_type,
                    )
                    return
                # Ledger table missing or DB hiccup — log and fall through
                # to legacy in-memory check (better than dropping the event).
                logger.warning(
                    "webhook_idempotency_ledger_unavailable",
                    event_id=_event_id,
                    error=str(e)[:200],
                )

        if event_type == "checkout.session.completed":
            org_id = data.get("metadata", {}).get("org_id")
            plan = data.get("metadata", {}).get("plan", "pro")
            if org_id:
                # Legacy in-memory guard (still useful for the no-event_id
                # edge case and as a safety net).
                existing_sub = await self.get_subscription(org_id)
                stripe_sub_id = data.get("subscription", "")
                if existing_sub and existing_sub.get("stripe_subscription_id") == stripe_sub_id:
                    logger.info("webhook_duplicate_skipped", event_type=event_type, org_id=org_id)
                    return
                await self._activate_subscription(org_id, plan, data)

        elif event_type == "customer.subscription.updated":
            sub_id = data.get("id")
            if sub_id:
                await self._update_subscription(sub_id, data)

        elif event_type == "customer.subscription.deleted":
            sub_id = data.get("id")
            if sub_id:
                await self._cancel_subscription(sub_id)

    async def _activate_subscription(self, org_id: str, plan: str, data: Dict):
        """Activate a subscription after successful checkout."""
        plan_info = PLANS.get(plan)
        if not plan_info:
            logger.error("billing_unknown_plan", plan=plan, org_id=org_id)
            plan_info = PLANS["free"]
            plan = "free"
        stripe_sub_id = data.get("subscription", "")
        stripe_customer_id = data.get("customer", "")

        # Update org
        await self.db.update(TABLES["organizations"], org_id, {
            "tier": plan,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_sub_id,
        })

        # Create/update subscription record
        existing = await self.get_subscription(org_id)
        sub_data = {
            "org_id": org_id,
            "plan": plan,
            "status": "active",
            "stripe_subscription_id": stripe_sub_id,
            "usage_limits": plan_info["limits"],
        }
        if existing:
            await self.db.update(TABLES["subscriptions"], existing["id"], sub_data)
        else:
            await self.db.create(TABLES["subscriptions"], sub_data)

        logger.info("subscription_activated", org_id=org_id, plan=plan)

    async def _update_subscription(self, stripe_sub_id: str, data: Dict):
        """Update subscription status from Stripe webhook."""
        subs = await self.db.query(TABLES["subscriptions"], filters=[("stripe_subscription_id", "==", stripe_sub_id)], limit=1)
        if subs:
            status = data.get("status", "active")
            await self.db.update(TABLES["subscriptions"], subs[0]["id"], {"status": status})

    async def _cancel_subscription(self, stripe_sub_id: str):
        """Cancel a subscription."""
        subs = await self.db.query(TABLES["subscriptions"], filters=[("stripe_subscription_id", "==", stripe_sub_id)], limit=1)
        if subs:
            await self.db.update(TABLES["subscriptions"], subs[0]["id"], {"status": "canceled", "plan": "free"})
            # Downgrade org tier
            org_id = subs[0].get("org_id")
            if org_id:
                await self.db.update(TABLES["organizations"], org_id, {"tier": "free"})
