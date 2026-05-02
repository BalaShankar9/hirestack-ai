"""A2.a — pattern_insights unit tests."""
from __future__ import annotations

import pytest

from app.services.pattern_insights import (
    MIN_OUTCOMES,
    MIN_PER_ARCHETYPE,
    SCORE_BUCKET_EDGES,
    ApplicationRecord,
    ArchetypePerformance,
    FunnelInsight,
    InsufficientData,
    PatternInsights,
    ScoreOutcomeInsight,
    compute_pattern_insights,
)


def _app(
    status: str,
    *,
    fit_score: float | None = None,
    archetype: str | None = None,
    aid: str | None = None,
) -> ApplicationRecord:
    return ApplicationRecord(
        application_id=aid or f"a-{id(status)}-{fit_score}-{archetype}",
        status=status,
        fit_score=fit_score,
        archetype_label=archetype,
    )


# ── Insufficient-data gating ─────────────────────────────────────────


def test_empty_inputs_return_insufficient_data_for_all_sections() -> None:
    out = compute_pattern_insights([])
    assert isinstance(out.funnel, InsufficientData)
    assert isinstance(out.score_outcome, InsufficientData)
    assert isinstance(out.archetype, InsufficientData)
    assert out.total_applications == 0
    assert out.total_outcomes == 0


def test_below_min_outcomes_returns_insufficient_data() -> None:
    out = compute_pattern_insights([_app("submitted")] * (MIN_OUTCOMES - 1))
    assert isinstance(out.funnel, InsufficientData)
    assert out.funnel.have == MIN_OUTCOMES - 1
    assert out.funnel.need == MIN_OUTCOMES


def test_at_min_outcomes_renders_funnel() -> None:
    records = [_app("submitted") for _ in range(MIN_OUTCOMES)]
    out = compute_pattern_insights(records)
    assert isinstance(out.funnel, FunnelInsight)


def test_drafts_and_archived_excluded_from_outcome_count() -> None:
    records = (
        [_app("draft")] * 10
        + [_app("archived")] * 10
        + [_app("submitted")] * (MIN_OUTCOMES - 1)
    )
    out = compute_pattern_insights(records)
    assert isinstance(out.funnel, InsufficientData)


# ── Funnel correctness ──────────────────────────────────────────────


def test_funnel_monotonic_progression() -> None:
    # 10 applied, 4 responded, 2 interview, 1 offer
    records = (
        [_app("submitted")] * 6      # applied-only
        + [_app("responded")] * 2    # applied + responded
        + [_app("interview")] * 1    # applied + responded + interview
        + [_app("offer")] * 1        # all four
    )
    out = compute_pattern_insights(records)
    assert isinstance(out.funnel, FunnelInsight)
    counts = {s.name: s.count for s in out.funnel.stages}
    assert counts == {"applied": 10, "responded": 4, "interview": 2, "offer": 1}


def test_funnel_rate_from_prior_and_top() -> None:
    records = (
        [_app("submitted")] * 6
        + [_app("responded")] * 2
        + [_app("interview")] * 1
        + [_app("offer")] * 1
    )
    out = compute_pattern_insights(records)
    assert isinstance(out.funnel, FunnelInsight)
    stages = {s.name: s for s in out.funnel.stages}
    # applied: top, no prior
    assert stages["applied"].rate_from_prior is None
    assert stages["applied"].rate_from_top == 1.0
    # responded: 4/10 from prior, 4/10 from top
    assert stages["responded"].rate_from_prior == pytest.approx(0.4)
    assert stages["responded"].rate_from_top == pytest.approx(0.4)
    # interview: 2/4 from prior, 2/10 from top
    assert stages["interview"].rate_from_prior == pytest.approx(0.5)
    assert stages["interview"].rate_from_top == pytest.approx(0.2)
    # offer: 1/2 from prior, 1/10 from top
    assert stages["offer"].rate_from_prior == pytest.approx(0.5)
    assert stages["offer"].rate_from_top == pytest.approx(0.1)


def test_funnel_handles_aliases_via_canonicalization() -> None:
    # 'applied' is an alias for 'submitted'; 'descartado' for 'discarded'
    records = (
        [_app("applied")] * 4
        + [_app("descartado")] * 2
    )
    out = compute_pattern_insights(records)
    assert isinstance(out.funnel, FunnelInsight)
    counts = {s.name: s.count for s in out.funnel.stages}
    # all 6 are applied (descartado is post-application discard)
    assert counts["applied"] == 6


# ── Score × outcome ─────────────────────────────────────────────────


def test_score_outcome_buckets_have_correct_labels_and_edges() -> None:
    records = [
        _app("offer", fit_score=4.5),
        _app("offer", fit_score=4.2),
        _app("interview", fit_score=3.5),
        _app("rejected", fit_score=2.5),
        _app("rejected", fit_score=1.0),
    ]
    out = compute_pattern_insights(records)
    assert isinstance(out.score_outcome, ScoreOutcomeInsight)
    assert len(out.score_outcome.buckets) == len(SCORE_BUCKET_EDGES) - 1
    assert out.score_outcome.buckets[0].label == "0.0–1.0"
    assert out.score_outcome.buckets[-1].label == "4.0–5.0"


def test_score_outcome_win_rate_and_cutoff() -> None:
    # 4-5 bucket: 2 wins → 100%
    # 3-4 bucket: 1 win → 100%
    # 2-3 bucket: 0/1 → 0%
    # 1-2 bucket: 0/0 → None (won+lost == 0)
    # 0-1 bucket: 0/1 → 0%
    records = [
        _app("offer", fit_score=4.5),
        _app("offer", fit_score=4.2),
        _app("interview", fit_score=3.5),
        _app("rejected", fit_score=2.5),
        _app("rejected", fit_score=0.5),
    ]
    out = compute_pattern_insights(records)
    assert isinstance(out.score_outcome, ScoreOutcomeInsight)
    rates = {b.label: b.win_rate for b in out.score_outcome.buckets}
    assert rates["4.0–5.0"] == pytest.approx(1.0)
    assert rates["3.0–4.0"] == pytest.approx(1.0)
    assert rates["2.0–3.0"] == pytest.approx(0.0)
    assert rates["1.0–2.0"] is None
    assert rates["0.0–1.0"] == pytest.approx(0.0)
    # cutoff = lowest bucket lower-edge with win_rate >= 0.5; here 3.0
    assert out.score_outcome.cutoff_score == pytest.approx(3.0)


def test_score_outcome_perfect_5_score_lands_in_top_bucket() -> None:
    records = [
        _app("offer", fit_score=5.0),
        _app("interview", fit_score=4.99),
        _app("offer", fit_score=4.0),
        _app("rejected", fit_score=2.0),
        _app("rejected", fit_score=1.0),
    ]
    out = compute_pattern_insights(records)
    assert isinstance(out.score_outcome, ScoreOutcomeInsight)
    top = out.score_outcome.buckets[-1]
    assert top.won == 3
    assert top.lost == 0


def test_score_outcome_excludes_open_pipeline() -> None:
    # responded does NOT count as won or lost
    records = [
        _app("offer", fit_score=4.5),
        _app("interview", fit_score=4.0),
        _app("rejected", fit_score=2.5),
        _app("rejected", fit_score=1.5),
        _app("rejected", fit_score=0.5),
        _app("responded", fit_score=4.8),  # excluded
        _app("submitted", fit_score=3.0),  # excluded
    ]
    out = compute_pattern_insights(records)
    assert isinstance(out.score_outcome, ScoreOutcomeInsight)
    assert out.score_outcome.total_scored_outcomes == 5


def test_score_outcome_below_min_returns_insufficient_data() -> None:
    records = [_app("offer", fit_score=4.5)] * (MIN_OUTCOMES - 1)
    out = compute_pattern_insights(records)
    assert isinstance(out.score_outcome, InsufficientData)


def test_score_outcome_no_cutoff_when_no_bucket_crosses_threshold() -> None:
    records = [
        _app("rejected", fit_score=4.5),
        _app("rejected", fit_score=4.2),
        _app("rejected", fit_score=3.5),
        _app("rejected", fit_score=2.5),
        _app("rejected", fit_score=1.0),
    ]
    out = compute_pattern_insights(records)
    assert isinstance(out.score_outcome, ScoreOutcomeInsight)
    assert out.score_outcome.cutoff_score is None


# ── Archetype performance ───────────────────────────────────────────


def test_archetype_performance_groups_and_ranks() -> None:
    # Five 'big_tech_ic': 1 offer + 2 interview + 2 rejected → response 60%, interview 60%, offer 20%
    # Four 'startup_founder_adj': 0 offers, 1 responded, 3 rejected → response 25%, interview 0%, offer 0%
    records = (
        [_app("offer", archetype="big_tech_ic"), _app("interview", archetype="big_tech_ic"),
         _app("interview", archetype="big_tech_ic"),
         _app("rejected", archetype="big_tech_ic"), _app("rejected", archetype="big_tech_ic")]
        + [_app("responded", archetype="startup_founder_adj"),
           _app("rejected", archetype="startup_founder_adj"),
           _app("rejected", archetype="startup_founder_adj"),
           _app("rejected", archetype="startup_founder_adj")]
    )
    out = compute_pattern_insights(records)
    assert isinstance(out.archetype, ArchetypePerformance)
    by_label = {r.label: r for r in out.archetype.rows}
    assert by_label["big_tech_ic"].n == 5
    assert by_label["big_tech_ic"].response_rate == pytest.approx(0.6)
    assert by_label["big_tech_ic"].interview_rate == pytest.approx(0.6)
    assert by_label["big_tech_ic"].offer_rate == pytest.approx(0.2)
    assert by_label["startup_founder_adj"].response_rate == pytest.approx(0.25)
    # ranked desc by response_rate
    assert out.archetype.rows[0].label == "big_tech_ic"


def test_archetype_excludes_groups_below_min_per_archetype() -> None:
    # one big_tech_ic (below MIN_PER_ARCHETYPE=3), four agency_consulting (above)
    records = (
        [_app("offer", archetype="big_tech_ic")]
        + [_app("rejected", archetype="agency_consulting")] * 4
    )
    out = compute_pattern_insights(records)
    assert isinstance(out.archetype, ArchetypePerformance)
    labels = {r.label for r in out.archetype.rows}
    assert "big_tech_ic" not in labels
    assert "agency_consulting" in labels
    assert "big_tech_ic" in out.archetype.excluded_for_low_n


def test_archetype_skips_records_without_label() -> None:
    records = (
        [_app("offer")] * 3              # no archetype → ignored
        + [_app("rejected", archetype="big_tech_ic")] * 3
    )
    out = compute_pattern_insights(records)
    # 6 outcomes total but only 3 with a label → 3 < MIN_OUTCOMES → insufficient
    assert isinstance(out.archetype, InsufficientData)


# ── Determinism / immutability ──────────────────────────────────────


def test_compute_pattern_insights_is_deterministic() -> None:
    records = [
        _app("offer", fit_score=4.5, archetype="big_tech_ic"),
        _app("interview", fit_score=4.0, archetype="big_tech_ic"),
        _app("rejected", fit_score=2.5, archetype="big_tech_ic"),
        _app("rejected", fit_score=1.5, archetype="enterprise_saas"),
        _app("offer", fit_score=4.8, archetype="enterprise_saas"),
    ]
    a = compute_pattern_insights(records)
    b = compute_pattern_insights(records)
    assert a == b


def test_compute_pattern_insights_does_not_mutate_input() -> None:
    records = [_app("offer")] * 5
    snap = list(records)
    compute_pattern_insights(records)
    assert records == snap


def test_total_counts_reported() -> None:
    records = (
        [_app("draft")] * 3
        + [_app("submitted")] * 5
        + [_app("offer")] * 1
    )
    out = compute_pattern_insights(records)
    assert out.total_applications == 9
    assert out.total_outcomes == 6  # drafts excluded


# ── Pattern insights envelope is a frozen dataclass ─────────────────


def test_pattern_insights_envelope_is_immutable() -> None:
    out = compute_pattern_insights([])
    with pytest.raises(Exception):
        out.total_applications = 99  # type: ignore[misc]
