"""Tests for ``app.scheduler.leader_lock`` (PR m2-pr6).

We never connect to a real Redis.  ``FakeAsyncRedis`` implements the
narrow surface LeaderLock requires (``set``, ``get``, ``eval``,
``delete``) so the lease semantics, ownership token, and refresh loop
can be verified in microseconds.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.scheduler.leader_lock import LeaderLock


class FakeAsyncRedis:
    """Minimal in-memory Redis stand-in supporting NX, EX, GET, DEL, EVAL."""

    def __init__(self) -> None:
        # value -> (raw_value, expires_at_or_None)
        self._store: dict[str, tuple[str, float | None]] = {}

    def _expired(self, key: str) -> bool:
        v = self._store.get(key)
        if v is None:
            return True
        _, exp = v
        return exp is not None and exp <= time.monotonic()

    async def set(self, key, value, nx=False, ex=None):
        if self._expired(key):
            self._store.pop(key, None)
        if nx and key in self._store:
            return None
        expires = time.monotonic() + ex if ex else None
        self._store[key] = (value, expires)
        return True

    async def get(self, key):
        if self._expired(key):
            self._store.pop(key, None)
            return None
        v = self._store.get(key)
        return v[0] if v else None

    async def delete(self, key):
        return 1 if self._store.pop(key, None) else 0

    async def eval(self, script, numkeys, *args):
        # We only support our release script: GET == ARGV[1] then DEL.
        key = args[0]
        expected = args[1]
        current = await self.get(key)
        if current == expected:
            await self.delete(key)
            return 1
        return 0


# ---------- construction guards --------------------------------------------


def test_lock_rejects_short_ttl():
    with pytest.raises(ValueError, match="ttl_seconds must be >= 5"):
        LeaderLock(FakeAsyncRedis(), "k", ttl_seconds=2)


def test_lock_owner_token_is_unique_per_instance():
    a = LeaderLock(FakeAsyncRedis(), "k")
    b = LeaderLock(FakeAsyncRedis(), "k")
    assert a.owner_token != b.owner_token


# ---------- lease behaviour ------------------------------------------------


@pytest.mark.asyncio
async def test_first_acquirer_wins():
    redis = FakeAsyncRedis()
    a = LeaderLock(redis, "leader", ttl_seconds=10)
    b = LeaderLock(redis, "leader", ttl_seconds=10)

    assert await a.acquire() is True
    assert a.is_leader

    assert await b.acquire() is False
    assert not b.is_leader

    await a.release()


@pytest.mark.asyncio
async def test_release_only_deletes_own_lock():
    """If a slow leader tries to release after a follower took over, the
    follower's key must NOT be deleted (Lua CAS prevents it)."""
    redis = FakeAsyncRedis()
    a = LeaderLock(redis, "leader", ttl_seconds=10)
    await a.acquire()

    # Manually overwrite the key as if a new leader took over.
    await redis.set("leader", "someone-else", ex=10)

    await a.release()  # should NOT remove the new leader's value
    assert await redis.get("leader") == "someone-else"


@pytest.mark.asyncio
async def test_lease_expires_when_holder_does_not_refresh():
    redis = FakeAsyncRedis()
    a = LeaderLock(
        redis,
        "leader",
        ttl_seconds=5,
        refresh_interval_seconds=10,  # no refresh inside the TTL window
    )
    await a.acquire()
    assert a.is_leader

    # Manually expire the underlying key to simulate timeout.
    redis._store["leader"] = (a.owner_token, time.monotonic() - 1)

    val = await redis.get("leader")
    assert val is None  # gone from Redis

    # Stop the refresh task (release tries to delete, but key is gone — fine).
    await a.release()


@pytest.mark.asyncio
async def test_refresh_loop_extends_lease():
    redis = FakeAsyncRedis()
    a = LeaderLock(
        redis,
        "leader",
        ttl_seconds=5,
        refresh_interval_seconds=0.05,
    )
    await a.acquire()

    # Wait long enough for at least one refresh.
    await asyncio.sleep(0.15)

    # Lease should still be alive (refresh kept extending it).
    assert await redis.get("leader") == a.owner_token
    assert a.is_leader

    await a.release()


@pytest.mark.asyncio
async def test_refresh_loop_detects_lost_leadership():
    """If something else overwrites the key, the refresh loop should
    notice and flip ``is_leader`` to False."""
    redis = FakeAsyncRedis()
    a = LeaderLock(
        redis,
        "leader",
        ttl_seconds=5,
        refresh_interval_seconds=0.02,
    )
    await a.acquire()
    assert a.is_leader

    await redis.set("leader", "imposter", ex=10)
    await asyncio.sleep(0.06)

    assert not a.is_leader
    await a.release()
    # Imposter's value untouched.
    assert await redis.get("leader") == "imposter"


@pytest.mark.asyncio
async def test_async_context_manager_releases_on_exit():
    redis = FakeAsyncRedis()
    async with LeaderLock(redis, "leader", ttl_seconds=10) as lock:
        assert lock.is_leader
    # Lock released → key gone.
    assert await redis.get("leader") is None
