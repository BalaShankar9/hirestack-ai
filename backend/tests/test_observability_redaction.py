"""S11-F2: log + Sentry redaction contract.

Pins the scrubber's behaviour so a refactor cannot quietly stop
masking sensitive values. Also pins that main.py wires the scrubber
into both structlog and Sentry, and that Sentry init carries
`release=settings.app_version`.
"""
from __future__ import annotations

import inspect

import pytest

from app.core.observability import (
    MAX_SCRUB_DEPTH,
    REDACTED,
    SENSITIVE_KEYS,
    redact_event_dict,
    sentry_before_send,
    _is_sensitive,
)


# ── _is_sensitive matrix ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "key",
    [
        "password",
        "Password",
        "user_password",
        "authorization",
        "Authorization",
        "X-Authorization",
        "api_key",
        "ApiKey",
        "Cookie",
        "Set-Cookie",
        "auth_token",
        "refresh_token",
        "access_token",
        "client_secret",
        "supabase_service_role_key",
    ],
)
def test_is_sensitive_matches(key: str) -> None:
    assert _is_sensitive(key) is True


@pytest.mark.parametrize(
    "key",
    ["user_id", "email", "name", "request_id", "duration_ms", "status", "path"],
)
def test_is_sensitive_does_not_match_safe(key: str) -> None:
    assert _is_sensitive(key) is False


# ── structlog processor ───────────────────────────────────────────────
def test_redact_event_dict_top_level() -> None:
    ev = {
        "event": "login",
        "password": "p@ssw0rd",
        "user_id": "u_123",
    }
    out = redact_event_dict(None, "info", ev)
    assert out["password"] == REDACTED
    assert out["user_id"] == "u_123"
    assert out["event"] == "login"


def test_redact_event_dict_nested_dict() -> None:
    ev = {
        "event": "request",
        "headers": {"Authorization": "Bearer abc.def.ghi", "User-Agent": "Mozilla"},
        "body": {"password": "x", "email": "a@b.c"},
    }
    out = redact_event_dict(None, "info", ev)
    assert out["headers"]["Authorization"] == REDACTED
    assert out["headers"]["User-Agent"] == "Mozilla"
    assert out["body"]["password"] == REDACTED
    assert out["body"]["email"] == "a@b.c"


def test_redact_event_dict_nested_list_of_dicts() -> None:
    ev = {"requests": [{"api_key": "k1"}, {"api_key": "k2"}]}
    out = redact_event_dict(None, "info", ev)
    assert out["requests"][0]["api_key"] == REDACTED
    assert out["requests"][1]["api_key"] == REDACTED


def test_redact_event_dict_returns_same_object() -> None:
    """Structlog mutates in place; processors should return the same mapping."""
    ev = {"x": 1}
    assert redact_event_dict(None, "info", ev) is ev


def test_redact_event_dict_handles_non_dict_value_gracefully() -> None:
    """Strings/ints/None as top-level values must not crash."""
    ev = {"event": "x", "count": 5, "label": None, "tags": ["a", "b"]}
    out = redact_event_dict(None, "info", ev)
    assert out["event"] == "x"
    assert out["count"] == 5
    assert out["label"] is None
    assert out["tags"] == ["a", "b"]


# ── Sentry before_send ────────────────────────────────────────────────
def test_sentry_before_send_scrubs_request_headers() -> None:
    event = {
        "request": {
            "headers": {"Authorization": "Bearer x", "Accept": "json"},
            "cookies": {"session": "s_abc"},
            "query_string": "token=abc&page=1",  # plain string, not scrubbed
            "data": {"password": "p"},
        }
    }
    out = sentry_before_send(event, {})
    assert out["request"]["headers"]["Authorization"] == REDACTED
    assert out["request"]["cookies"]["session"] == REDACTED
    assert out["request"]["data"]["password"] == REDACTED


def test_sentry_before_send_scrubs_extra_and_contexts() -> None:
    event = {
        "extra": {"api_key": "k", "user": "u"},
        "contexts": {"app": {"client_secret": "cs"}},
    }
    out = sentry_before_send(event, {})
    assert out["extra"]["api_key"] == REDACTED
    assert out["extra"]["user"] == "u"
    assert out["contexts"]["app"]["client_secret"] == REDACTED


def test_sentry_before_send_scrubs_breadcrumbs() -> None:
    event = {
        "breadcrumbs": {
            "values": [
                {"category": "http", "data": {"Authorization": "Bearer y"}},
            ]
        }
    }
    out = sentry_before_send(event, {})
    assert out["breadcrumbs"]["values"][0]["data"]["Authorization"] == REDACTED


def test_sentry_before_send_returns_event_not_none() -> None:
    """Returning None would drop the event entirely; we must always return it."""
    out = sentry_before_send({"foo": "bar"}, {})
    assert out is not None
    assert out["foo"] == "bar"


def test_sentry_before_send_swallows_exceptions() -> None:
    """If the scrubber bugs, we must still return the event so Sentry
    can still report the underlying error."""

    class _ExplodingMapping(dict):
        def get(self, *a, **kw):  # type: ignore[override]
            raise RuntimeError("boom")

    out = sentry_before_send(_ExplodingMapping(foo="bar"), {})
    assert out is not None


# ── main.py wiring contract ───────────────────────────────────────────
def test_main_wires_redactor_into_structlog() -> None:
    """Regression: main.py must register `redact_event_dict` in the
    structlog processor chain. A removal would silently re-open R2."""
    import main

    src = inspect.getsource(main)
    assert "redact_event_dict" in src, (
        "S11-F2 contract drift: main.py no longer references "
        "redact_event_dict; structlog redaction is bypassed."
    )


def test_main_wires_before_send_and_release_into_sentry() -> None:
    """Regression: Sentry init must carry release=app_version and
    before_send=sentry_before_send."""
    import main

    src = inspect.getsource(main)
    assert "before_send=sentry_before_send" in src, (
        "S11-F2 R3 drift: Sentry init lost before_send hook."
    )
    assert "release=settings.app_version" in src, (
        "S11-F2 R6 drift: Sentry init lost release pin."
    )


def test_sensitive_keys_is_non_empty_tuple() -> None:
    """Cheap regression — accidentally setting SENSITIVE_KEYS = () would
    silently disable redaction."""
    assert isinstance(SENSITIVE_KEYS, tuple)
    assert len(SENSITIVE_KEYS) >= 10


# ── m11-pr40: depth pin (TD-4) ────────────────────────────────────────
def test_max_scrub_depth_pinned_to_16() -> None:
    """TD-4: MAX_SCRUB_DEPTH must be ≥ 16 so deeply-nested Sentry
    payloads (request → context → breadcrumb → http → data → headers
    → nested envelope → ...) get scrubbed end-to-end."""
    assert MAX_SCRUB_DEPTH >= 16


def test_redact_scrubs_at_depth_15() -> None:
    """Build a 15-level nested dict with `password` at the bottom and
    verify redaction reaches it."""
    leaf = {"password": "p@ss"}
    nested: dict = leaf
    for _ in range(15):
        nested = {"wrap": nested}
    out = redact_event_dict(None, "info", {"root": nested})
    cur = out["root"]
    for _ in range(15):
        cur = cur["wrap"]
    assert cur["password"] == REDACTED


def test_redact_stops_past_max_depth() -> None:
    """At depth > MAX_SCRUB_DEPTH the scrubber bails. Pin that the cap
    is enforced (otherwise an infinite recursive structure would loop)."""
    leaf = {"password": "should-survive-because-too-deep"}
    nested: dict = leaf
    for _ in range(MAX_SCRUB_DEPTH + 5):
        nested = {"wrap": nested}
    out = redact_event_dict(None, "info", {"root": nested})
    cur = out["root"]
    for _ in range(MAX_SCRUB_DEPTH + 5):
        cur = cur["wrap"]
    # Beyond the depth limit the value is returned untouched.
    assert cur["password"] == "should-survive-because-too-deep"
