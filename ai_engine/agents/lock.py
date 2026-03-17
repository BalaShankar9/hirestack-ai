"""
Pipeline concurrency control.

Prevents concurrent pipeline runs for the same (user_id, pipeline_name).
Uses in-memory asyncio.Lock per key with configurable timeout.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator


class PipelineLockManager:
    """One active pipeline per (user_id, pipeline_name)."""

    def __init__(self, timeout_seconds: float = 300.0):
        self._locks: dict[str, asyncio.Lock] = {}
        self._timeout = timeout_seconds

    def _key(self, user_id: str, pipeline_name: str) -> str:
        return f"{user_id}:{pipeline_name}"

    @asynccontextmanager
    async def acquire(
        self, user_id: str, pipeline_name: str, pipeline_id: str
    ) -> AsyncGenerator[None, None]:
        key = self._key(user_id, pipeline_name)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        lock = self._locks[key]
        await asyncio.wait_for(lock.acquire(), timeout=self._timeout)
        try:
            yield
        finally:
            lock.release()
            # Lock objects are small; skip cleanup to avoid race with queued waiters
