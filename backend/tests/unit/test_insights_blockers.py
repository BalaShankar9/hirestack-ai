"""A2.b — insights_blockers unit tests."""
from __future__ import annotations

import pytest

from app.services.insights_blockers import (
    MAX_REASON_SNIPPET_LEN,
    MAX_SAMPLES_PER_BLOCKER,
    MIN_BLOCKER_OUTCOMES,
    MIN_DOMINANT_SHARE,
    BlockerReport,
    Recommendation,
    RejectedApplication,
    build_recommendations,
    classify_blockers,
)
from app.services.pattern_insights import (
    ApplicationRecord,
    compute_pattern_insights,
)


def _r(reason: str | None, status: str = "rejected", aid: str | None = None) -> RejectedApplication:
    return RejectedApplication(
        application_id=aid or f"r-{id(reason)}-{status}",
        status=status,
        rejection_reason=reason,
    )


# ── Classifier coverage (one per category) ──────────────────────────


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("Looking for someone more senior with 10+ years experience.", "under_qualified"),
        ("You're overqualified for this role.", "over_qualified"),
        ("We can only hire local candidates in the Bay Area office.", "location_mismatch"),
        ("Sorry, we cannot offer visa sponsorship at this time.", "visa_sponsorship"),
        ("Your salary expectations are out of our budget range.", "salary_mismatch"),
        ("Position has been filled internally.", "timing_filled"),
        ("Looking for a better match on the tech stack.", "skills_gap"),
        ("Just didn't work out.", "other"),
    ],
)
def test_classifier_routes_each_category(reason: str, expected: str) -> None:
    rep = classify_blockers([_r(reason)] * MIN_BLOCKER_OUTCOMES)
    by_cat = {b.category: b for b in rep.counts}
    assert expected in by_cat
    assert by_cat[expected].count == MIN_BLOCKER_OUTCOMES


def test_classifier_missing_reason_is_ghosted() -> None:
    rep = classify_blockers([_r(None)] * MIN_BLOCKER_OUTCOMES)
    by_cat = {b.category: b for b in rep.counts}
    assert "ghosted" in by_cat
    assert by_cat["ghosted"].count == MIN_BLOCKER_OUTCOMES


def test_classifier_empty_string_reason_is_ghosted() -> None:
    rep = classify_blockers([_r("   ")] * MIN_BLOCKER_OUTCOMES)
    by_cat = {b.category: b for b in rep.counts}
    assert by_cat["ghosted"].count == MIN_BLOCKER_OUTCOMES


def test_classifier_first_pattern_wins_for_priority() -> None:
    # "overqualified" + "salary" both match — over_qualified is checked first
    rep = classify_blockers(
        [_r("You are overqualified for this salary band.")] * MIN_BLOCKER_OUTCOMES
    )
    by_cat = {b.category: b for b in rep.counts}
    assert "over_qualified" in by_cat
    assert "salary_mismatch" not in by_cat


# ── Report shape + sufficiency gate ─────────────────────────────────


def test_report_below_min_is_insufficient() -> None:
    rep = classify_blockers([_r("rejected because of skills gap")] * (MIN_BLOCKER_OUTCOMES - 1))
    assert rep.sufficient is False
    assert rep.total_rejected == MIN_BLOCKER_OUTCOMES - 1


def test_report_at_min_is_sufficient() -> None:
    rep = classify_blockers([_r("rejected because of skills gap")] * MIN_BLOCKER_OUTCOMES)
    assert rep.sufficient is True


def test_report_excludes_non_rejection_statuses() -> None:
    rep = classify_blockers([
        _r("filled", status="offer"),
        _r("filled", status="interview"),
        _r("filled", status="responded"),
    ])
    assert rep.total_rejected == 0


def test_report_includes_discarded_via_alias() -> None:
    # 'descartado' is an alias for 'discarded' — must classify
    rep = classify_blockers(
        [_r("Position has been filled.", status="descartado")] * MIN_BLOCKER_OUTCOMES
    )
    assert rep.sufficient is True
    by_cat = {b.category: b for b in rep.counts}
    assert by_cat["timing_filled"].count == MIN_BLOCKER_OUTCOMES


def test_report_shares_sum_to_one_when_classified() -> None:
    rep = classify_blockers([
        _r("salary mismatch"),
        _r("salary mismatch"),
        _r("looking for senior"),
        _r(None),
        _r("just because"),
    ])
    assert rep.classified == 5
    assert sum(b.share for b in rep.counts) == pytest.approx(1.0)


def test_report_counts_sorted_desc() -> None:
    rep = classify_blockers(
        [_r("salary mismatch")] * 3
        + [_r("Position filled.")] * 2
        + [_r("looking for senior")] * 1
    )
    counts = [b.count for b in rep.counts]
    assert counts == sorted(counts, reverse=True)


# ── Samples + snippet truncation ────────────────────────────────────


def test_samples_capped_at_max_per_blocker() -> None:
    rep = classify_blockers([_r(f"salary issue {i}") for i in range(10)])
    by_cat = {b.category: b for b in rep.counts}
    assert len(by_cat["salary_mismatch"].samples) == MAX_SAMPLES_PER_BLOCKER


def test_long_reason_snippet_truncated() -> None:
    long = "salary " + ("x" * 500)
    rep = classify_blockers([_r(long)] * MIN_BLOCKER_OUTCOMES)
    by_cat = {b.category: b for b in rep.counts}
    sample = by_cat["salary_mismatch"].samples[0]
    assert len(sample) <= MAX_REASON_SNIPPET_LEN
    assert sample.endswith("…")


def test_ghosted_bucket_has_no_samples() -> None:
    rep = classify_blockers([_r(None)] * MIN_BLOCKER_OUTCOMES)
    by_cat = {b.category: b for b in rep.counts}
    assert by_cat["ghosted"].samples == ()


# ── Determinism / immutability ──────────────────────────────────────


def test_classify_is_deterministic() -> None:
    rec_list = [_r("salary"), _r(None), _r("looking for senior"), _r("filled internally")]
    a = classify_blockers(rec_list)
    b = classify_blockers(rec_list)
    assert a == b


def test_classify_does_not_mutate_input() -> None:
    rec_list = [_r("salary")] * 3
    snap = list(rec_list)
    classify_blockers(rec_list)
    assert rec_list == snap


# ── Recommendation rules ────────────────────────────────────────────


def _apps(*specs: tuple[str, str | None, float | None, str | None]) -> list[ApplicationRecord]:
    """Helper: each spec = (status, _ignored, fit_score, archetype)."""
    return [
        ApplicationRecord(application_id=f"a-{i}", status=s, fit_score=fs, archetype_label=arch)
        for i, (s, _, fs, arch) in enumerate(specs)
    ]


def test_funnel_collapse_critical_when_drop_above_threshold() -> None:
    # 20 applied, 1 responded → 95% drop
    apps = (
        [ApplicationRecord(application_id=f"a-{i}", status="submitted") for i in range(19)]
        + [ApplicationRecord(application_id="a-19", status="responded")]
    )
    insights = compute_pattern_insights(apps)
    blockers = classify_blockers([])
    recs = build_recommendations(insights, blockers)
    codes = [r.code for r in recs]
    assert any(c.startswith("funnel_collapse_") for c in codes)
    crit = [r for r in recs if r.code.startswith("funnel_collapse_")][0]
    assert crit.severity == "critical"


def test_no_funnel_collapse_when_drops_are_normal() -> None:
    # 10 applied, 6 responded, 4 interview, 2 offer — no stage drops ≥85%
    apps = (
        [ApplicationRecord(application_id=f"a-{i}", status="submitted") for i in range(4)]
        + [ApplicationRecord(application_id=f"r-{i}", status="responded") for i in range(2)]
        + [ApplicationRecord(application_id=f"i-{i}", status="interview") for i in range(2)]
        + [ApplicationRecord(application_id=f"o-{i}", status="offer") for i in range(2)]
    )
    insights = compute_pattern_insights(apps)
    blockers = classify_blockers([])
    recs = build_recommendations(insights, blockers)
    assert not any(r.code.startswith("funnel_collapse_") for r in recs)


def test_below_cutoff_critical_when_share_above_threshold() -> None:
    # cutoff at 4.0 (only 4-5 bucket wins). 5 below + 5 at cutoff → 50% below
    apps = [
        ApplicationRecord(application_id=f"hi-{i}", status="offer", fit_score=4.5)
        for i in range(5)
    ] + [
        ApplicationRecord(application_id=f"lo-{i}", status="rejected", fit_score=2.0)
        for i in range(5)
    ]
    insights = compute_pattern_insights(apps)
    blockers = classify_blockers([])
    recs = build_recommendations(insights, blockers)
    codes = [r.code for r in recs]
    assert "below_cutoff_waste" in codes
    rec = next(r for r in recs if r.code == "below_cutoff_waste")
    assert rec.severity == "critical"


def test_dominant_blocker_warn_emitted() -> None:
    insights = compute_pattern_insights([])
    blockers = classify_blockers(
        [_r("salary mismatch")] * 4
        + [_r(None)]            # 4/5 → 80% dominant
    )
    recs = build_recommendations(insights, blockers)
    rec = next(r for r in recs if r.code.startswith("dominant_blocker_"))
    assert rec.severity == "warn"
    assert "salary" in rec.code


def test_no_dominant_blocker_when_share_below_threshold() -> None:
    insights = compute_pattern_insights([])
    # 1 of each category → top share = 1/8 = 12.5% < 30%
    blockers = classify_blockers([
        _r("salary"), _r("looking for senior"), _r("overqualified"),
        _r("relocate"), _r("visa"), _r("filled"),
        _r("better match"), _r("just because"),
    ])
    recs = build_recommendations(insights, blockers)
    assert not any(r.code.startswith("dominant_blocker_") for r in recs)


def test_archetype_concentration_info_when_clear_winner() -> None:
    # big_tech_ic 5 offers, enterprise_saas 5 rejected → response gap >> 10pp
    apps = (
        [ApplicationRecord(application_id=f"bt-{i}", status="offer", archetype_label="big_tech_ic") for i in range(5)]
        + [ApplicationRecord(application_id=f"es-{i}", status="rejected", archetype_label="enterprise_saas") for i in range(5)]
    )
    insights = compute_pattern_insights(apps)
    blockers = classify_blockers([])
    recs = build_recommendations(insights, blockers)
    rec = next(r for r in recs if r.code.startswith("top_archetype_"))
    assert rec.severity == "info"
    assert rec.code == "top_archetype_big_tech_ic"


def test_no_archetype_rec_when_only_one_archetype() -> None:
    apps = [
        ApplicationRecord(application_id=f"a-{i}", status="offer", archetype_label="big_tech_ic")
        for i in range(5)
    ]
    insights = compute_pattern_insights(apps)
    recs = build_recommendations(insights, classify_blockers([]))
    assert not any(r.code.startswith("top_archetype_") for r in recs)


def test_ghost_pattern_info_when_ghost_share_in_band() -> None:
    # ghosted 25% (between 20% and 30%) → info, no dominant rule
    blockers = classify_blockers(
        [_r(None)] * 2 + [_r("salary")] * 2 + [_r("looking for senior")] * 2 + [_r("filled")] * 2
    )
    insights = compute_pattern_insights([])
    recs = build_recommendations(insights, blockers)
    assert any(r.code == "ghost_pattern" for r in recs)


def test_ghost_pattern_skipped_when_dominant_already_emitted() -> None:
    # ghosted 5/5 = 100% → dominant rule fires, ghost_pattern suppressed
    blockers = classify_blockers([_r(None)] * MIN_BLOCKER_OUTCOMES)
    insights = compute_pattern_insights([])
    recs = build_recommendations(insights, blockers)
    codes = [r.code for r in recs]
    assert "dominant_blocker_ghosted" in codes
    assert "ghost_pattern" not in codes


def test_recommendations_sorted_critical_first() -> None:
    # All three severities present
    apps = (
        [ApplicationRecord(application_id=f"hi-{i}", status="offer", fit_score=4.5,
                           archetype_label="big_tech_ic") for i in range(5)]
        + [ApplicationRecord(application_id=f"lo-{i}", status="rejected", fit_score=2.0,
                             archetype_label="enterprise_saas") for i in range(15)]
    )
    insights = compute_pattern_insights(apps)
    blockers = classify_blockers([_r("salary")] * 5)
    recs = build_recommendations(insights, blockers)
    severities = [r.severity for r in recs]
    # First non-info must come before any info; criticals before warns
    seen_warn = False
    seen_info = False
    for s in severities:
        if s == "info":
            seen_info = True
        elif s == "warn":
            assert not seen_info, "warn should not follow info"
            seen_warn = True
        elif s == "critical":
            assert not seen_warn, "critical should not follow warn"
            assert not seen_info, "critical should not follow info"


def test_recommendations_empty_when_no_signals() -> None:
    insights = compute_pattern_insights([])
    blockers = classify_blockers([])
    recs = build_recommendations(insights, blockers)
    assert recs == ()


def test_recommendations_deterministic() -> None:
    apps = [
        ApplicationRecord(application_id=f"hi-{i}", status="offer", fit_score=4.5)
        for i in range(5)
    ] + [
        ApplicationRecord(application_id=f"lo-{i}", status="rejected", fit_score=2.0)
        for i in range(5)
    ]
    blockers = classify_blockers([_r("salary")] * 5)
    a = build_recommendations(compute_pattern_insights(apps), blockers)
    b = build_recommendations(compute_pattern_insights(apps), blockers)
    assert a == b


def test_dominant_blocker_skipped_when_insufficient() -> None:
    # 4 records (below MIN=5) — even if all same category, not sufficient
    blockers = classify_blockers([_r("salary")] * 4)
    recs = build_recommendations(compute_pattern_insights([]), blockers)
    assert not any(r.code.startswith("dominant_blocker_") for r in recs)


def test_below_cutoff_skipped_when_no_cutoff() -> None:
    # All rejected — no cutoff set
    apps = [
        ApplicationRecord(application_id=f"a-{i}", status="rejected", fit_score=4.5)
        for i in range(5)
    ]
    insights = compute_pattern_insights(apps)
    recs = build_recommendations(insights, classify_blockers([]))
    assert not any(r.code == "below_cutoff_waste" for r in recs)
