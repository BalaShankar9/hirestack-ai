"""Observability helpers — log + error-tracker scrubbing.

S11-F2 closure for R2 (no log redaction) and R3/R6 (Sentry hardening).

Two pure functions are exported so they can be unit-tested in isolation:

  - `redact_event_dict(event_dict)`   — structlog processor.
  - `sentry_before_send(event, hint)` — Sentry SDK `before_send` hook.

Both target the same key list (`SENSITIVE_KEYS`) and use the same
matching rule (case-insensitive substring match against dict keys),
so a developer who adds a new key type only has to extend one constant.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

REDACTED = "[REDACTED]"

# Case-insensitive substring match. "authorization" matches "Authorization",
# "x-authorization", "auth_token" via "auth", etc.
SENSITIVE_KEYS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "cookie",
    "set-cookie",
    "session",
    "private_key",
    "client_secret",
    "refresh_token",
    "access_token",
    "service_role_key",
)


def _is_sensitive(key: str) -> bool:
    """Return True if *key* (case-insensitive) contains any sensitive marker."""
    lk = key.lower()
    return any(marker in lk for marker in SENSITIVE_KEYS)


def _scrub(value: Any, *, _depth: int = 0) -> Any:
    """Recursively walk *value*, replacing values whose KEY is sensitive
    with ``REDACTED``.

    Applies a small depth limit (8) and a small list-length limit (1000)
    to bound work and avoid runaway recursion on cyclic structures.
    """
    if _depth > 8:
        return value
    if isinstance(value, Mapping):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _is_sensitive(k):
                out[k] = REDACTED
            else:
                out[k] = _scrub(v, _depth=_depth + 1)
        return out
    if isinstance(value, list):
        if len(value) > 1000:
            return value
        return [_scrub(item, _depth=_depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item, _depth=_depth + 1) for item in value)
    return value


def redact_event_dict(
    logger_instance: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor signature.

    Replaces values for any sensitive top-level key, then recurses into
    nested dicts/lists. Pure — never raises. Returns the same mapping
    (mutated) so structlog's pipeline keeps moving.
    """
    keys_to_walk = list(event_dict.keys())
    for k in keys_to_walk:
        v = event_dict[k]
        if isinstance(k, str) and _is_sensitive(k):
            event_dict[k] = REDACTED
        else:
            event_dict[k] = _scrub(v)
    return event_dict


def sentry_before_send(
    event: MutableMapping[str, Any], hint: Mapping[str, Any] | None = None
) -> MutableMapping[str, Any] | None:
    """Sentry SDK `before_send` hook — scrub request bodies, query
    strings, and free-form `extra` fields.

    Returns the (mutated) event so Sentry continues processing.
    Returning None would drop the event entirely — we don't want that.
    """
    try:
        # request.headers, request.cookies, request.data
        req = event.get("request")
        if isinstance(req, dict):
            for sub_key in ("headers", "cookies", "data", "query_string", "env"):
                if sub_key in req:
                    req[sub_key] = _scrub(req[sub_key])
        # contexts may carry runtime / app state
        contexts = event.get("contexts")
        if isinstance(contexts, dict):
            event["contexts"] = _scrub(contexts)
        # extra is free-form
        extra = event.get("extra")
        if isinstance(extra, dict):
            event["extra"] = _scrub(extra)
        # breadcrumbs may carry HTTP traces with auth headers
        crumbs = event.get("breadcrumbs")
        if isinstance(crumbs, dict) and "values" in crumbs and isinstance(crumbs["values"], list):
            crumbs["values"] = [_scrub(b) for b in crumbs["values"]]
    except Exception:
        # Never let a bug in the scrubber prevent error reporting.
        return event
    return event
