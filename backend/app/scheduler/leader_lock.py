"""Redis-backed leader lock for the scheduler process.

Implements the classic ``SET key value NX EX <ttl>`` lease pattern with a
background refresh loop so a healthy leader keeps the lock indefinitely
while a crashed leader's lease expires within ``ttl`` seconds, allowing
a follower to take over.

Why this and not Redlock?  HireStack runs a single Redis (Railway add-on)
so the simpler single-instance lease is correct.  If we move to Redis
Cluster / multi-region, swap the lock impl and keep this interface.

Contract:

  >>> async with LeaderLock(client, "hirestack:scheduler:leader",
  ...                       ttl_seconds=30) as lock:
  ...     if lock.is_leader:
  ...         await run_periodic_jobs()

Test seam: the ``client`` parameter is duck-typed — anything with
async ``set``, ``get``, ``delete``, and ``eval`` works.  Tests use
``FakeRedis`` to avoid network.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from typing import Optional


logger = logging.getLogger("hirestack.scheduler.leader_lock")


# Lua script: only delete the key if its value still matches our owner
# token.  Prevents a slow-leader from deleting the new leader's lock.
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


def _default_owner_token() -> str:
    """Stable-per-process identifier embedded in the lock value."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class LeaderLock:
    """Async context manager wrapping a Redis SET NX EX lease."""

    def __init__(
        self,
        client,
        key: str,
        ttl_seconds: int = 30,
        refresh_interval_seconds: Optional[float] = None,
        owner_token: Optional[str] = None,
    ) -> None:
        if ttl_seconds < 5:
            raise ValueError("ttl_seconds must be >= 5 to leave headroom for refresh")
        self._client = client
        self._key = key
        self._ttl = ttl_seconds
        self._refresh_every = refresh_interval_seconds or max(2.0, ttl_seconds / 3)
        self._owner = owner_token or _default_owner_token()
        self._is_leader = False
        self._refresh_task: Optional[asyncio.Task] = None

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    @property
    def owner_token(self) -> str:
        return self._owner

    async def acquire(self) -> bool:
        """Try to acquire the lock once. Returns True on success."""
        ok = await self._client.set(
            self._key, self._owner, nx=True, ex=self._ttl
        )
        self._is_leader = bool(ok)
        if self._is_leader:
            logger.info(
                "leader_lock.acquired",
                extra={"key": self._key, "owner": self._owner, "ttl": self._ttl},
            )
            self._refresh_task = asyncio.create_task(self._refresh_loop())
        return self._is_leader

    async def release(self) -> None:
        """Release the lock if we still own it; cancel refresher."""
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except (asyncio.CancelledError, Exception):
                pass
            self._refresh_task = None
        if self._is_leader:
            try:
                await self._client.eval(
                    _RELEASE_SCRIPT, 1, self._key, self._owner
                )
            except Exception as exc:  # pragma: no cover — best-effort cleanup
                logger.warning(
                    "leader_lock.release_failed",
                    extra={"key": self._key, "error": str(exc)[:120]},
                )
            self._is_leader = False

    async def _refresh_loop(self) -> None:
        """Periodically extend the lease while we still hold it."""
        try:
            while self._is_leader:
                await asyncio.sleep(self._refresh_every)
                # Only extend if the key still belongs to us.
                current = await self._client.get(self._key)
                if isinstance(current, bytes):
                    current = current.decode()
                if current != self._owner:
                    logger.warning(
                        "leader_lock.lost",
                        extra={"key": self._key, "owner": self._owner},
                    )
                    self._is_leader = False
                    return
                # Re-set with same TTL.  We use SET (no NX) since we own it.
                await self._client.set(self._key, self._owner, ex=self._ttl)
        except asyncio.CancelledError:
            raise

    # Async context manager sugar.
    async def __aenter__(self) -> "LeaderLock":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()
