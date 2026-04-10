"""
Webhook Service
Fires webhook events to registered endpoints when key actions happen.
"""
import hashlib
import hmac
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import httpx
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()


class WebhookService:
    """Dispatches webhook events to registered endpoints."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def fire(self, org_id: str, event_type: str, payload: Dict[str, Any]):
        """Fire a webhook event to all registered endpoints for this org."""
        webhooks = await self.db.query(
            TABLES["webhooks"],
            filters=[("org_id", "==", org_id), ("is_active", "==", True)],
        )

        for wh in webhooks:
            # Check if this webhook subscribes to this event
            events = wh.get("events", ["*"])
            if "*" not in events and event_type not in events:
                continue

            url = wh.get("url", "")
            secret = wh.get("secret", "")
            if not url:
                continue

            body = json.dumps({
                "event": event_type,
                "data": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "webhook_id": wh["id"],
            })

            # Sign payload
            signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-HireStack-Signature": f"sha256={signature}",
                            "X-HireStack-Event": event_type,
                        },
                    )
                    if resp.status_code >= 400:
                        await self._record_failure(wh["id"])
                    else:
                        await self.db.update(TABLES["webhooks"], wh["id"], {
                            "last_triggered_at": datetime.now(timezone.utc).isoformat(),
                            "failure_count": 0,
                        })
            except Exception as e:
                logger.warning("webhook_delivery_failed", webhook_id=wh["id"], url=url, error=str(e)[:100])
                await self._record_failure(wh["id"])

    async def _record_failure(self, webhook_id: str):
        """Record a webhook delivery failure. Disable after 10 consecutive failures."""
        wh = await self.db.get(TABLES["webhooks"], webhook_id)
        if not wh:
            return
        failures = (wh.get("failure_count") or 0) + 1
        update: Dict[str, Any] = {"failure_count": failures}
        if failures >= 10:
            update["is_active"] = False
            logger.warning("webhook_disabled_after_failures", webhook_id=webhook_id, failures=failures)
        await self.db.update(TABLES["webhooks"], webhook_id, update)

    async def register(self, org_id: str, url: str, events: list = None, secret: str = "") -> str:
        """Register a new webhook endpoint."""
        import secrets as _secrets
        if not secret:
            secret = _secrets.token_urlsafe(32)
        wh_id = await self.db.create(TABLES["webhooks"], {
            "org_id": org_id,
            "url": url,
            "secret": secret,
            "events": events or ["*"],
            "is_active": True,
        })
        return wh_id

    async def list_webhooks(self, org_id: str):
        return await self.db.query(TABLES["webhooks"], filters=[("org_id", "==", org_id)])

    async def delete_webhook(self, webhook_id: str):
        return await self.db.delete(TABLES["webhooks"], webhook_id)
