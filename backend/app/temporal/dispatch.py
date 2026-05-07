"""Temporal client dispatch helper for the generation workflow.

PR m6-pr18 — strangler entry point. Used by
`backend/app/api/routes/generate/jobs.py::_start_generation_job` when
`ff_temporal_generation` is set AND `TEMPORAL_HOST` is configured.
Stays a thin wrapper so that:

* the FastAPI process never imports `temporalio` at module import time
  (defer to first dispatch);
* unit tests can monkey-patch :func:`get_client` without spinning up
  Temporal infra.

There is no module-level Temporal client cache. Each request creates a
fresh client; the SDK pools the underlying gRPC channel internally and
the cost of `Client.connect` is dominated by the first TLS handshake,
which is amortised by the worker connection. We can revisit caching
once we have observability on dispatch latency.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.temporal.config import TemporalSettings, load_settings

logger = logging.getLogger(__name__)


def _workflow_id(job_id: str) -> str:
    return f"generation-{job_id}"


async def get_client(settings: Optional[TemporalSettings] = None) -> Any:
    """Connect to Temporal and return a `temporalio.client.Client`.

    Raises `RuntimeError` if `TEMPORAL_HOST` is not configured. The
    caller is responsible for branching on `settings.enabled` *before*
    calling this; we re-check defensively so importing the module never
    panics.
    """
    cfg = settings or load_settings()
    if not cfg.enabled:
        raise RuntimeError(
            "Temporal is not configured (TEMPORAL_HOST is unset)."
        )
    # Lazy import keeps the FastAPI app boot path free of temporalio.
    from temporalio.client import Client

    return await Client.connect(
        cfg.host,
        namespace=cfg.namespace,
        api_key=cfg.api_key,
        tls=cfg.tls or bool(cfg.api_key),
    )


async def dispatch_generation_workflow(
    *,
    job_id: str,
    user_id: str,
    application_id: str,
    requested_modules: list[str],
    settings: Optional[TemporalSettings] = None,
) -> str:
    """Start GenerationWorkflow on Temporal. Returns the workflow id.

    Errors are logged and re-raised so the caller can fall back to the
    legacy path (Redis Stream or in-process) if Temporal is unreachable.
    """
    cfg = settings or load_settings()
    # Lazy imports — same rationale as get_client.
    from app.temporal.activities import GenerationInput
    from app.temporal.workflows import GenerationWorkflow

    client = await get_client(cfg)
    workflow_id = _workflow_id(job_id)
    payload = GenerationInput(
        job_id=job_id,
        org_id="",
        user_id=user_id,
        document_type="application_bundle",
        payload={
            "application_id": application_id,
            "requested_modules": list(requested_modules),
        },
    )
    handle = await client.start_workflow(
        GenerationWorkflow.run,
        payload,
        id=workflow_id,
        task_queue=cfg.task_queue,
    )
    logger.info(
        "temporal_dispatch.started",
        extra={
            "job_id": job_id,
            "user_id": user_id,
            "workflow_id": handle.id,
            "task_queue": cfg.task_queue,
        },
    )
    return handle.id


__all__ = ["dispatch_generation_workflow", "get_client"]
