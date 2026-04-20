"""W6 Integrations — webhook retry + Slack formatter anchor tests.

Verifies the code paths without hitting the network: we assert on the
behavior of pure helpers and on the delivery loop wiring via mocks.
"""
from __future__ import annotations

import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch


def test_slack_url_detection() -> None:
    from app.services.webhook import _is_slack_url
    assert _is_slack_url("https://hooks.slack.com/services/T00/B00/xxx") is True
    assert _is_slack_url("https://myapp.example.com/webhook") is False
    assert _is_slack_url("") is False
    assert _is_slack_url(None) is False  # type: ignore[arg-type]


def test_slack_payload_has_top_level_text() -> None:
    from app.services.webhook import _format_slack_payload
    out = _format_slack_payload(
        "pipeline.completed",
        {"application_id": "abc", "job_title": "SWE", "company": "Acme", "score": 87},
    )
    assert "text" in out, "Slack requires top-level 'text'"
    assert "Pipeline · Completed" in out["text"]
    # highlights must include known fields
    assert "Acme" in out["text"]
    assert "SWE" in out["text"]
    # attachment colour defaults to 'good' on success events
    assert out["attachments"][0]["color"] == "good"


def test_slack_payload_uses_danger_color_on_failure_events() -> None:
    from app.services.webhook import _format_slack_payload
    out = _format_slack_payload("pipeline.failed", {"reason": "boom"})
    assert out["attachments"][0]["color"] == "danger"


def test_webhook_retry_constants_are_sane() -> None:
    from app.services import webhook as wh_mod
    assert wh_mod._RETRY_MAX_ATTEMPTS >= 2
    assert wh_mod._RETRY_MAX_ATTEMPTS <= 5  # avoid thundering herd
    assert 429 in wh_mod._RETRYABLE_STATUSES
    assert 502 in wh_mod._RETRYABLE_STATUSES
    assert 500 in wh_mod._RETRYABLE_STATUSES
    # 4xx (other than listed) must NOT retry
    assert 404 not in wh_mod._RETRYABLE_STATUSES
    assert 401 not in wh_mod._RETRYABLE_STATUSES


def test_fire_retries_on_transient_failure_then_succeeds() -> None:
    """Transient 503 → retry → 200 must count as delivered (no failure record)."""
    from app.services.webhook import WebhookService

    fake_db = MagicMock()
    fake_db.query = AsyncMock(return_value=[{
        "id": "wh_1",
        "url": "https://example.com/hook",
        "secret": "shhh",
        "events": ["*"],
        "is_active": True,
    }])
    fake_db.update = AsyncMock()
    fake_db.get = AsyncMock(return_value={"failure_count": 0})

    # httpx responses: 503 then 200
    class _Resp:
        def __init__(self, code):
            self.status_code = code

    client_instance = MagicMock()
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)
    client_instance.post = AsyncMock(side_effect=[_Resp(503), _Resp(200)])

    svc = WebhookService(db=fake_db)
    with patch("app.services.webhook.httpx.AsyncClient", return_value=client_instance), \
         patch("app.services.webhook.asyncio.sleep", new=AsyncMock()):
        import asyncio
        asyncio.run(svc.fire("org_1", "pipeline.completed", {"score": 90}))

    # On success: update called with reset failure_count=0
    assert fake_db.update.await_count == 1
    update_args = fake_db.update.await_args.args
    assert update_args[1] == "wh_1"
    assert update_args[2]["failure_count"] == 0
    # get (used by _record_failure) must NOT have been called.
    assert fake_db.get.await_count == 0


def test_fire_does_not_retry_hard_4xx() -> None:
    """401 Unauthorized is terminal — no retries, go straight to failure record."""
    from app.services.webhook import WebhookService

    fake_db = MagicMock()
    fake_db.query = AsyncMock(return_value=[{
        "id": "wh_2",
        "url": "https://example.com/hook",
        "secret": "shhh",
        "events": ["pipeline.completed"],
        "is_active": True,
    }])
    fake_db.update = AsyncMock()
    fake_db.get = AsyncMock(return_value={"failure_count": 0})

    class _Resp:
        def __init__(self, code):
            self.status_code = code

    client_instance = MagicMock()
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)
    client_instance.post = AsyncMock(return_value=_Resp(401))

    svc = WebhookService(db=fake_db)
    with patch("app.services.webhook.httpx.AsyncClient", return_value=client_instance), \
         patch("app.services.webhook.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        import asyncio
        asyncio.run(svc.fire("org_1", "pipeline.completed", {"score": 90}))

    # Exactly one POST — hard 4xx is NOT retried.
    assert client_instance.post.await_count == 1
    sleep_mock.assert_not_awaited()
    # Failure recorded (_record_failure queries the webhook row).
    assert fake_db.get.await_count == 1


def test_slack_webhook_sends_slack_shape() -> None:
    """When URL is a Slack incoming webhook, the body must carry a 'text' field."""
    from app.services.webhook import WebhookService

    fake_db = MagicMock()
    fake_db.query = AsyncMock(return_value=[{
        "id": "wh_slack",
        "url": "https://hooks.slack.com/services/T0/B0/xyz",
        "secret": "s",
        "events": ["*"],
        "is_active": True,
    }])
    fake_db.update = AsyncMock()

    class _Resp:
        status_code = 200

    client_instance = MagicMock()
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)
    client_instance.post = AsyncMock(return_value=_Resp())

    svc = WebhookService(db=fake_db)
    with patch("app.services.webhook.httpx.AsyncClient", return_value=client_instance):
        import asyncio
        asyncio.run(svc.fire("org_1", "pipeline.completed", {"score": 90, "company": "Acme"}))

    sent_body = client_instance.post.await_args.kwargs["content"]
    parsed = json.loads(sent_body)
    assert "text" in parsed, "Slack payload missing required 'text' field"
    assert "Acme" in parsed["text"]


def test_fire_method_is_async_and_signed() -> None:
    """Anchor test: invariants against accidental regression."""
    from app.services import webhook as wh_mod
    src = inspect.getsource(wh_mod.WebhookService.fire)
    assert "hmac.new" in src, "HMAC signing must remain in fire()"
    assert "X-HireStack-Signature" in src
    assert "X-HireStack-Delivery-Attempt" in src, "retry attempt header must stay"
