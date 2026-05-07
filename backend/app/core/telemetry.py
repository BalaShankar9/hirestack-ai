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

        FastAPIInstrumentor.instrument_app(app)
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
