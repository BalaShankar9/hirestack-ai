"""PR m6-pr22: standard span attribute helpers + FastAPI hook.

Validates the four-attribute contract — request_id, org_id, domain,
route — that downstream dashboards key off. Uses an in-memory
``InMemorySpanExporter`` so we don't need a live collector.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_set_standard_attrs_writes_truthy_keys_only():
    from app.core.telemetry import (
        ATTR_DOMAIN,
        ATTR_ORG_ID,
        ATTR_REQUEST_ID,
        ATTR_ROUTE,
        set_standard_attrs,
    )

    span = MagicMock()
    span.is_recording.return_value = True

    set_standard_attrs(
        span,
        request_id="rid-123",
        org_id="org-abc",
        domain="aim",
        route="/api/aim/sections/{id}",
    )

    calls = {c.args[0]: c.args[1] for c in span.set_attribute.call_args_list}
    assert calls[ATTR_REQUEST_ID] == "rid-123"
    assert calls[ATTR_ORG_ID] == "org-abc"
    assert calls[ATTR_DOMAIN] == "aim"
    assert calls[ATTR_ROUTE] == "/api/aim/sections/{id}"


def test_set_standard_attrs_skips_falsy_values():
    from app.core.telemetry import set_standard_attrs

    span = MagicMock()
    span.is_recording.return_value = True

    set_standard_attrs(span, request_id="", org_id=None, domain="", route=None)
    # No attribute writes — every input was falsy.
    assert span.set_attribute.call_count == 0


def test_set_standard_attrs_noop_on_none_span():
    from app.core.telemetry import set_standard_attrs

    # Must not raise.
    set_standard_attrs(None, request_id="x", org_id="y", domain="z", route="/r")


def test_set_standard_attrs_skips_non_recording_span():
    from app.core.telemetry import set_standard_attrs

    span = MagicMock()
    span.is_recording.return_value = False
    set_standard_attrs(span, request_id="x", domain="aim")
    assert span.set_attribute.call_count == 0


def test_set_standard_attrs_truncates_long_values():
    from app.core.telemetry import ATTR_REQUEST_ID, set_standard_attrs

    span = MagicMock()
    span.is_recording.return_value = True
    huge = "a" * 500
    set_standard_attrs(span, request_id=huge)
    args = span.set_attribute.call_args_list[0].args
    assert args[0] == ATTR_REQUEST_ID
    assert len(args[1]) == 128  # capped


def test_fastapi_server_request_hook_pulls_request_id_and_org_id(monkeypatch):
    """Hook reads request_id_var (set by RequestIDMiddleware earlier in
    the ASGI chain) and the X-Org-Id header from the raw scope."""
    from app.core import telemetry as tel
    from app.core.tracing import request_id_var

    # Simulate RequestIDMiddleware having run first.
    token = request_id_var.set("rid-from-ctx")
    try:
        span = MagicMock()
        span.is_recording.return_value = True

        # Build a minimal ASGI scope with a route + org header.
        class _Route:
            path = "/api/aim/sections/{section_id}"

        scope = {
            "type": "http",
            "path": "/api/aim/sections/abc",
            "headers": [
                (b"x-org-id", b"org-xyz"),
                (b"content-type", b"application/json"),
            ],
            "route": _Route(),
        }

        tel._fastapi_server_request_hook(span, scope)
    finally:
        request_id_var.reset(token)

    calls = {c.args[0]: c.args[1] for c in span.set_attribute.call_args_list}
    assert calls[tel.ATTR_REQUEST_ID] == "rid-from-ctx"
    assert calls[tel.ATTR_ORG_ID] == "org-xyz"
    assert calls[tel.ATTR_ROUTE] == "/api/aim/sections/{section_id}"
    assert calls[tel.ATTR_DOMAIN] == "http"


def test_fastapi_server_request_hook_falls_back_to_raw_path():
    """When no route matched (404), we still record the raw path."""
    from app.core import telemetry as tel

    span = MagicMock()
    span.is_recording.return_value = True
    scope = {
        "type": "http",
        "path": "/missing",
        "headers": [],
        # no "route" key
    }
    tel._fastapi_server_request_hook(span, scope)
    calls = {c.args[0]: c.args[1] for c in span.set_attribute.call_args_list}
    assert calls[tel.ATTR_ROUTE] == "/missing"


def test_fastapi_server_request_hook_swallows_exceptions(monkeypatch):
    """Telemetry must NEVER raise into the request path."""
    from app.core import telemetry as tel

    # Span whose is_recording check raises — shouldn't bubble.
    span = MagicMock()
    span.is_recording.side_effect = RuntimeError("noisy")
    # No exception expected.
    tel._fastapi_server_request_hook(span, {"type": "http", "headers": []})
