"""Tests for batch_scorer_worker — async fan-out glue.

The scorer is always injected; tests never touch the AI router.
"""

from __future__ import annotations

import asyncio
import pytest

from app.services.batch_evaluator import BatchEntry, ScoringResult, rank_batch
from app.services.batch_scorer_worker import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    score_plan,
)


# ── helpers ──────────────────────────────────────────────────────────


def _entry(url: str, *, ats=None) -> BatchEntry:
    return BatchEntry(raw_url=url, canonical_url=url, ats_key=ats)


def _ok(url: str, score: float, *, title="t", company="c") -> ScoringResult:
    return ScoringResult(
        canonical_url=url, fit_score=score, error=None, title=title, company=company,
    )


# ── empty / trivial cases ────────────────────────────────────────────


class TestEmpty:
    @pytest.mark.asyncio
    async def test_empty_entries_returns_empty_tuple(self):
        async def scorer(_):  # never called
            raise AssertionError("scorer must not run on empty input")
        result = await score_plan([], scorer=scorer)
        assert result == ()

    @pytest.mark.asyncio
    async def test_single_entry_passthrough(self):
        e = _entry("https://example.com/a")

        async def scorer(entry):
            return _ok(entry.canonical_url, 4.2)

        result = await score_plan([e], scorer=scorer)
        assert len(result) == 1
        assert result[0].canonical_url == "https://example.com/a"
        assert result[0].fit_score == 4.2


# ── ordering ─────────────────────────────────────────────────────────


class TestOrdering:
    @pytest.mark.asyncio
    async def test_results_match_input_order_even_with_jitter(self):
        """Slow scorers must not reorder results — UI correlates by index."""
        urls = [f"https://example.com/{i}" for i in range(8)]
        entries = [_entry(u) for u in urls]

        async def scorer(entry):
            # Reverse-proportional sleep: later entries finish first.
            idx = int(entry.canonical_url.rsplit("/", 1)[1])
            await asyncio.sleep(0.001 * (8 - idx))
            return _ok(entry.canonical_url, float(idx))

        result = await score_plan(entries, scorer=scorer, concurrency=8)
        assert [r.canonical_url for r in result] == urls
        assert [r.fit_score for r in result] == [float(i) for i in range(8)]


# ── concurrency cap ──────────────────────────────────────────────────


class TestConcurrencyCap:
    @pytest.mark.asyncio
    async def test_cap_honoured(self):
        """Instrument in-flight count and assert cap is never exceeded."""
        in_flight = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def scorer(entry):
            nonlocal in_flight, max_seen
            async with lock:
                in_flight += 1
                max_seen = max(max_seen, in_flight)
            await asyncio.sleep(0.005)
            async with lock:
                in_flight -= 1
            return _ok(entry.canonical_url, 3.0)

        entries = [_entry(f"https://example.com/{i}") for i in range(10)]
        await score_plan(entries, scorer=scorer, concurrency=3)
        assert max_seen <= 3

    @pytest.mark.asyncio
    async def test_concurrency_clamped_to_max(self):
        """Caller asking for 1000 must get clamped, not honoured."""
        in_flight = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def scorer(entry):
            nonlocal in_flight, max_seen
            async with lock:
                in_flight += 1
                max_seen = max(max_seen, in_flight)
            await asyncio.sleep(0.002)
            async with lock:
                in_flight -= 1
            return _ok(entry.canonical_url, 3.0)

        entries = [_entry(f"https://example.com/{i}") for i in range(50)]
        await score_plan(entries, scorer=scorer, concurrency=1000)
        assert max_seen <= MAX_CONCURRENCY

    @pytest.mark.asyncio
    async def test_concurrency_zero_clamped_to_one(self):
        async def scorer(entry):
            return _ok(entry.canonical_url, 1.0)

        entries = [_entry(f"https://example.com/{i}") for i in range(3)]
        result = await score_plan(entries, scorer=scorer, concurrency=0)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_concurrency_negative_clamped_to_one(self):
        async def scorer(entry):
            return _ok(entry.canonical_url, 1.0)

        entries = [_entry(f"https://example.com/{i}") for i in range(3)]
        result = await score_plan(entries, scorer=scorer, concurrency=-5)
        assert len(result) == 3

    def test_default_concurrency_is_reasonable(self):
        """Sanity: default must be in valid range."""
        assert 1 <= DEFAULT_CONCURRENCY <= MAX_CONCURRENCY


# ── error handling ───────────────────────────────────────────────────


class TestScorerErrors:
    @pytest.mark.asyncio
    async def test_scorer_raises_becomes_scorer_bug_error(self):
        async def scorer(entry):
            if "bad" in entry.canonical_url:
                raise RuntimeError("kaboom")
            return _ok(entry.canonical_url, 3.0)

        entries = [
            _entry("https://example.com/good"),
            _entry("https://example.com/bad"),
            _entry("https://example.com/also-good"),
        ]
        result = await score_plan(entries, scorer=scorer)
        assert result[0].error is None
        assert result[0].fit_score == 3.0
        assert result[1].error == "scorer_bug:RuntimeError"
        assert result[1].fit_score is None
        assert result[2].error is None

    @pytest.mark.asyncio
    async def test_scorer_returns_none_becomes_bad_return_error(self):
        async def scorer(entry):
            return None  # contract violation

        result = await score_plan([_entry("https://example.com/x")], scorer=scorer)
        assert result[0].error == "scorer_bad_return"
        assert result[0].fit_score is None

    @pytest.mark.asyncio
    async def test_scorer_returns_wrong_url_pinned_with_mismatch_error(self):
        async def scorer(entry):
            # Buggy scorer returns a different URL.
            return ScoringResult(
                canonical_url="https://wrong.example.com",
                fit_score=4.0,
                error=None,
                title="x",
                company="y",
            )

        result = await score_plan([_entry("https://right.example.com")], scorer=scorer)
        # canonical_url MUST be pinned to the original entry.
        assert result[0].canonical_url == "https://right.example.com"
        # And we MUST tag it so persistence layer knows the score is suspect.
        assert result[0].error == "scorer_url_mismatch"
        assert result[0].fit_score == 4.0
        assert result[0].title == "x"

    @pytest.mark.asyncio
    async def test_scorer_returning_url_mismatch_with_existing_error_keeps_error(self):
        async def scorer(entry):
            return ScoringResult(
                canonical_url="https://wrong.example.com",
                fit_score=None,
                error="upstream_timeout",
                title=None,
                company=None,
            )

        result = await score_plan([_entry("https://right.example.com")], scorer=scorer)
        assert result[0].canonical_url == "https://right.example.com"
        # Original error wins over the synthetic mismatch tag.
        assert result[0].error == "upstream_timeout"

    @pytest.mark.asyncio
    async def test_one_failure_does_not_kill_batch(self):
        async def scorer(entry):
            if "kill" in entry.canonical_url:
                raise ValueError("nope")
            return _ok(entry.canonical_url, 2.5)

        entries = [_entry(f"https://example.com/{i}") for i in range(5)]
        entries[2] = _entry("https://example.com/kill")
        result = await score_plan(entries, scorer=scorer)
        assert len(result) == 5
        assert result[2].error == "scorer_bug:ValueError"
        for i in (0, 1, 3, 4):
            assert result[i].error is None


# ── cancellation ─────────────────────────────────────────────────────


class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancellation_propagates(self):
        started = asyncio.Event()

        async def scorer(entry):
            started.set()
            await asyncio.sleep(10)  # long enough to be cancelled
            return _ok(entry.canonical_url, 1.0)

        entries = [_entry(f"https://example.com/{i}") for i in range(4)]
        task = asyncio.create_task(score_plan(entries, scorer=scorer))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ── integration with rank_batch ──────────────────────────────────────


class TestRankBatchIntegration:
    @pytest.mark.asyncio
    async def test_score_then_rank_end_to_end(self):
        """Worker output flows directly into rank_batch."""
        async def scorer(entry):
            mapping = {
                "https://example.com/a": 4.5,
                "https://example.com/b": 2.0,
                "https://example.com/c": 3.7,
            }
            return _ok(entry.canonical_url, mapping[entry.canonical_url])

        entries = [
            _entry("https://example.com/a"),
            _entry("https://example.com/b"),
            _entry("https://example.com/c"),
        ]
        scored = await score_plan(entries, scorer=scorer)
        ranked = rank_batch(scored, min_fit_score=3.0)

        assert [r.canonical_url for r in ranked.ranked] == [
            "https://example.com/a",
            "https://example.com/c",
        ]
        assert [r.canonical_url for r in ranked.below_threshold] == [
            "https://example.com/b",
        ]
        assert ranked.failed == ()

    @pytest.mark.asyncio
    async def test_failures_route_to_failed_bucket(self):
        async def scorer(entry):
            if "fail" in entry.canonical_url:
                raise RuntimeError("x")
            return _ok(entry.canonical_url, 4.0)

        entries = [
            _entry("https://example.com/ok"),
            _entry("https://example.com/fail"),
        ]
        scored = await score_plan(entries, scorer=scorer)
        ranked = rank_batch(scored, min_fit_score=3.0)
        assert len(ranked.ranked) == 1
        assert len(ranked.failed) == 1
        assert ranked.failed[0].error == "scorer_bug:RuntimeError"
