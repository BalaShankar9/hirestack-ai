"""Batch scoring worker — parallel fan-out over a BatchPlan.

This is the slow side of the batch flow:

  plan_batch(urls)            ← B0.api: instant, pure-fn validation
       ↓ BatchPlan.accepted
  score_plan(...)             ← THIS MODULE: async parallel scoring
       ↓ Iterable[ScoringResult]
  rank_batch(results, min)    ← existing pure-fn bucket+sort
       ↓ RankedBatch
  persist (B0.persist next)   ← writes to applications

Why a separate module from `batch_evaluator`:
- batch_evaluator stays *pure* (sync, no I/O, trivially testable).
- All asyncio + concurrency caps + per-entry retry/error policy live
  here, mirroring the portal_scanner_worker pattern (B1.next).
- The actual scoring call is **injected** as a `Scorer` callable so
  tests never touch the AI router and prod can swap in either the
  rules-based scorer or the LLM chain without changing this glue.

The worker NEVER:
- Calls the AI router directly (Scorer is injected).
- Touches the database (B0.persist owns that).
- Raises on per-entry failures (failures become ScoringResult(error=...)
  so rank_batch can bucket them).
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Iterable, Optional, Sequence

from app.services.batch_evaluator import BatchEntry, ScoringResult


# ── concurrency knobs ────────────────────────────────────────────────

# AI scoring is token-bound, not connection-bound — keep the cap low
# so a single user's batch can't drain the rate-limit budget shared
# with interactive flows.  Tune up only after measuring p99 latency
# under load.
DEFAULT_CONCURRENCY = 4

# Hard ceiling regardless of caller request — prevents an over-eager
# caller from setting concurrency=1000 and starving the rest of the
# app.  Values above this are clamped silently (worker is a library,
# not a public API; the caller should validate at the boundary).
MAX_CONCURRENCY = 16


# ── Scorer protocol ──────────────────────────────────────────────────

# A Scorer takes a single accepted entry and returns a fully-formed
# ScoringResult.  It MUST NOT raise — any failure should be surfaced
# as ScoringResult(canonical_url=..., fit_score=None, error="...").
# We still defensively try/except below in case a Scorer breaks
# contract, but the docstring is the contract.
Scorer = Callable[[BatchEntry], Awaitable[ScoringResult]]


# ── public API ───────────────────────────────────────────────────────


async def score_plan(
    entries: Sequence[BatchEntry],
    *,
    scorer: Scorer,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> tuple[ScoringResult, ...]:
    """Fan out scoring across `entries` under a concurrency cap.

    * Order of returned results matches the order of `entries` so the
      UI can correlate row-by-row before rank_batch reshuffles.
    * Each entry is scored under a single semaphore slot; concurrency
      is clamped to [1, MAX_CONCURRENCY].
    * If `scorer` raises (contract violation), that entry yields a
      ScoringResult with error="scorer_bug" rather than crashing the
      whole batch — one bad URL shouldn't kill the other 11.
    * If the entire `score_plan` task is cancelled, CancelledError
      propagates (asyncio cleanup).  Per-entry CancelledError is also
      propagated (don't swallow cancellation inside the worker).
    """
    if not entries:
        return ()

    # Clamp concurrency at the boundary — never trust the caller.
    cap = max(1, min(int(concurrency), MAX_CONCURRENCY))
    sem = asyncio.Semaphore(cap)

    async def _score_one(entry: BatchEntry) -> ScoringResult:
        async with sem:
            try:
                result = await scorer(entry)
            except asyncio.CancelledError:
                # Never swallow cancellation — let asyncio unwind.
                raise
            except Exception as exc:  # pragma: no cover - defensive
                # Scorer broke its no-raise contract.  Surface as a
                # failure ScoringResult so rank_batch can bucket it
                # into `failed` instead of dropping the row entirely.
                return ScoringResult(
                    canonical_url=entry.canonical_url,
                    fit_score=None,
                    error=f"scorer_bug:{type(exc).__name__}",
                )
        # Defensive: a scorer might return None / wrong type.  Treat
        # those as failures rather than crashing rank_batch later.
        if not isinstance(result, ScoringResult):
            return ScoringResult(
                canonical_url=entry.canonical_url,
                fit_score=None,
                error="scorer_bad_return",
            )
        # Pin canonical_url to the entry's value — a buggy scorer that
        # returns a different URL would break correlation with the
        # original BatchPlan in B0.persist.
        if result.canonical_url != entry.canonical_url:
            return ScoringResult(
                canonical_url=entry.canonical_url,
                fit_score=result.fit_score,
                error=result.error or "scorer_url_mismatch",
                title=result.title,
                company=result.company,
            )
        return result

    results = await asyncio.gather(*(_score_one(e) for e in entries))
    return tuple(results)


__all__ = [
    "DEFAULT_CONCURRENCY",
    "MAX_CONCURRENCY",
    "Scorer",
    "score_plan",
]
