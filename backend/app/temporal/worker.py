"""Temporal worker entrypoint (PR m6-pr17).

Run via Procfile: ``python -m app.temporal.worker``.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from app.temporal.activities import ActivityHooks, build_activities
from app.temporal.activities.production import build_production_hooks
from app.temporal.config import TemporalSettings, load_settings
from app.temporal.workflows import GenerationWorkflow

logger = logging.getLogger("hirestack.temporal.worker")


async def _connect(settings: TemporalSettings):
    from temporalio.client import Client

    tls = True if settings.tls or settings.api_key else False
    return await Client.connect(
        settings.host,
        namespace=settings.namespace,
        api_key=settings.api_key,
        tls=tls,
    )


async def run_worker(
    settings: Optional[TemporalSettings] = None,
    hooks: Optional[ActivityHooks] = None,
) -> None:
    from temporalio.worker import Worker

    cfg = settings or load_settings()
    if not cfg.enabled:
        logger.warning("TEMPORAL_HOST unset; worker exiting cleanly.")
        return

    client = await _connect(cfg)
    # PR m6-pr24: default to production hooks that bridge the workflow
    # to the legacy generation runtime. Tests override via ``hooks=``.
    active_hooks = hooks if hooks is not None else build_production_hooks()
    worker = Worker(
        client,
        task_queue=cfg.task_queue,
        workflows=[GenerationWorkflow],
        activities=build_activities(active_hooks),
    )
    logger.info("temporal_worker_starting host=%s queue=%s", cfg.host, cfg.task_queue)
    await worker.run()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
