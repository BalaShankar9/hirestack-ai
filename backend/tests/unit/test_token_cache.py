"""S1-F5: tests for _TokenCache negative caching (DoS amplifier closed).

Pins five contracts on the auth-token cache:

  1. Positive cache: put() then get() returns the claims; expired (per JWT
     'exp') entries are dropped on next get().
  2. Negative cache: mark_bad() then is_known_bad() returns True until
     the negative TTL elapses, then returns False.
  3. mark_bad() is independent of the positive cache — adding a bad
     entry does NOT touch the positive store.
  4. put() of valid claims clears any negative entry for that token
     (a refreshed/reissued token must verify on its next request).
  5. invalidate() and clear() drop both positive and negative entries.

Pure in-memory test — no Supabase, no JWT decode, no event loop.
"""
from __future__ import annotations

import time

from app.core.database import _TokenCache


# ─────────────────────────────────────────────────────────────────────────────
# Positive cache (pre-existing behavior, pinned for safety)
# ─────────────────────────────────────────────────────────────────────────────

class TestPositiveCache:
    def test_put_then_get_returns_claims(self) -> None:
        cache = _TokenCache(max_size=4)
        token = "tok-good"
        claims = {"sub": "user-1", "exp": time.time() + 60}
        cache.put(token, claims)
        assert cache.get(token) == claims

    def test_expired_entry_dropped_on_get(self) -> None:
        cache = _TokenCache(max_size=4)
        token = "tok-expired"
        claims = {"sub": "user-1", "exp": time.time() - 1}  # already past
        cache.put(token, claims)
        assert cache.get(token) is None
        # Confirm internal eviction happened too
        assert cache.get(token) is None

    def test_lru_evicts_oldest(self) -> None:
        cache = _TokenCache(max_size=2)
        for i in range(3):
            cache.put(f"tok-{i}", {"sub": str(i), "exp": time.time() + 60})
        # tok-0 is oldest → evicted
        assert cache.get("tok-0") is None
        assert cache.get("tok-1") is not None
        assert cache.get("tok-2") is not None


# ─────────────────────────────────────────────────────────────────────────────
# Negative cache — the F5 deliverable
# ─────────────────────────────────────────────────────────────────────────────

class TestNegativeCache:
    def test_unknown_token_is_not_known_bad(self) -> None:
        cache = _TokenCache()
        assert cache.is_known_bad("never-seen") is False

    def test_mark_bad_then_is_known_bad_returns_true(self) -> None:
        cache = _TokenCache()
        cache.mark_bad("tok-bad")
        assert cache.is_known_bad("tok-bad") is True

    def test_negative_entry_expires_after_ttl(self) -> None:
        cache = _TokenCache(negative_ttl_s=0.05)
        cache.mark_bad("tok-bad")
        assert cache.is_known_bad("tok-bad") is True
        time.sleep(0.06)
        assert cache.is_known_bad("tok-bad") is False

    def test_mark_bad_does_not_populate_positive_cache(self) -> None:
        cache = _TokenCache()
        cache.mark_bad("tok-bad")
        assert cache.get("tok-bad") is None  # still nothing in positive store

    def test_negative_eviction_respects_max_size(self) -> None:
        cache = _TokenCache(negative_max_size=2)
        cache.mark_bad("a")
        cache.mark_bad("b")
        cache.mark_bad("c")  # evicts 'a' (oldest)
        assert cache.is_known_bad("a") is False
        assert cache.is_known_bad("b") is True
        assert cache.is_known_bad("c") is True


# ─────────────────────────────────────────────────────────────────────────────
# Cross-cache interaction
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossCache:
    def test_put_clears_existing_negative_entry(self) -> None:
        """A token previously rejected can later succeed (refresh/key-rotate)."""
        cache = _TokenCache()
        token = "tok-flip"
        cache.mark_bad(token)
        assert cache.is_known_bad(token) is True

        cache.put(token, {"sub": "user-1", "exp": time.time() + 60})
        assert cache.is_known_bad(token) is False
        assert cache.get(token) is not None

    def test_invalidate_drops_both_caches(self) -> None:
        cache = _TokenCache()
        token = "tok-x"
        cache.put(token, {"sub": "user-1", "exp": time.time() + 60})
        cache.mark_bad("tok-y")

        cache.invalidate(token)
        cache.invalidate("tok-y")
        assert cache.get(token) is None
        assert cache.is_known_bad("tok-y") is False

    def test_clear_drops_all_entries(self) -> None:
        cache = _TokenCache()
        cache.put("a", {"sub": "1", "exp": time.time() + 60})
        cache.mark_bad("b")
        cache.clear()
        assert cache.get("a") is None
        assert cache.is_known_bad("b") is False
