"""
Pipeline concurrency control.

Prevents concurrent pipeline runs for the same (user_id, pipeline_name).
Supports two strategies:
  1. In-memory asyncio.Lock — fast, single-process (default fallback)
  2. DB-advisory lock via Supabase table — distributed, multi-worker safe

The distributed lock stores a row with a heartbeat timestamp.
A lock is considered stale if the heartbeat hasn't been refreshed
within `stale_after_seconds`.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.lock")


class PipelineLockManager:
    """One active pipeline per (user_id, pipeline_name).

    Falls back to in-memory locking when no `db` is provided.
    When `db` is supplied, uses the `pipeline_locks` table for
    distributed advisory locking with heartbeat-based stale detection.
    """

    def __init__(
        self,
        timeout_seconds: float = 300.0,
        db: Any = None,
        table_name: str = "pipeline_locks",
        stale_after_seconds: float = 600.0,
    ):
        # In-memory fallback
        self._locks: dict[str, asyncio.Lock] = {}
        self._timeout = timeout_seconds
        # Distributed mode
        self._db = db
        self._table = table_name
        self._stale_after = stale_after_seconds

    def _key(self, user_id: str, pipeline_name: str) -> str:
        return f"{user_id}:{pipeline_name}"

    # ── Distributed lock (DB-based) ──────────────────────────────────

    async def _try_acquire_db(
        self, user_id: str, pipeline_name: str, pipeline_id: str,
    ) -> bool:
        """Attempt to acquire a distributed lock row.

        Returns True if acquired.  Cleans up stale locks automatically.
        """
        key = self._key(user_id, pipeline_name)
        now_iso = _now_iso()
        stale_cutoff = _seconds_ago_iso(self._stale_after)

        # 1. Delete stale locks (heartbeat older than cutoff)
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._table)
                .delete()
                .eq("lock_key", key)
                .lt("heartbeat_at", stale_cutoff)
                .execute()
            )
        except Exception:
            pass  # Best-effort cleanup

        # 2. Try to insert our lock row (unique constraint on lock_key)
        try:
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._table)
                .insert({
                    "lock_key": key,
                    "pipeline_id": pipeline_id,
                    "user_id": user_id,
                    "pipeline_name": pipeline_name,
                    "acquired_at": now_iso,
                    "heartbeat_at": now_iso,
                })
                .execute()
            )
            return bool(resp.data)
        except Exception:
            # Unique constraint violation → another worker holds the lock
            return False

    async def _release_db(self, user_id: str, pipeline_name: str, pipeline_id: str) -> None:
        key = self._key(user_id, pipeline_name)
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._table)
                .delete()
                .eq("lock_key", key)
                .eq("pipeline_id", pipeline_id)
                .execute()
            )
        except Exception as e:
            logger.warning("lock_release_failed", key=key, error=str(e))

    async def _heartbeat_db(self, user_id: str, pipeline_name: str, pipeline_id: str) -> None:
        key = self._key(user_id, pipeline_name)
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._table)
                .update({"heartbeat_at": _now_iso()})
                .eq("lock_key", key)
                .eq("pipeline_id", pipeline_id)
                .execute()
            )
        except Exception:
            pass

    # ── Main context manager ─────────────────────────────────────────

    @asynccontextmanager
    async def acquire(
        self, user_id: str, pipeline_name: str, pipeline_id: str,
    ) -> AsyncGenerator[None, None]:
        if not self._db:
            # Fallback: in-memory lock with cleanup of idle entries
            key = self._key(user_id, pipeline_name)
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            lock = self._locks[key]
            await asyncio.wait_for(lock.acquire(), timeout=self._timeout)
            try:
                yield
            finally:
                lock.release()
                # Cleanup: remove lock if nobody is waiting
                if not lock.locked():
                    self._locks.pop(key, None)
            return

        # Distributed: poll for lock acquisition with backoff
        deadline = time.monotonic() + self._timeout
        acquired = False
        heartbeat_task: Optional[asyncio.Task] = None
        try:
            backoff = 0.5
            while time.monotonic() < deadline:
                acquired = await self._try_acquire_db(user_id, pipeline_name, pipeline_id)
                if acquired:
                    break
                await asyncio.sleep(min(backoff, deadline - time.monotonic()))
                backoff = min(backoff * 1.5, 10.0)

            if not acquired:
                raise asyncio.TimeoutError(
                    f"Could not acquire distributed lock for {user_id}:{pipeline_name} "
                    f"within {self._timeout}s"
                )

            # Start heartbeat background task
            async def _heartbeat_loop():
                interval = max(self._stale_after / 3, 30.0)
                while True:
                    await asyncio.sleep(interval)
                    await self._heartbeat_db(user_id, pipeline_name, pipeline_id)

            heartbeat_task = asyncio.create_task(_heartbeat_loop())
            yield
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            if acquired:
                await self._release_db(user_id, pipeline_name, pipeline_id)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _seconds_ago_iso(seconds: float) -> str:
    from datetime import datetime, timezone, timedelta
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
