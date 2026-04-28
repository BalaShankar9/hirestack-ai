"""S1-F10: behavioral tests — cache layer extracted to app.core.cache.

Pins the contract:
  - Public cache functions live in app.core.cache.
  - app.core.database re-exports the same callables (back-compat).
  - In-memory fallback round-trips a value when Redis is absent.
  - cache_invalidate_prefix removes all matching in-mem keys.
"""
from __future__ import annotations

import importlib

import pytest


def test_cache_module_exposes_public_surface():
    cache = importlib.import_module("app.core.cache")
    for name in (
        "get_redis",
        "cache_get",
        "cache_set",
        "cache_invalidate",
        "cache_invalidate_prefix",
    ):
        assert hasattr(cache, name), f"app.core.cache must expose {name}"


def test_database_reexports_cache_callables_for_backcompat():
    cache = importlib.import_module("app.core.cache")
    db = importlib.import_module("app.core.database")
    for name in (
        "get_redis",
        "cache_get",
        "cache_set",
        "cache_invalidate",
        "cache_invalidate_prefix",
    ):
        assert getattr(db, name) is getattr(cache, name), (
            f"app.core.database.{name} must be the same object as "
            f"app.core.cache.{name}"
        )


@pytest.mark.asyncio
async def test_in_memory_fallback_round_trip(monkeypatch):
    from app.core import cache as cache_mod

    # Force the Redis path off so we exercise the in-memory LRU.
    monkeypatch.setattr(cache_mod, "get_redis", lambda: None)

    key = "test:f10:roundtrip"
    await cache_mod.cache_set(key, {"hello": "world"}, ttl=30)
    got = await cache_mod.cache_get(key)
    assert got == {"hello": "world"}

    await cache_mod.cache_invalidate(key)
    assert await cache_mod.cache_get(key) is None


@pytest.mark.asyncio
async def test_invalidate_prefix_clears_matching_in_mem_keys(monkeypatch):
    from app.core import cache as cache_mod

    monkeypatch.setattr(cache_mod, "get_redis", lambda: None)

    await cache_mod.cache_set("jobs:org-A:1", {"v": 1}, ttl=30)
    await cache_mod.cache_set("jobs:org-A:2", {"v": 2}, ttl=30)
    await cache_mod.cache_set("jobs:org-B:1", {"v": 3}, ttl=30)

    await cache_mod.cache_invalidate_prefix("jobs:org-A")

    assert await cache_mod.cache_get("jobs:org-A:1") is None
    assert await cache_mod.cache_get("jobs:org-A:2") is None
    # Sibling prefix is untouched.
    assert await cache_mod.cache_get("jobs:org-B:1") == {"v": 3}

    # Cleanup.
    await cache_mod.cache_invalidate_prefix("jobs:org-B")
