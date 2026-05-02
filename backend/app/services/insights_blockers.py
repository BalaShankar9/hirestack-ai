"""A2.b — blockers + recommendations (pure-function).

Two related concerns split for clarity:

  1. ``classify_blockers(records)`` — mines rejection_reason free-text
     from rejected/discarded applications, classifying each into one
     of 8 deterministic buckets via keyword regex tables. Returns
     per-bucket counts + sample reason snippets + total / classified
     / unclassified counts. Falls back to "ghosted" when there's no
     reason text (the silent-rejection case is itself a signal).

  2. ``build_recommendations(insights, blockers)`` — rule-driven
     recommender that reads A2.a's ``PatternInsights`` + the
     ``BlockerReport`` and emits a tuple of ``Recommendation``
     records sorted by severity. Each rule has its own min-data
     gate so we don't recommend off three data points.

Why no LLM: classification rules are deterministic and the dataset
is the user's own, so a keyword table is more honest than a
hallucinated reason. A2.b stays pure for the same reason A2.a does
— the chart route just hydrates DB rows and asks for a verdict.

Severity ordering (high → low): ``critical`` (funnel collapse,
applying-below-cutoff waste), ``warn`` (single dominant blocker,
archetype concentration), ``info`` (story-bank suggestions, voice
suggestions). The /dashboard/insights page renders critical at top.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Sequence

from app.models.application_status import canonicalize_for_analytics
from app.services.pattern_insights import (
    ArchetypePerformance,
    FunnelInsight,
    InsufficientData,
    PatternInsights,
    ScoreOutcomeInsight,
)

# ── Tunables ─────────────────────────────────────────────────────────

MIN_BLOCKER_OUTCOMES: int = 5     # min rejected/discarded with reason text
MIN_DOMINANT_SHARE: float = 0.30  # one blocker ≥ 30% triggers a 'warn' rec
MIN_FUNNEL_DROP_RATE: float = 0.85  # ≥85% drop at any stage triggers 'critical'
MIN_BELOW_CUTOFF_SHARE: float = 0.40  # ≥40% applies below cutoff → 'critical'
MAX_REASON_SNIPPET_LEN: int = 120
MAX_SAMPLES_PER_BLOCKER: int = 3

BlockerCategory = Literal[
    "under_qualified",
    "over_qualified",
    "location_mismatch",
    "visa_sponsorship",
    "salary_mismatch",
    "timing_filled",
    "skills_gap",
    "ghosted",
    "other",
]

Severity = Literal["critical", "warn", "info"]


# Order matters — first match wins. Most specific patterns first.
_BLOCKER_PATTERNS: tuple[tuple[BlockerCategory, re.Pattern[str]], ...] = (
    ("over_qualified", re.compile(
        r"\b(over[\s-]?qualified|too\s+(senior|experienced)|"
        r"someone\s+with\s+(less|fewer))\b", re.IGNORECASE)),
    ("under_qualified", re.compile(
        r"\b(under[\s-]?qualified|not\s+enough\s+experience|"
        r"more\s+(years?|seniority|senior)|"
        r"(?:more|someone)\s+senior|"
        r"\d+\+?\s+years?\s+(?:of\s+)?experience|"
        r"looking\s+for\s+(senior|staff|principal|lead)|"
        r"need\s+(more|additional)\s+experience|junior)\b", re.IGNORECASE)),
    ("visa_sponsorship", re.compile(
        r"\b(visa|sponsor(?:ship)?|work\s+(?:auth(?:orization)?|permit)|"
        r"h-?1b|right\s+to\s+work|citizen(?:ship)?\s+required)\b", re.IGNORECASE)),
    ("location_mismatch", re.compile(
        r"\b(reloc(?:ate|ation)|on[\s-]?site|in[\s-]?(?:office|person)|"
        r"hybrid|remote\s+(?:not|isn't)|local\s+candidates?|time[\s-]?zone|"
        r"based\s+in)\b", re.IGNORECASE)),
    ("salary_mismatch", re.compile(
        r"\b(salary|compensation|comp(?:ensation)?|budget|pay\s+range|"
        r"out\s+of\s+(?:range|budget))\b", re.IGNORECASE)),
    ("timing_filled", re.compile(
        r"\b(position\s+(?:has\s+been\s+)?filled|role\s+(?:has\s+been\s+)?filled|"
        r"filled\s+internally|no\s+longer\s+(?:available|open|active)|"
        r"on\s+hold|paused|frozen|hiring\s+freeze|decided\s+to\s+pursue)\b",
        re.IGNORECASE)),
    ("skills_gap", re.compile(
        r"\b(skill\s+gap|missing\s+(?:skill|requirement)|tech\s+stack|"
        r"specific\s+(?:experience|knowledge|background)|not\s+a\s+match|"
        r"better\s+(?:match|fit))\b", re.IGNORECASE)),
)


# ── Inputs ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RejectedApplication:
    """Minimal shape needed to mine blockers from a rejection."""
    application_id: str
    status: str                       # rejected / discarded / withdrawn / etc.
    rejection_reason: Optional[str] = None


# ── Output types ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class BlockerCount:
    category: BlockerCategory
    count: int
    share: float                       # count / classified
    samples: tuple[str, ...]           # up to MAX_SAMPLES_PER_BLOCKER snippets


@dataclass(frozen=True)
class BlockerReport:
    counts: tuple[BlockerCount, ...]   # sorted desc by count
    total_rejected: int                # all rejected/discarded outcomes
    total_with_reason: int             # had non-empty rejection_reason
    classified: int                    # had reason AND matched a pattern
    sufficient: bool                   # total_rejected >= MIN_BLOCKER_OUTCOMES


@dataclass(frozen=True)
class Recommendation:
    code: str                          # stable id e.g. "below_cutoff_waste"
    severity: Severity
    title: str                         # short human-readable
    body: str                          # one paragraph rationale
    metric: Optional[str] = None       # the number that triggered it (display)


# ── Blocker classifier ──────────────────────────────────────────────


def _is_rejection_status(status: str) -> bool:
    """Treat all closed-out negative statuses as candidates for mining."""
    bucket = canonicalize_for_analytics(status)
    return bucket in {"rejected", "discarded"}


def _classify_reason(text: str) -> BlockerCategory:
    for category, pattern in _BLOCKER_PATTERNS:
        if pattern.search(text):
            return category
    return "other"


def _snippet(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= MAX_REASON_SNIPPET_LEN:
        return cleaned
    return cleaned[: MAX_REASON_SNIPPET_LEN - 1].rstrip() + "…"


def classify_blockers(records: Iterable[RejectedApplication]) -> BlockerReport:
    """Mine free-text rejection reasons into stable blocker buckets.

    Records without a reason map to ``ghosted``; records with a
    reason that no pattern catches map to ``other``. Both are
    counted in the classified denominator so shares sum to 1.0.
    """
    records_list = tuple(records)
    rejected = [r for r in records_list if _is_rejection_status(r.status)]
    total_rejected = len(rejected)

    bucket_counts: dict[BlockerCategory, int] = {}
    bucket_samples: dict[BlockerCategory, list[str]] = {}
    total_with_reason = 0

    for r in rejected:
        text = (r.rejection_reason or "").strip()
        if text:
            total_with_reason += 1
            category: BlockerCategory = _classify_reason(text)
            sample = _snippet(text)
        else:
            category = "ghosted"
            sample = ""
        bucket_counts[category] = bucket_counts.get(category, 0) + 1
        if sample and len(bucket_samples.setdefault(category, [])) < MAX_SAMPLES_PER_BLOCKER:
            bucket_samples[category].append(sample)

    classified = total_rejected
    counts: list[BlockerCount] = []
    for category, count in bucket_counts.items():
        share = (count / classified) if classified else 0.0
        counts.append(BlockerCount(
            category=category,
            count=count,
            share=share,
            samples=tuple(bucket_samples.get(category, ())),
        ))
    # Sort: count desc, then category name for determinism.
    counts.sort(key=lambda b: (-b.count, b.category))

    return BlockerReport(
        counts=tuple(counts),
        total_rejected=total_rejected,
        total_with_reason=total_with_reason,
        classified=classified,
        sufficient=total_rejected >= MIN_BLOCKER_OUTCOMES,
    )


# ── Recommendation rules ────────────────────────────────────────────


def _rate(stage_count: int, top_count: int) -> Optional[float]:
    if top_count <= 0:
        return None
    return stage_count / top_count


def _funnel_collapse_rec(funnel: FunnelInsight) -> Optional[Recommendation]:
    """Critical when a single stage drops ≥ MIN_FUNNEL_DROP_RATE from prior."""
    stages = funnel.stages
    for i in range(1, len(stages)):
        prior = stages[i - 1]
        cur = stages[i]
        if prior.count == 0:
            continue
        drop = 1.0 - (cur.count / prior.count)
        if drop >= MIN_FUNNEL_DROP_RATE:
            pct = int(round(drop * 100))
            return Recommendation(
                code=f"funnel_collapse_{prior.name}_to_{cur.name}",
                severity="critical",
                title=f"{pct}% drop between {prior.name} and {cur.name}",
                body=(
                    f"Only {cur.count} of {prior.count} applications that reached "
                    f"'{prior.name}' moved to '{cur.name}'. This is your single "
                    "biggest leak — focus the next iteration here."
                ),
                metric=f"{cur.count}/{prior.count}",
            )
    return None


def _below_cutoff_rec(score: ScoreOutcomeInsight) -> Optional[Recommendation]:
    """Critical when ≥ MIN_BELOW_CUTOFF_SHARE of scored apps land below cutoff."""
    if score.cutoff_score is None:
        return None
    below = sum(b.won + b.lost for b in score.buckets if b.upper <= score.cutoff_score)
    total = score.total_scored_outcomes
    if total == 0:
        return None
    share = below / total
    if share < MIN_BELOW_CUTOFF_SHARE:
        return None
    pct = int(round(share * 100))
    return Recommendation(
        code="below_cutoff_waste",
        severity="critical",
        title=f"Stop applying below fit_score {score.cutoff_score:.1f}",
        body=(
            f"{pct}% of your scored applications are below the win-rate "
            f"cutoff of {score.cutoff_score:.1f}. Setting a hard floor here "
            "would reclaim that effort for higher-fit roles."
        ),
        metric=f"{below}/{total}",
    )


def _dominant_blocker_rec(blockers: BlockerReport) -> Optional[Recommendation]:
    """Warn when one blocker category owns ≥ MIN_DOMINANT_SHARE of rejections."""
    if not blockers.sufficient or not blockers.counts:
        return None
    top = blockers.counts[0]
    if top.share < MIN_DOMINANT_SHARE:
        return None
    pct = int(round(top.share * 100))
    title_map: dict[BlockerCategory, str] = {
        "under_qualified": "Under-qualified is your top rejection reason",
        "over_qualified": "Over-qualified is your top rejection reason",
        "location_mismatch": "Location is your top rejection reason",
        "visa_sponsorship": "Sponsorship is your top rejection reason",
        "salary_mismatch": "Salary mismatch is your top rejection reason",
        "timing_filled": "Roles filling before you respond is your top blocker",
        "skills_gap": "Specific skills gap is your top rejection reason",
        "ghosted": "Most of your rejections are silent (no reason given)",
        "other": "Most rejections don't fit a known category",
    }
    body_map: dict[BlockerCategory, str] = {
        "under_qualified": "Adjust seniority targeting or strengthen the experience signal in your CV.",
        "over_qualified": "Consider applying to roles one level above your current targets.",
        "location_mismatch": "Tighten your location filters or add a relocation/remote signal upfront.",
        "visa_sponsorship": "Filter scanner targets to companies known to sponsor.",
        "salary_mismatch": "List a tighter expected band on outreach to pre-qualify before interview.",
        "timing_filled": "Ship faster — auto-prep + cadence will get you in earlier next time.",
        "skills_gap": "Use the Story Bank to surface adjacent skills more aggressively.",
        "ghosted": "Try follow-ups 3 and 7 days after submission; ghost-check before applying next time.",
        "other": "Tag rejections with a category to surface a clearer pattern.",
    }
    return Recommendation(
        code=f"dominant_blocker_{top.category}",
        severity="warn",
        title=title_map[top.category],
        body=f"{pct}% of your rejections are tagged '{top.category}'. " + body_map[top.category],
        metric=f"{top.count}/{blockers.classified}",
    )


def _archetype_concentration_rec(arch: ArchetypePerformance) -> Optional[Recommendation]:
    """Info: surface the top-performing archetype if there's a clear winner."""
    if len(arch.rows) < 2:
        return None
    top = arch.rows[0]
    runner = arch.rows[1]
    if top.response_rate <= runner.response_rate + 0.10:
        return None
    pct = int(round(top.response_rate * 100))
    return Recommendation(
        code=f"top_archetype_{top.label}",
        severity="info",
        title=f"You convert best on '{top.label}' roles",
        body=(
            f"Your response rate on '{top.label}' is {pct}% "
            f"vs {int(round(runner.response_rate * 100))}% on '{runner.label}'. "
            "Bias the scanner toward this archetype."
        ),
        metric=f"{pct}%",
    )


def _ghost_pattern_rec(blockers: BlockerReport) -> Optional[Recommendation]:
    """Info when ghosted is dominant but the dominant_blocker rule didn't fire."""
    if not blockers.sufficient:
        return None
    ghost = next((b for b in blockers.counts if b.category == "ghosted"), None)
    if ghost is None or ghost.share < 0.20 or ghost.share >= MIN_DOMINANT_SHARE:
        return None  # let dominant rule own ≥30%; below 20% isn't worth surfacing
    pct = int(round(ghost.share * 100))
    return Recommendation(
        code="ghost_pattern",
        severity="info",
        title=f"{pct}% of your rejections are silent",
        body=(
            "Run the public ghost-check on jobs before applying to filter out "
            "likely-stale postings."
        ),
        metric=f"{ghost.count}/{blockers.classified}",
    )


_SEVERITY_ORDER: dict[Severity, int] = {"critical": 0, "warn": 1, "info": 2}


def build_recommendations(
    insights: PatternInsights,
    blockers: BlockerReport,
) -> tuple[Recommendation, ...]:
    """Compose all rule outputs into a deterministic ranked list."""
    recs: list[Recommendation] = []

    if isinstance(insights.funnel, FunnelInsight):
        rec = _funnel_collapse_rec(insights.funnel)
        if rec is not None:
            recs.append(rec)

    if isinstance(insights.score_outcome, ScoreOutcomeInsight):
        rec = _below_cutoff_rec(insights.score_outcome)
        if rec is not None:
            recs.append(rec)

    rec = _dominant_blocker_rec(blockers)
    if rec is not None:
        recs.append(rec)

    if isinstance(insights.archetype, ArchetypePerformance):
        rec = _archetype_concentration_rec(insights.archetype)
        if rec is not None:
            recs.append(rec)

    rec = _ghost_pattern_rec(blockers)
    if rec is not None:
        recs.append(rec)

    recs.sort(key=lambda r: (_SEVERITY_ORDER[r.severity], r.code))
    return tuple(recs)


__all__ = [
    "MIN_BLOCKER_OUTCOMES", "MIN_DOMINANT_SHARE", "MIN_FUNNEL_DROP_RATE",
    "MIN_BELOW_CUTOFF_SHARE", "MAX_REASON_SNIPPET_LEN", "MAX_SAMPLES_PER_BLOCKER",
    "BlockerCategory", "Severity",
    "RejectedApplication",
    "BlockerCount", "BlockerReport",
    "Recommendation",
    "classify_blockers", "build_recommendations",
]
