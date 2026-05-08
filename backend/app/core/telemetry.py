"""OpenTelemetry bootstrap.

PR m4-pr12: optional OTLP/HTTP tracing for FastAPI + httpx.

Activation contract — ALL of these must be true:
- ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set to a non-empty string.
- The ``opentelemetry-*`` packages are importable.

If either condition fails, ``setup_telemetry`` is a no-op so the app still
boots in environments (CI, local dev, prod-without-collector) that have not
provisioned a collector yet. Rollback = unset ``OTEL_EXPORTER_OTLP_ENDPOINT``.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_INITIALISED = False


def setup_telemetry(app: Any) -> bool:
    """Install OTel tracing on ``app``. Returns True iff actually wired.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _INITIALISED
    if _INITIALISED:
        return True

    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not endpoint:
        logger.debug("telemetry: OTEL_EXPORTER_OTLP_ENDPOINT unset, skipping")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:  # pragma: no cover — optional dep guard
        logger.warning("telemetry: opentelemetry SDK missing (%s); skipping", exc)
        return False

    service_name = os.getenv("OTEL_SERVICE_NAME") or "hirestack-backend"
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    # Instrument frameworks. Each wrapped in its own try so a partial failure
    # does not abort the whole bootstrap.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # PR m6-pr22: stamp standard attrs on every FastAPI server span so
        # cross-service correlation works without per-route boilerplate.
        FastAPIInstrumentor.instrument_app(
            app, server_request_hook=_fastapi_server_request_hook
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("telemetry: FastAPI instrumentor failed: %s", exc)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover
        logger.warning("telemetry: httpx instrumentor failed: %s", exc)

    _INITIALISED = True
    logger.info("telemetry: OTLP HTTP tracing → %s (service=%s)", endpoint, service_name)
    return True


# ── Standard span attributes (PR m6-pr22) ──────────────────────────────
# Single source of truth for the four labels every HireStack span carries:
#   • request_id  — correlates traces ↔ logs (RequestIDMiddleware contextvar)
#   • org_id      — multi-tenant filter
#   • domain      — agent / aim / portal / generation / etc.
#   • route       — FastAPI route template ("/api/aim/sections/{id}")
# Other instrumenters/exporters key dashboards off these names; do not
# rename without updating dashboards in tandem.

ATTR_REQUEST_ID = "hirestack.request_id"
ATTR_ORG_ID = "hirestack.org_id"
ATTR_DOMAIN = "hirestack.domain"
ATTR_ROUTE = "hirestack.route"


def set_standard_attrs(
    span: Any,
    *,
    request_id: str | None = None,
    org_id: str | None = None,
    domain: str | None = None,
    route: str | None = None,
) -> None:
    """Attach the four standard attributes to ``span``.

    No-op when ``span`` is None or an OTel NonRecordingSpan. Only sets
    keys whose values are truthy strings — avoids cluttering spans with
    empty labels.
    """
    if span is None:
        return
    if not getattr(span, "is_recording", lambda: True)():
        return
    if request_id:
        span.set_attribute(ATTR_REQUEST_ID, str(request_id)[:128])
    if org_id:
        span.set_attribute(ATTR_ORG_ID, str(org_id)[:64])
    if domain:
        span.set_attribute(ATTR_DOMAIN, str(domain)[:64])
    if route:
        span.set_attribute(ATTR_ROUTE, str(route)[:256])


def _fastapi_server_request_hook(span: Any, scope: dict[str, Any]) -> None:
    """FastAPIInstrumentor hook: copy contextvar + headers onto the span.

    Runs synchronously at request entry, BEFORE handler dispatch. The
    RequestIDMiddleware is added before the OTel instrumentor (because
    Starlette wraps middlewares in REVERSE add order), so the contextvar
    is already populated by the time this hook fires.
    """
    try:
        if span is None or not getattr(span, "is_recording", lambda: True)():
            return
        from app.core.tracing import request_id_var  # local import (no cycle)

        rid = request_id_var.get("") or ""
        # Header-based fallbacks for org_id (multi-tenant) — same lookup
        # access_log middleware uses.
        org_id = ""
        for name, value in scope.get("headers", []) or []:
            if name == b"x-org-id":
                org_id = value.decode("latin-1", errors="replace")[:64]
                break
        # FastAPI populates scope["route"].path for matched routes; fall
        # back to raw path for 404s / unmatched.
        route_obj = scope.get("route")
        route_template = getattr(route_obj, "path", None) or scope.get("path", "")
        set_standard_attrs(
            span,
            request_id=rid,
            org_id=org_id or None,
            route=route_template or None,
            domain="http",
        )
    except Exception:  # pragma: no cover — telemetry must never break a request
        pass


__all__ = [
    "setup_telemetry",
    "set_standard_attrs",
    "ATTR_REQUEST_ID",
    "ATTR_ORG_ID",
    "ATTR_DOMAIN",
    "ATTR_ROUTE",
]
