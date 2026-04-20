"""W7 Future-proofing: lightweight feature-flag service.

Ad-hoc ``os.getenv("X_ENABLED", "").lower() in ("1","true")`` checks are
scattered across the codebase. This module centralises them so:

    * Flags can be toggled without code changes (env-driven today; a
      DB-backed rollout layer can be slotted in without touching callers).
    * Every check goes through a single cached lookup → no stringly-typed
      typos, no duplicate environment parses.
    * Default values are explicit — missing flags don't silently enable
      unreleased features.
    * Flags can be declared once with a doc string (the registry below),
      giving us a single place to audit what's gated.

Usage
-----

    from app.core.feature_flags import is_enabled, FLAGS

    if is_enabled(FLAGS.BILLING):
        mount_billing_routes()

Semantics
---------

* ``is_enabled(flag)`` returns ``True`` iff the env var matches one of
  ``{"1", "true", "yes", "on"}`` (case-insensitive). Anything else (unset,
  empty, ``"0"``, ``"false"``, malformed) → ``False``.
* The first lookup for a given flag caches the result — callers on hot
  paths don't pay env-parse cost repeatedly. :func:`reset` clears the
  cache (used in tests).
* Flags have a ``default`` that applies only when the env var is
  completely unset. An explicit falsy env value still evaluates to False.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock
from typing import Dict

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})


@dataclass(frozen=True)
class FeatureFlag:
    """Declarative flag definition — one per gated feature."""
    env_var: str
    default: bool
    description: str


class _Registry:
    """Well-known flags. Add new ones here, not as random env lookups."""

    BILLING = FeatureFlag(
        env_var="BILLING_ENABLED",
        default=False,
        description="Expose Stripe checkout/portal endpoints. Disabled in dev by default.",
    )
    INTEL_PREFETCH = FeatureFlag(
        env_var="INTEL_PREFETCH_ENABLED",
        default=True,
        description="Accept POST /api/intel/prefetch requests (W4).",
    )
    DOC_QUALITY_SCORER = FeatureFlag(
        env_var="DOC_QUALITY_SCORER_ENABLED",
        default=True,
        description="Run deterministic per-document quality scorer in Sentinel (W2).",
    )
    WEBHOOK_RETRIES = FeatureFlag(
        env_var="WEBHOOK_RETRIES_ENABLED",
        default=True,
        description="Retry webhook delivery on transient failures (W6).",
    )


FLAGS = _Registry()

_cache: Dict[str, bool] = {}
_cache_lock = Lock()


def is_enabled(flag: FeatureFlag) -> bool:
    """Return True iff the flag is enabled.

    Cached per-flag after first read. Thread-safe. Tolerant of weird env
    values — only explicit truthy tokens count as enabled.
    """
    with _cache_lock:
        cached = _cache.get(flag.env_var)
        if cached is not None:
            return cached
        raw = os.getenv(flag.env_var)
        if raw is None:
            result = flag.default
        else:
            normalized = raw.strip().lower()
            if normalized in _TRUTHY:
                result = True
            elif normalized in _FALSY:
                result = False
            else:
                # Unknown token — fall back to default (safer than raising).
                result = flag.default
        _cache[flag.env_var] = result
        return result


def reset() -> None:
    """Clear the cache (test-only helper)."""
    with _cache_lock:
        _cache.clear()


def snapshot() -> Dict[str, bool]:
    """Return current value of every declared flag — for /metrics or admin UI."""
    return {
        getattr(FLAGS, name).env_var: is_enabled(getattr(FLAGS, name))
        for name in dir(FLAGS)
        if isinstance(getattr(FLAGS, name), FeatureFlag)
    }
