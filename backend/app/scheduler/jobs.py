"""Periodic background jobs owned by the scheduler process.

Extracted verbatim from ``backend/main.py`` (PR m2-pr6).  When the
``legacy_inproc_scheduler`` flag is True the web process imports these
and runs them inline (preserves current behaviour); when False the
dedicated scheduler process is the sole runner.
"""
from __future__ import annotations

import asyncio
import logging

import structlog

from app.core.config import settings


logger = structlog.get_logger("hirestack.scheduler.jobs")


async def periodic_stale_job_cleanup() -> None:
    """Sweep stale generation jobs + orphaned modules every 10 minutes."""
    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            from app.api.routes.generate import cleanup_stale_generation_jobs

            cleaned = await asyncio.wait_for(
                cleanup_stale_generation_jobs(), timeout=30
            )
            if cleaned:
                logger.info("Stale job cleanup completed", cleaned_count=cleaned)
            from app.api.routes.generate import cleanup_orphaned_generating_modules

            orphans = await asyncio.wait_for(
                cleanup_orphaned_generating_modules(), timeout=30
            )
            if orphans:
                logger.info(
                    "Orphaned module cleanup completed", cleaned_count=orphans
                )
        except asyncio.CancelledError:
            break
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Stale job cleanup error", error=str(e))


async def periodic_career_monitor_tick() -> None:
    """Proactive career scan loop — only scans users with active missions
    or enabled tracked companies, keeping cost bounded."""
    from app.services.career_monitor import AutonomousCareerMonitor

    interval_s = settings.career_monitor_interval_seconds
    batch_size = settings.career_monitor_user_batch_size
    initial_delay_s = min(60, max(10, interval_s // 6))
    await asyncio.sleep(initial_delay_s)

    while True:
        try:
            summary = await asyncio.wait_for(
                AutonomousCareerMonitor().run_scheduled_scan_batch(limit=batch_size),
                timeout=max(120, min(interval_s, 600)),
            )
            if summary.get("candidate_count"):
                logger.info(
                    "Background career monitor tick completed", **summary
                )
        except asyncio.CancelledError:
            break
        except Exception as e:  # pragma: no cover — defensive
            logger.warning(
                "Background career monitor tick failed", error=str(e)[:200]
            )

        try:
            await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            break
