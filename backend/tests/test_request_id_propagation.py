"""S11-F3: request_id round-trip + middleware order regression guard.

R4: ensures the X-Request-ID header is honoured (when supplied) or
generated (when not), is reflected on the response, and propagates
into structlog event_dicts via the contextvar.

R5: pins the middleware add-order. Starlette executes middleware in
REVERSE add-order, so RequestIDMiddleware (added FIRST) is the
OUTERMOST wrapper, which is what we want — every other middleware
sees `request_id_var` populated.
"""
from __future__ import annotations

import inspect
import re
import uuid

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.tracing import (
    AccessLogMiddleware,
    MaxBodySizeMiddleware,
    RequestIDMiddleware,
    TimeoutMiddleware,
    request_id_var,
)


# ── round-trip ────────────────────────────────────────────────────────
def _build_app(observed: dict) -> Starlette:
    async def endpoint(request):
        # Capture what RequestIDMiddleware put in the contextvar.
        observed["rid_in_handler"] = request_id_var.get("")
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", endpoint)])
    app.add_middleware(RequestIDMiddleware)
    return app


def test_request_id_generated_when_missing() -> None:
    observed: dict = {}
    client = TestClient(_build_app(observed))
    resp = client.get("/x")
    assert resp.status_code == 200
    rid = resp.headers.get("x-request-id")
    assert rid, "response must carry x-request-id"
    assert re.fullmatch(r"[0-9a-f]{16}", rid), f"generated rid wrong shape: {rid!r}"
    assert observed["rid_in_handler"] == rid


def test_request_id_honours_upstream_header() -> None:
    observed: dict = {}
    client = TestClient(_build_app(observed))
    upstream = "trace-abc-123"
    resp = client.get("/x", headers={"X-Request-ID": upstream})
    assert resp.headers["x-request-id"] == upstream
    assert observed["rid_in_handler"] == upstream


def test_request_id_caps_oversized_upstream_header() -> None:
    observed: dict = {}
    client = TestClient(_build_app(observed))
    huge = "z" * 5000
    resp = client.get("/x", headers={"X-Request-ID": huge})
    rid = resp.headers["x-request-id"]
    assert len(rid) <= 128
    assert observed["rid_in_handler"] == rid


def test_request_id_isolated_between_requests() -> None:
    observed: dict = {}
    client = TestClient(_build_app(observed))
    r1 = client.get("/x", headers={"X-Request-ID": "a"})
    r2 = client.get("/x", headers={"X-Request-ID": "b"})
    assert r1.headers["x-request-id"] == "a"
    assert r2.headers["x-request-id"] == "b"


def test_request_id_clears_after_request() -> None:
    """After RequestIDMiddleware exits, the contextvar must be reset
    to its default so a later background task doesn't inherit a stale id."""
    observed: dict = {}
    client = TestClient(_build_app(observed))
    client.get("/x", headers={"X-Request-ID": "stale"})
    # Outside any request scope:
    assert request_id_var.get("") == ""


# ── structlog integration ─────────────────────────────────────────────
def test_structlog_processor_picks_up_request_id() -> None:
    """The _add_request_id processor in main.py must read from the same
    contextvar that RequestIDMiddleware writes to."""
    import main

    src = inspect.getsource(main._add_request_id)
    assert "request_id_var" in src, (
        "S11-F3 R4 drift: _add_request_id no longer reads request_id_var; "
        "logs will lose correlation IDs."
    )


# ── middleware order regression ───────────────────────────────────────
def test_main_middleware_add_order_is_pinned() -> None:
    """Pin the add-order in main.py source. Starlette executes in
    REVERSE add-order, so the FIRST add is the OUTERMOST wrapper.
    Required outermost-to-innermost wrap order at runtime:
        RequestID → AccessLog → MaxBodySize → Timeout → SecurityHeaders
    Therefore add-order in source must be the SAME (first add becomes
    outermost). Any reorder would break either correlation IDs or
    body-size limits.
    """
    import main

    src = inspect.getsource(main)
    expected_order = [
        "app.add_middleware(RequestIDMiddleware)",
        "app.add_middleware(AccessLogMiddleware)",
        "app.add_middleware(MaxBodySizeMiddleware)",
        "app.add_middleware(TimeoutMiddleware)",
        "app.add_middleware(SecurityHeadersMiddleware)",
    ]
    positions = [src.find(line) for line in expected_order]
    for line, pos in zip(expected_order, positions):
        assert pos >= 0, f"middleware add line missing: {line!r}"
    assert positions == sorted(positions), (
        "S11-F3 R5 drift: middleware add-order changed. "
        "Expected RequestID → AccessLog → MaxBodySize → Timeout → SecurityHeaders. "
        f"Got positions: {dict(zip(expected_order, positions))}"
    )


def test_request_id_header_listed_in_cors_allow_headers() -> None:
    """If a browser cannot send X-Request-ID due to CORS, distributed
    tracing breaks for SPA traffic. Pin its presence."""
    import main

    src = inspect.getsource(main)
    # The CORSMiddleware allow_headers list must include X-Request-ID.
    assert '"X-Request-ID"' in src, (
        "S11-F3 R5 drift: X-Request-ID was removed from CORS allow_headers; "
        "browsers will strip the header on cross-origin requests."
    )
