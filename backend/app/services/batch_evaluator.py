"""B0 — batch_evaluator (pure-function core).

POST /api/generate/batch will take ≤25 URLs, run the scoring-only
pipeline in parallel, and return a ranked table.  This module owns
the *pure* halves of that flow:

  1. ``plan_batch(urls)`` — input validator.  Caps at 25, normalizes
     each URL via ``canonicalize_url``, drops duplicates (canonical-
     URL-equivalent), tags each entry with the ATS key when one is
     extractable, and reports rejects with reasons.  The caller (the
     API route) gets back a ``BatchPlan`` it can persist before
     dispatching parallel scorers.

  2. ``rank_batch(scored, *, min_fit_score)`` — output ranker.  Given
     the per-URL scoring results coming back from the parallel
     workers, sorts by ``fit_score`` desc (deterministic tie-break by
     canonical URL), drops anything below ``min_fit_score``, and
     splits scoring failures into a ``failed`` bucket so the UI can
     show them separately rather than silently dropping them.

PURE: no HTTP, no DB, no LLM calls.  The Celery worker that fans out
``ScoringTask`` → ``ScoringResult`` lives in the next slice; this
module is the contract between API and worker.

HARD RULES:
  * MAX_URLS = 25 enforced at the entry point.  Caller may surface a
    400 to the user.
  * min_fit_score in [0.0, 5.0] (matches missions.min_fit_score
    constraint in §3.6 / §13.6).
  * Empty/whitespace URLs are rejects, not silent drops.
  * Canonical-URL dedup is the *only* dedup signal — different URL
    representations of the same posting must collapse.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Sequence

from app.services.url_canonicalizer import canonicalize_url, extract_ats_key

# ── Constants ────────────────────────────────────────────────────────

MAX_URLS: int = 25
MIN_FIT_SCORE_FLOOR: float = 0.0
MIN_FIT_SCORE_CEIL: float = 5.0

RejectReason = Literal[
    "empty",
    "invalid_url",
    "duplicate",
    "over_cap",
]


# ── Types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BatchEntry:
    """One accepted URL in the batch.

    ``ats_key`` is set when ``extract_ats_key`` recognizes the URL
    (greenhouse/lever/ashby/workday/workable/smartrecruiters); else
    None — the worker still scores the page, it just lacks structured
    metadata.
    """
    raw_url: str
    canonical_url: str
    ats_key: Optional[tuple[str, str, str]]  # (platform, company, job_id)


@dataclass(frozen=True)
class BatchReject:
    raw_url: str
    reason: RejectReason


@dataclass(frozen=True)
class BatchPlan:
    """Validated batch ready to dispatch to parallel scorers."""
    accepted: tuple[BatchEntry, ...]
    rejected: tuple[BatchReject, ...]

    @property
    def is_empty(self) -> bool:
        return not self.accepted


@dataclass(frozen=True)
class ScoringResult:
    """Per-URL output coming back from the worker.

    ``error`` is set when scoring failed; ``fit_score`` may be None in
    that case.  ``error`` and a real ``fit_score`` are mutually
    exclusive — ``rank_batch`` enforces that by routing failures to
    the ``failed`` bucket regardless of any score that snuck through.
    """
    canonical_url: str
    fit_score: Optional[float]      # 0.0 .. 5.0 when present
    error: Optional[str] = None     # short failure code for UI
    title: Optional[str] = None
    company: Optional[str] = None


@dataclass(frozen=True)
class RankedBatch:
    """Ranked + bucketed scoring output for the UI."""
    ranked: tuple[ScoringResult, ...]    # passed min_fit_score, sorted desc
    below_threshold: tuple[ScoringResult, ...]  # scored OK but under floor
    failed: tuple[ScoringResult, ...]    # scoring errored out


# ── plan_batch ───────────────────────────────────────────────────────


def _looks_like_url(raw: str) -> bool:
    s = raw.strip()
    if not s:
        return False
    return s.lower().startswith(("http://", "https://"))


def plan_batch(urls: Sequence[str]) -> BatchPlan:
    """Validate, canonicalize, and dedupe a batch of URLs.

    * Anything past index ``MAX_URLS-1`` is rejected with reason
      ``over_cap`` (so the user sees *which* URLs got cut, not just
      "too many").
    * Empty / whitespace-only strings → reject ``empty``.
    * Strings that don't begin with http(s) → reject ``invalid_url``.
    * Two URLs collapsing to the same ``canonicalize_url`` keep the
      first; the rest become reject ``duplicate``.
    """
    accepted: list[BatchEntry] = []
    rejected: list[BatchReject] = []
    seen_canonicals: set[str] = set()

    for idx, raw in enumerate(urls):
        # Defensively coerce — caller may pass non-strings via JSON.
        raw_str = raw if isinstance(raw, str) else str(raw or "")
        if idx >= MAX_URLS:
            rejected.append(BatchReject(raw_url=raw_str, reason="over_cap"))
            continue
        if not raw_str.strip():
            rejected.append(BatchReject(raw_url=raw_str, reason="empty"))
            continue
        if not _looks_like_url(raw_str):
            rejected.append(BatchReject(raw_url=raw_str, reason="invalid_url"))
            continue
        try:
            canonical = canonicalize_url(raw_str)
        except Exception:
            # canonicalize_url is conservative but never trust 3rd-party
            # parsers — surface as invalid_url rather than crashing.
            rejected.append(BatchReject(raw_url=raw_str, reason="invalid_url"))
            continue
        if not canonical:
            rejected.append(BatchReject(raw_url=raw_str, reason="invalid_url"))
            continue
        if canonical in seen_canonicals:
            rejected.append(BatchReject(raw_url=raw_str, reason="duplicate"))
            continue
        seen_canonicals.add(canonical)
        accepted.append(BatchEntry(
            raw_url=raw_str,
            canonical_url=canonical,
            ats_key=extract_ats_key(raw_str),
        ))

    return BatchPlan(accepted=tuple(accepted), rejected=tuple(rejected))


# ── rank_batch ───────────────────────────────────────────────────────


def _validate_threshold(min_fit_score: float) -> float:
    if min_fit_score is None:
        return MIN_FIT_SCORE_FLOOR
    try:
        v = float(min_fit_score)
    except (TypeError, ValueError):
        raise ValueError(f"min_fit_score must be a number, got {min_fit_score!r}")
    if v < MIN_FIT_SCORE_FLOOR or v > MIN_FIT_SCORE_CEIL:
        raise ValueError(
            f"min_fit_score must be in [{MIN_FIT_SCORE_FLOOR}, {MIN_FIT_SCORE_CEIL}]"
        )
    return v


def rank_batch(
    scored: Iterable[ScoringResult],
    *,
    min_fit_score: float = MIN_FIT_SCORE_FLOOR,
) -> RankedBatch:
    """Bucket and sort scoring results.

    Buckets:
      * ``failed`` — any result with non-None ``error`` (regardless of
        whether ``fit_score`` is set).  Original order preserved.
      * ``below_threshold`` — scored OK but ``fit_score < min_fit_score``.
        Sorted desc by score (so the UI can show "almost made it").
      * ``ranked`` — scored OK and ``fit_score >= min_fit_score``.
        Sorted desc by score; ties broken by canonical_url asc for
        determinism.

    Results with ``fit_score is None`` and no ``error`` are treated as
    failures (defensive: shouldn't happen, but better than crashing).
    """
    threshold = _validate_threshold(min_fit_score)

    failed: list[ScoringResult] = []
    passing: list[ScoringResult] = []
    below: list[ScoringResult] = []

    for r in scored:
        if r.error or r.fit_score is None:
            failed.append(r)
            continue
        if r.fit_score < threshold:
            below.append(r)
        else:
            passing.append(r)

    passing.sort(key=lambda x: (-(x.fit_score or 0.0), x.canonical_url))
    below.sort(key=lambda x: (-(x.fit_score or 0.0), x.canonical_url))

    return RankedBatch(
        ranked=tuple(passing),
        below_threshold=tuple(below),
        failed=tuple(failed),
    )


__all__ = [
    "MAX_URLS", "MIN_FIT_SCORE_FLOOR", "MIN_FIT_SCORE_CEIL",
    "RejectReason",
    "BatchEntry", "BatchReject", "BatchPlan",
    "ScoringResult", "RankedBatch",
    "plan_batch", "rank_batch",
]
