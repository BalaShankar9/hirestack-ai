"""B0 — batch_evaluator unit tests."""
from __future__ import annotations

import pytest

from app.services.batch_evaluator import (
    MAX_URLS,
    BatchEntry,
    BatchPlan,
    BatchReject,
    RankedBatch,
    ScoringResult,
    plan_batch,
    rank_batch,
)


# ── plan_batch ───────────────────────────────────────────────────────


def test_plan_batch_accepts_valid_urls() -> None:
    plan = plan_batch([
        "https://boards.greenhouse.io/stripe/jobs/12345",
        "https://jobs.lever.co/netflix/abc-123",
    ])
    assert len(plan.accepted) == 2
    assert plan.rejected == ()
    assert plan.accepted[0].ats_key is not None
    assert plan.accepted[0].ats_key[0] == "greenhouse"
    assert plan.accepted[1].ats_key[0] == "lever"


def test_plan_batch_canonicalizes_urls() -> None:
    plan = plan_batch(["https://EXAMPLE.com/jobs/1?utm_source=foo"])
    assert plan.accepted[0].canonical_url == "https://example.com/jobs/1"
    # raw preserved as-given
    assert plan.accepted[0].raw_url == "https://EXAMPLE.com/jobs/1?utm_source=foo"


def test_plan_batch_dedupes_by_canonical() -> None:
    plan = plan_batch([
        "https://x.com/jobs/1?utm_source=a",
        "https://x.com/jobs/1?utm_source=b",
        "https://x.com/jobs/1?fbclid=z",
    ])
    assert len(plan.accepted) == 1
    assert len(plan.rejected) == 2
    assert all(r.reason == "duplicate" for r in plan.rejected)
    # first wins
    assert plan.accepted[0].raw_url == "https://x.com/jobs/1?utm_source=a"


def test_plan_batch_rejects_empty_strings() -> None:
    plan = plan_batch(["", "   ", "\t\n"])
    assert plan.accepted == ()
    assert len(plan.rejected) == 3
    assert all(r.reason == "empty" for r in plan.rejected)


def test_plan_batch_rejects_non_http_urls() -> None:
    plan = plan_batch(["ftp://x", "not a url", "javascript:alert(1)"])
    assert plan.accepted == ()
    assert all(r.reason == "invalid_url" for r in plan.rejected)


def test_plan_batch_caps_at_max_urls() -> None:
    urls = [f"https://x.com/jobs/{i}" for i in range(MAX_URLS + 5)]
    plan = plan_batch(urls)
    assert len(plan.accepted) == MAX_URLS
    over = [r for r in plan.rejected if r.reason == "over_cap"]
    assert len(over) == 5
    # First MAX_URLS accepted; last 5 rejected as over_cap.
    assert over[0].raw_url == urls[MAX_URLS]


def test_plan_batch_handles_empty_input() -> None:
    plan = plan_batch([])
    assert plan.accepted == ()
    assert plan.rejected == ()
    assert plan.is_empty is True


def test_plan_batch_coerces_non_string_inputs() -> None:
    plan = plan_batch([None, 42, "https://x.com/j/1"])  # type: ignore[list-item]
    # None → "" → empty; 42 → "42" → invalid_url; valid one accepted.
    assert len(plan.accepted) == 1
    reasons = sorted(r.reason for r in plan.rejected)
    assert reasons == ["empty", "invalid_url"]


def test_plan_batch_preserves_order() -> None:
    plan = plan_batch([
        "https://a.com/j/1",
        "https://b.com/j/2",
        "https://c.com/j/3",
    ])
    hosts = [e.canonical_url.split("/")[2] for e in plan.accepted]
    assert hosts == ["a.com", "b.com", "c.com"]


def test_plan_batch_marks_unknown_ats_with_none_key() -> None:
    plan = plan_batch(["https://random-careers.example.com/jobs/42"])
    assert plan.accepted[0].ats_key is None


def test_batch_plan_is_empty_property() -> None:
    assert plan_batch([]).is_empty
    assert not plan_batch(["https://x.com/j/1"]).is_empty


# ── rank_batch ───────────────────────────────────────────────────────


def _result(url: str, score: float | None, *, error: str | None = None) -> ScoringResult:
    return ScoringResult(canonical_url=url, fit_score=score, error=error)


def test_rank_batch_sorts_desc_by_fit_score() -> None:
    out = rank_batch([
        _result("https://a/1", 3.0),
        _result("https://b/2", 4.5),
        _result("https://c/3", 2.0),
    ])
    assert [r.fit_score for r in out.ranked] == [4.5, 3.0, 2.0]


def test_rank_batch_filters_below_threshold() -> None:
    out = rank_batch(
        [_result("https://a/1", 3.0), _result("https://b/2", 4.5),
         _result("https://c/3", 2.0)],
        min_fit_score=3.5,
    )
    assert [r.fit_score for r in out.ranked] == [4.5]
    assert [r.fit_score for r in out.below_threshold] == [3.0, 2.0]


def test_rank_batch_routes_errored_results_to_failed() -> None:
    out = rank_batch([
        _result("https://a/1", None, error="fetch_failed"),
        _result("https://b/2", 4.0),
        # error wins even if a score is also present
        _result("https://c/3", 5.0, error="parse_failed"),
    ])
    assert len(out.failed) == 2
    assert {r.error for r in out.failed} == {"fetch_failed", "parse_failed"}
    assert len(out.ranked) == 1


def test_rank_batch_treats_none_score_without_error_as_failed() -> None:
    out = rank_batch([_result("https://a/1", None)])
    assert len(out.failed) == 1
    assert out.ranked == ()


def test_rank_batch_preserves_failed_input_order() -> None:
    out = rank_batch([
        _result("https://a/1", None, error="e1"),
        _result("https://b/2", None, error="e2"),
        _result("https://c/3", None, error="e3"),
    ])
    assert [r.error for r in out.failed] == ["e1", "e2", "e3"]


def test_rank_batch_tie_breaks_by_canonical_url_asc() -> None:
    out = rank_batch([
        _result("https://b/2", 4.0),
        _result("https://a/1", 4.0),
        _result("https://c/3", 4.0),
    ])
    assert [r.canonical_url for r in out.ranked] == [
        "https://a/1", "https://b/2", "https://c/3",
    ]


def test_rank_batch_threshold_at_floor_includes_zero() -> None:
    out = rank_batch([_result("https://a/1", 0.0)], min_fit_score=0.0)
    assert len(out.ranked) == 1


def test_rank_batch_threshold_boundary_inclusive() -> None:
    # threshold is >= so a result exactly at threshold passes.
    out = rank_batch([_result("https://a/1", 4.0)], min_fit_score=4.0)
    assert len(out.ranked) == 1
    assert out.below_threshold == ()


def test_rank_batch_rejects_out_of_range_threshold() -> None:
    with pytest.raises(ValueError):
        rank_batch([], min_fit_score=-0.1)
    with pytest.raises(ValueError):
        rank_batch([], min_fit_score=5.1)


def test_rank_batch_rejects_non_numeric_threshold() -> None:
    with pytest.raises(ValueError):
        rank_batch([], min_fit_score="high")  # type: ignore[arg-type]


def test_rank_batch_handles_empty_input() -> None:
    out = rank_batch([])
    assert out.ranked == ()
    assert out.below_threshold == ()
    assert out.failed == ()


def test_rank_batch_default_threshold_is_floor() -> None:
    # Default min_fit_score=0 means even a 0.0 score lands in ranked.
    out = rank_batch([_result("https://a/1", 0.5), _result("https://b/2", 0.0)])
    assert len(out.ranked) == 2
    assert out.below_threshold == ()


# ── Integration: plan + rank round-trip ──────────────────────────────


def test_plan_then_rank_uses_canonical_url_as_handoff_key() -> None:
    plan = plan_batch([
        "https://x.com/jobs/1?utm_source=a",
        "https://y.com/jobs/2",
    ])
    # Worker scores by canonical_url and returns same key.
    scored = [
        ScoringResult(canonical_url=plan.accepted[0].canonical_url, fit_score=3.5),
        ScoringResult(canonical_url=plan.accepted[1].canonical_url, fit_score=4.5),
    ]
    out = rank_batch(scored, min_fit_score=3.0)
    assert [r.fit_score for r in out.ranked] == [4.5, 3.5]


def test_dataclasses_are_frozen() -> None:
    e = BatchEntry(raw_url="r", canonical_url="c", ats_key=None)
    with pytest.raises(Exception):
        e.raw_url = "x"  # type: ignore[misc]


def test_plan_batch_does_not_mutate_input() -> None:
    urls = ["https://x/j/1", "https://y/j/2"]
    snap = list(urls)
    plan_batch(urls)
    assert urls == snap
