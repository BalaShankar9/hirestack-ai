"""
Webhook Service
Fires webhook events to registered endpoints when key actions happen.
"""
import asyncio
import hashlib
import hmac
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import httpx
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()

# ── W6: retry policy for transient failures ──────────────────────────
# Network errors and 5xx responses are retried with capped exponential
# backoff. 4xx responses (except 429) are NOT retried — they mean the
# consumer's endpoint is misconfigured and more tries won't help.
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_BASE_S = 0.5
_RETRY_BACKOFF_CAP_S = 4.0
_RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def _is_slack_url(url: str) -> bool:
    """Heuristic: Slack incoming-webhooks expect their own payload shape."""
    if not url:
        return False
    u = url.lower()
    return "hooks.slack.com/services" in u or "slack.com/services" in u


def _format_slack_payload(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a HireStack webhook body to Slack Incoming Webhook JSON.

    Slack requires a top-level 'text' field. We surface the event name plus
    a handful of common fields (application_id, job_title, company) if
    present — keeping the raw event payload in an attachment for debugging.
    """
    title = event_type.replace("_", " ").replace(".", " · ").title()
    highlights: list[str] = []
    for key in ("application_id", "job_title", "company", "status", "score"):
        val = payload.get(key)
        if val is not None and val != "":
            highlights.append(f"*{key.replace('_', ' ').title()}*: {val}")
    text_lines = [f"*{title}*"]
    if highlights:
        text_lines.append(" | ".join(highlights))
    return {
        "text": "\n".join(text_lines),
        "attachments": [
            {
                "color": "good" if "failed" not in event_type else "danger",
                "text": f"```{json.dumps(payload, default=str)[:3500]}```",
            }
        ],
    }


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

            # W6: Slack-compatible body when the URL points at Slack.
            if _is_slack_url(url):
                body_obj: Dict[str, Any] = _format_slack_payload(event_type, payload)
            else:
                body_obj = {
                    "event": event_type,
                    "data": payload,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "webhook_id": wh["id"],
                }
            body = json.dumps(body_obj)

            # Sign payload (HMAC over body bytes; consumer must use the
            # exact shipped bytes — including the Slack-compatible shape —
            # to re-compute the signature).
            signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()

            # W6: capped exponential-backoff retry for transient failures.
            delivered = False
            last_status: Optional[int] = None
            last_err: Optional[str] = None
            for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(
                            url,
                            content=body,
                            headers={
                                "Content-Type": "application/json",
                                "X-HireStack-Signature": f"sha256={signature}",
                                "X-HireStack-Event": event_type,
                                "X-HireStack-Delivery-Attempt": str(attempt),
                            },
                        )
                        last_status = resp.status_code
                    if resp.status_code < 400:
                        delivered = True
                        break
                    if resp.status_code not in _RETRYABLE_STATUSES:
                        # Hard failure — do not retry.
                        break
                except Exception as e:
                    last_err = str(e)[:200]
                # Back off before next attempt.
                if attempt < _RETRY_MAX_ATTEMPTS:
                    delay = min(
                        _RETRY_BACKOFF_CAP_S,
                        _RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)),
                    )
                    await asyncio.sleep(delay)

            if delivered:
                await self.db.update(TABLES["webhooks"], wh["id"], {
                    "last_triggered_at": datetime.now(timezone.utc).isoformat(),
                    "failure_count": 0,
                })
            else:
                logger.warning(
                    "webhook_delivery_failed",
                    webhook_id=wh["id"],
                    url=url,
                    last_status=last_status,
                    error=last_err,
                    attempts=_RETRY_MAX_ATTEMPTS,
                )
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
