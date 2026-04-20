"""
JobWatchdog — periodic reconciler that catches stalled generation jobs.

Why this exists:
  The legacy `_periodic_stale_job_cleanup` task runs every 10 minutes and
  uses age-based heuristics. That's too coarse for a real-time pipeline
  where users watch progress live. The watchdog runs on a 30s tick and
  asks a sharper question: *has this job emitted any event recently?*

  If a job is in `running` state but its `generation_jobs.updated_at`
  hasn't moved in `STALL_SECONDS`, the pipeline is dead — usually a
  process crash or an unhandled async exception. The watchdog flips the
  job to `error` with a clear message so the UI stops spinning forever.

This is intentionally separate from the cleanup loop: cleanup is about
hygiene, the watchdog is about liveness.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# Tunables — exported for the watchdog smoke test.
TICK_SECONDS = 30
STALL_SECONDS = 120


class JobWatchdog:
    """Background task that flags stalled generation jobs."""

    def __init__(
        self,
        db: Any,
        tables: Dict[str, str],
        *,
        tick_seconds: int = TICK_SECONDS,
        stall_seconds: int = STALL_SECONDS,
    ) -> None:
        self._db = db
        self._tables = tables
        self._tick = max(5, int(tick_seconds))
        self._stall = max(30, int(stall_seconds))
        self._task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> asyncio.Task[None]:
        if self._task and not self._task.done():
            return self._task
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="job-watchdog")
        logger.info("job_watchdog.started",
                    tick_s=self._tick, stall_s=self._stall)
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    # ── tick loop ────────────────────────────────────────────────────

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick)
                break  # stop signaled
            except asyncio.TimeoutError:
                pass

            try:
                stalled = await self.scan_once()
                if stalled:
                    logger.warning("job_watchdog.stalled_jobs_flagged",
                                   count=len(stalled),
                                   ids=[j.get("id") for j in stalled])
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.warning("job_watchdog.tick_failed", error=str(ex)[:200])

    async def scan_once(self) -> List[Dict[str, Any]]:
        """One reconciliation pass. Returns rows that were flagged stalled."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._stall)
        cutoff_iso = cutoff.isoformat()

        running = await self._fetch_running_before(cutoff_iso)
        if not running:
            return []

        flagged: List[Dict[str, Any]] = []
        for row in running:
            job_id = row.get("id")
            if not job_id:
                continue
            ok = await self._mark_failed(
                job_id=str(job_id),
                error_message=(
                    f"Job stalled — no updates for >{self._stall}s. "
                    "Reconciled by JobWatchdog."
                ),
            )
            if ok:
                flagged.append(row)
        return flagged

    # ── DB helpers ───────────────────────────────────────────────────

    async def _fetch_running_before(self, cutoff_iso: str) -> List[Dict[str, Any]]:
        try:
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_jobs"])
                .select("id,user_id,application_id,status,updated_at,phase,progress")
                .eq("status", "running")
                .lt("updated_at", cutoff_iso)
                .limit(50)
                .execute()
            )
            return list(resp.data or [])
        except Exception as ex:
            logger.warning("job_watchdog.fetch_failed", error=str(ex)[:200])
            return []

    async def _mark_failed(self, *, job_id: str, error_message: str) -> bool:
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_jobs"])
                .update({
                    "status": "failed",
                    "error_message": error_message,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", job_id)
                .eq("status", "running")     # idempotent — only flip if still running
                .execute()
            )
            logger.info("job_watchdog.marked_failed", job_id=job_id)
            return True
        except Exception as ex:
            logger.warning("job_watchdog.mark_failed_error",
                           job_id=job_id, error=str(ex)[:200])
            return False
