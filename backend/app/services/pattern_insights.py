"""A2.a — pattern_insights (pure-function analyzer).

Three insight sections that power /dashboard/insights:

  1. funnel — stage-to-stage conversion across the pipeline:
     applied → responded → interview → offer.  Each step exposes
     count + rate from prior stage + rate from top-of-funnel.

  2. score_outcome — fit_score × outcome scatter, plus aggregates:
     win-rate per score bucket (0-1, 1-2, 2-3, 3-4, 4-5) and a
     "score where win-rate crosses 50%" cutoff signal.  Tells the
     user "stop applying below X."

  3. archetype_performance — per-stable-archetype response /
     interview / offer rates, sorted desc by response_rate.

Each section is gated by ``MIN_OUTCOMES`` (5) so we never show
charts off three data points.  Below the floor we return
``InsufficientData`` with a hint about how many more outcomes the
user needs.

PURE: takes a list of ``ApplicationRecord`` (already loaded by the
API route — typically a SELECT joined with stable archetype tag) and
returns ``PatternInsights``.  No DB, no LLM, no time mocking.

Why split A2.a from A2.b: this slice owns the three quantitative
sections.  A2.b adds a blocker-frequency miner (free-text rejection
reason classifier) + a recommendations engine (rule-driven "do X
because Y") that read these results.  Splitting keeps charts
shippable independent of the recommender.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, Optional, Sequence

from app.models.application_status import canonicalize_for_analytics

# ── Tunables ─────────────────────────────────────────────────────────

MIN_OUTCOMES: int = 5            # min closed-out apps to render any section
MIN_PER_ARCHETYPE: int = 3       # min apps per archetype before reporting it
SCORE_BUCKET_EDGES: tuple[float, ...] = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
WIN_RATE_CUTOFF_THRESHOLD: float = 0.5  # "applying above this score wins ≥ 50%"

# Stage progression — order matters for funnel %-from-prior calc.
_FUNNEL_STAGES: tuple[str, ...] = ("applied", "responded", "interview", "offer")

# Outcome classification used by score_outcome.
# - "won"  = reached interview or offer
# - "lost" = rejected / discarded / skip
# - "open" = still in pipeline, excluded from win-rate denominators
_WON_BUCKETS: frozenset[str] = frozenset({"interview", "offer"})
_LOST_BUCKETS: frozenset[str] = frozenset({"rejected", "discarded", "skip"})


# ── Inputs ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ApplicationRecord:
    """One application as the analyzer needs it.

    The API route is responsible for hydrating this from the DB.
    ``status`` may be any value; it's normalized via
    ``canonicalize_for_analytics`` before counting.
    """
    application_id: str
    status: str
    fit_score: Optional[float] = None        # 0..5 if computed
    archetype_label: Optional[str] = None    # one of F2's 8 labels or None


# ── Output types ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class InsufficientData:
    have: int
    need: int
    reason: str = "min_outcomes_not_met"


@dataclass(frozen=True)
class FunnelStage:
    name: str           # one of _FUNNEL_STAGES
    count: int
    rate_from_prior: Optional[float]   # None for the first stage
    rate_from_top: Optional[float]     # None when top is 0 (impossible if rendered)


@dataclass(frozen=True)
class FunnelInsight:
    stages: tuple[FunnelStage, ...]
    total_outcomes: int


@dataclass(frozen=True)
class ScoreBucket:
    label: str          # e.g. "3.0–4.0"
    lower: float
    upper: float        # inclusive on the top bucket only
    won: int
    lost: int
    win_rate: Optional[float]   # None when (won+lost)==0


@dataclass(frozen=True)
class ScoreOutcomeInsight:
    buckets: tuple[ScoreBucket, ...]
    cutoff_score: Optional[float]   # lowest bucket lower with win_rate >= 0.5
    total_scored_outcomes: int


@dataclass(frozen=True)
class ArchetypeRow:
    label: str
    n: int
    response_rate: float        # responded+ / total
    interview_rate: float       # interview+ / total
    offer_rate: float           # offer / total


@dataclass(frozen=True)
class ArchetypePerformance:
    rows: tuple[ArchetypeRow, ...]
    excluded_for_low_n: tuple[str, ...]


@dataclass(frozen=True)
class PatternInsights:
    funnel: FunnelInsight | InsufficientData
    score_outcome: ScoreOutcomeInsight | InsufficientData
    archetype: ArchetypePerformance | InsufficientData
    total_applications: int
    total_outcomes: int


# ── Internal counters ────────────────────────────────────────────────


def _bucket(record: ApplicationRecord) -> Optional[str]:
    return canonicalize_for_analytics(record.status)


def _is_outcome(bucket: Optional[str]) -> bool:
    """Closed-out enough to count toward a denominator."""
    if bucket is None:
        return False
    return bucket in _WON_BUCKETS or bucket in _LOST_BUCKETS or bucket == "responded"


# ── Funnel ───────────────────────────────────────────────────────────


def _compute_funnel(records: Sequence[ApplicationRecord]) -> tuple[dict[str, int], int]:
    """Returns (stage_counts, total_outcomes).

    Funnel is monotonic-by-progression: an application that reached
    'offer' counts in every prior stage too.  This matches user
    intuition ("80 applied → 30 responded → 10 interviewed → 2 offers").

    ``total_outcomes`` is the count of applications that reached the
    top-of-funnel ('applied') — anything past draft/active/archived.
    The funnel renders as soon as the user has MIN_OUTCOMES applies;
    they don't need to wait for results.
    """
    counts = {s: 0 for s in _FUNNEL_STAGES}
    for r in records:
        b = _bucket(r)
        if b is None:
            continue
        # Anything that isn't a pre-application status counts as "applied".
        if b in {"draft", "active", "archived"}:
            continue
        counts["applied"] += 1
        if b in {"responded", "interview", "offer"}:
            counts["responded"] += 1
        if b in {"interview", "offer"}:
            counts["interview"] += 1
        if b == "offer":
            counts["offer"] += 1
    return counts, counts["applied"]


def _build_funnel(records: Sequence[ApplicationRecord]) -> FunnelInsight | InsufficientData:
    counts, total_outcomes = _compute_funnel(records)
    if total_outcomes < MIN_OUTCOMES:
        return InsufficientData(have=total_outcomes, need=MIN_OUTCOMES)
    top = counts["applied"]
    stages: list[FunnelStage] = []
    prev_count: Optional[int] = None
    for name in _FUNNEL_STAGES:
        c = counts[name]
        rate_prior: Optional[float] = None
        if prev_count is not None:
            rate_prior = (c / prev_count) if prev_count > 0 else 0.0
        rate_top: Optional[float] = (c / top) if top > 0 else None
        stages.append(FunnelStage(name=name, count=c, rate_from_prior=rate_prior, rate_from_top=rate_top))
        prev_count = c
    return FunnelInsight(stages=tuple(stages), total_outcomes=total_outcomes)


# ── Score × outcome ──────────────────────────────────────────────────


def _bucket_index(score: float) -> int:
    """Index into SCORE_BUCKET_EDGES for the lower edge of the bucket.

    Buckets are [edge_i, edge_{i+1}), with the final bucket inclusive
    on both ends so a perfect 5.0 lands somewhere.
    """
    if score >= SCORE_BUCKET_EDGES[-1]:
        return len(SCORE_BUCKET_EDGES) - 2
    for i in range(len(SCORE_BUCKET_EDGES) - 1):
        if SCORE_BUCKET_EDGES[i] <= score < SCORE_BUCKET_EDGES[i + 1]:
            return i
    return 0


def _build_score_outcome(
    records: Sequence[ApplicationRecord],
) -> ScoreOutcomeInsight | InsufficientData:
    won_per_bucket = [0] * (len(SCORE_BUCKET_EDGES) - 1)
    lost_per_bucket = [0] * (len(SCORE_BUCKET_EDGES) - 1)
    total = 0
    for r in records:
        if r.fit_score is None:
            continue
        if r.fit_score < SCORE_BUCKET_EDGES[0] or r.fit_score > SCORE_BUCKET_EDGES[-1]:
            continue
        b = _bucket(r)
        if b in _WON_BUCKETS:
            won_per_bucket[_bucket_index(r.fit_score)] += 1
            total += 1
        elif b in _LOST_BUCKETS:
            lost_per_bucket[_bucket_index(r.fit_score)] += 1
            total += 1
    if total < MIN_OUTCOMES:
        return InsufficientData(have=total, need=MIN_OUTCOMES)

    buckets: list[ScoreBucket] = []
    for i in range(len(SCORE_BUCKET_EDGES) - 1):
        lo = SCORE_BUCKET_EDGES[i]
        hi = SCORE_BUCKET_EDGES[i + 1]
        won = won_per_bucket[i]
        lost = lost_per_bucket[i]
        denom = won + lost
        rate: Optional[float] = (won / denom) if denom > 0 else None
        buckets.append(ScoreBucket(
            label=f"{lo:.1f}–{hi:.1f}",
            lower=lo,
            upper=hi,
            won=won,
            lost=lost,
            win_rate=rate,
        ))

    cutoff: Optional[float] = None
    for b in buckets:
        if b.win_rate is not None and b.win_rate >= WIN_RATE_CUTOFF_THRESHOLD:
            cutoff = b.lower
            break
    return ScoreOutcomeInsight(
        buckets=tuple(buckets),
        cutoff_score=cutoff,
        total_scored_outcomes=total,
    )


# ── Archetype performance ────────────────────────────────────────────


def _build_archetype(
    records: Sequence[ApplicationRecord],
) -> ArchetypePerformance | InsufficientData:
    by_label: dict[str, list[ApplicationRecord]] = {}
    total_outcomes = 0
    for r in records:
        if not r.archetype_label:
            continue
        b = _bucket(r)
        if b in {"draft", "active", "archived"}:
            continue  # not yet an outcome candidate
        by_label.setdefault(r.archetype_label, []).append(r)
        total_outcomes += 1
    if total_outcomes < MIN_OUTCOMES:
        return InsufficientData(have=total_outcomes, need=MIN_OUTCOMES)

    rows: list[ArchetypeRow] = []
    excluded: list[str] = []
    for label in sorted(by_label):
        group = by_label[label]
        n = len(group)
        if n < MIN_PER_ARCHETYPE:
            excluded.append(label)
            continue
        responded_plus = sum(
            1 for r in group if _bucket(r) in {"responded", "interview", "offer"}
        )
        interview_plus = sum(1 for r in group if _bucket(r) in {"interview", "offer"})
        offer_count = sum(1 for r in group if _bucket(r) == "offer")
        rows.append(ArchetypeRow(
            label=label,
            n=n,
            response_rate=responded_plus / n,
            interview_rate=interview_plus / n,
            offer_rate=offer_count / n,
        ))
    rows.sort(key=lambda x: (-x.response_rate, x.label))
    return ArchetypePerformance(rows=tuple(rows), excluded_for_low_n=tuple(sorted(excluded)))


# ── Public entry point ───────────────────────────────────────────────


def compute_pattern_insights(records: Iterable[ApplicationRecord]) -> PatternInsights:
    """Build all three insight sections from a collection of applications."""
    records_list = tuple(records)
    total_apps = len(records_list)
    _, total_outcomes = _compute_funnel(records_list)
    return PatternInsights(
        funnel=_build_funnel(records_list),
        score_outcome=_build_score_outcome(records_list),
        archetype=_build_archetype(records_list),
        total_applications=total_apps,
        total_outcomes=total_outcomes,
    )


__all__ = [
    "MIN_OUTCOMES", "MIN_PER_ARCHETYPE", "SCORE_BUCKET_EDGES",
    "WIN_RATE_CUTOFF_THRESHOLD",
    "ApplicationRecord",
    "InsufficientData",
    "FunnelStage", "FunnelInsight",
    "ScoreBucket", "ScoreOutcomeInsight",
    "ArchetypeRow", "ArchetypePerformance",
    "PatternInsights",
    "compute_pattern_insights",
]
