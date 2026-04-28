"""S1-F8: behavioral pin — SupabaseDB._run no longer serializes calls globally.

Background:
  Module-level singleton `_db_instance = SupabaseDB()` previously held an
  asyncio.Lock that wrapped *every* call to `_run`. Because every async
  DB call in the app routes through that one instance, the lock was
  forcing global serialization — a multi-tenant pipeline was running
  one Supabase round-trip at a time, regardless of asyncio concurrency.

  This test confirms that:
    1. SupabaseDB no longer carries a `_lock` attribute (gone, not just
       rebuilt).
    2. Two concurrent _run() calls on the SAME instance interleave —
       a slow call does NOT block a fast call started after it.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.core.database import SupabaseDB


def test_supabase_db_has_no_global_lock():
    """The _lock attribute must be gone — its mere presence is the bug."""
    db = SupabaseDB.__new__(SupabaseDB)  # bypass __init__ (avoids real client)
    db.client = None  # type: ignore[assignment]
    assert not hasattr(db, "_lock"), (
        "SupabaseDB._lock must not exist — it serializes every DB call "
        "across the entire app via the module singleton"
    )


@pytest.mark.asyncio
async def test_run_does_not_serialize_concurrent_calls():
    """Two concurrent _run() calls on one instance must overlap.

    With the old per-instance asyncio.Lock, the slow call would block
    the fast call. We start a slow call (sleeps 200ms in a worker thread)
    and a fast call (returns immediately) concurrently and assert the
    fast call finishes BEFORE the slow one — proving they are parallel.
    """
    db = SupabaseDB.__new__(SupabaseDB)
    db.client = None  # type: ignore[assignment]

    fast_done_at: list[float] = []
    slow_done_at: list[float] = []

    def _slow():
        time.sleep(0.2)
        return "slow"

    def _fast():
        return "fast"

    async def _run_slow():
        out = await db._run(_slow)
        slow_done_at.append(time.monotonic())
        return out

    async def _run_fast():
        # Start slightly later but sleep nothing — should finish first.
        await asyncio.sleep(0.01)
        out = await db._run(_fast)
        fast_done_at.append(time.monotonic())
        return out

    started = time.monotonic()
    results = await asyncio.gather(_run_slow(), _run_fast())
    total_elapsed = time.monotonic() - started

    assert results == ["slow", "fast"]
    # Fast call must complete before slow call.
    assert fast_done_at[0] < slow_done_at[0], (
        "fast call finished AFTER slow call — _run is still serializing"
    )
    # Total wall time must be ~0.2s, not ~0.4s (proves overlap).
    assert total_elapsed < 0.35, (
        f"total elapsed {total_elapsed:.3f}s suggests calls were serialized "
        "(expected near 0.2s, the slow call's sleep)"
    )
