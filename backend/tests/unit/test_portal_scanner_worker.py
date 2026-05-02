"""B1.next — portal_scanner_worker unit tests.

Covers:
  * Backoff math (1, 2, 4, capped at 8).
  * _is_retryable_status truth table (429, 5xx vs 4xx).
  * _fetch_with_retry: success first try, retry-then-success on 429,
    permanent 404 short-circuits, transport error path, max-retry
    exhaustion.
  * _scan_one: parser-error path mapped to ScanFailure(parse_error).
  * run_scan end-to-end: empty input, mixed providers, dedup against
    seen_url_canonicals, per-provider concurrency cap honoured,
    fetcher failures isolated to their plan.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from unittest.mock import AsyncMock

import pytest

from app.services import portal_scanner_worker as worker
from app.services.portal_scanner import FetchPlan, JobPosting, TrackedCompany


# ── Fixtures ─────────────────────────────────────────────────────────


def _gh_payload() -> dict:
    return {
        "jobs": [
            {
                "id": 101,
                "title": "Senior Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
                "location": {"name": "Remote"},
                "updated_at": "2026-04-20T12:00:00Z",
                "departments": [{"name": "Eng"}],
            }
        ]
    }


def _lever_payload() -> list:
    return [
        {
            "id": "abc-123",
            "text": "Staff PM",
            "hostedUrl": "https://jobs.lever.co/foo/abc-123",
            "categories": {"location": "NYC", "team": "Product"},
            "createdAt": 1_700_000_000_000,
        }
    ]


# ── Backoff + retry-status helpers ───────────────────────────────────


class TestBackoffMath:
    def test_attempt_zero_returns_zero(self) -> None:
        assert worker._backoff_seconds(0) == 0.0

    def test_attempt_one_two_four(self) -> None:
        assert worker._backoff_seconds(1) == 1.0
        assert worker._backoff_seconds(2) == 2.0
        assert worker._backoff_seconds(3) == 4.0

    def test_capped_at_max(self) -> None:
        # 1 * 2^9 = 512, capped at 8.
        assert worker._backoff_seconds(10) == worker._BACKOFF_MAX_SECONDS


class TestRetryableStatus:
    @pytest.mark.parametrize("code", [429, 500, 502, 503, 599])
    def test_retryable(self, code: int) -> None:
        assert worker._is_retryable_status(code) is True

    @pytest.mark.parametrize("code", [200, 301, 400, 401, 404, 410])
    def test_not_retryable(self, code: int) -> None:
        assert worker._is_retryable_status(code) is False


# ── _fetch_with_retry ────────────────────────────────────────────────


class TestFetchWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_try(self) -> None:
        plan = FetchPlan(provider="greenhouse", company_slug="acme", url="https://x")
        fetcher = AsyncMock(return_value=worker.FetchResult(status=200, payload=_gh_payload()))
        sleep = AsyncMock()
        result, failure = await worker._fetch_with_retry(plan, fetcher, sleep)
        assert failure is None
        assert result is not None and result.status == 200
        assert fetcher.await_count == 1
        sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_429_then_success(self) -> None:
        plan = FetchPlan(provider="lever", company_slug="foo", url="https://x")
        fetcher = AsyncMock(side_effect=[
            worker.FetchResult(status=429),
            worker.FetchResult(status=200, payload=_lever_payload()),
        ])
        sleep = AsyncMock()
        result, failure = await worker._fetch_with_retry(plan, fetcher, sleep)
        assert failure is None
        assert result is not None and result.status == 200
        assert fetcher.await_count == 2
        sleep.assert_awaited_once_with(1.0)

    @pytest.mark.asyncio
    async def test_permanent_404_short_circuits(self) -> None:
        plan = FetchPlan(provider="ashby", company_slug="x", url="https://x")
        fetcher = AsyncMock(return_value=worker.FetchResult(status=404))
        sleep = AsyncMock()
        result, failure = await worker._fetch_with_retry(plan, fetcher, sleep)
        assert result is None
        assert failure is not None
        assert failure.status == 404
        assert failure.reason == "http_404"
        assert failure.attempts == 1
        assert fetcher.await_count == 1
        sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transport_error_then_success(self) -> None:
        plan = FetchPlan(provider="workday", company_slug="x", url="https://x")
        fetcher = AsyncMock(side_effect=[
            worker.FetchError("connection reset"),
            worker.FetchResult(status=200, payload={"jobPostings": []}),
        ])
        sleep = AsyncMock()
        result, failure = await worker._fetch_with_retry(plan, fetcher, sleep)
        assert failure is None
        assert result is not None
        assert fetcher.await_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self) -> None:
        plan = FetchPlan(provider="greenhouse", company_slug="x", url="https://x")
        fetcher = AsyncMock(return_value=worker.FetchResult(status=503))
        sleep = AsyncMock()
        result, failure = await worker._fetch_with_retry(plan, fetcher, sleep)
        assert result is None
        assert failure is not None
        assert failure.attempts == worker._MAX_RETRIES
        assert failure.reason == "max_retries"
        assert failure.status == 503
        # Sleeps between attempts: MAX_RETRIES - 1 of them.
        assert sleep.await_count == worker._MAX_RETRIES - 1


# ── _scan_one parse-error path ───────────────────────────────────────


class TestScanOneParseError:
    @pytest.mark.asyncio
    async def test_parse_exception_becomes_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        plan = FetchPlan(provider="greenhouse", company_slug="acme", url="https://x")

        def _raise(*_: object, **__: object) -> list[JobPosting]:
            raise RuntimeError("parser blew up")

        monkeypatch.setattr(worker, "parse_payload", _raise)
        fetcher = AsyncMock(return_value=worker.FetchResult(status=200, payload=_gh_payload()))
        sem = asyncio.Semaphore(1)
        gsem = asyncio.Semaphore(1)
        postings, failure = await worker._scan_one(
            plan, fetcher, AsyncMock(), sem, gsem,
        )
        assert postings == []
        assert failure is not None
        assert failure.reason == "parse_error"
        assert failure.status == 200


# ── run_scan end-to-end ──────────────────────────────────────────────


class TestRunScan:
    @pytest.mark.asyncio
    async def test_empty_companies_returns_empty(self) -> None:
        out = await worker.run_scan([], fetcher=AsyncMock())
        assert out.plans_attempted == 0
        assert out.new_postings == ()
        assert out.failures == ()

    @pytest.mark.asyncio
    async def test_mixed_providers_aggregates_and_dedupes(self) -> None:
        companies = [
            TrackedCompany(provider="greenhouse", company_slug="acme"),
            TrackedCompany(provider="lever",      company_slug="foo"),
        ]

        async def _fetcher(url: str) -> worker.FetchResult:
            if "greenhouse" in url:
                return worker.FetchResult(status=200, payload=_gh_payload())
            if "lever" in url:
                return worker.FetchResult(status=200, payload=_lever_payload())
            return worker.FetchResult(status=404)

        out = await worker.run_scan(companies, fetcher=_fetcher, sleep=AsyncMock())
        assert out.plans_attempted == 2
        assert out.failures == ()
        assert len(out.new_postings) == 2
        slugs = {p.company_slug for p in out.new_postings}
        assert slugs == {"acme", "foo"}

    @pytest.mark.asyncio
    async def test_dedup_against_seen_canonicals(self) -> None:
        companies = [TrackedCompany(provider="greenhouse", company_slug="acme")]
        async def _fetcher(_: str) -> worker.FetchResult:
            return worker.FetchResult(status=200, payload=_gh_payload())

        # Pre-canonicalize the URL the parser will emit.
        from app.services.url_canonicalizer import canonicalize_url
        seen = [canonicalize_url("https://boards.greenhouse.io/acme/jobs/101")]

        out = await worker.run_scan(
            companies, fetcher=_fetcher,
            seen_url_canonicals=seen,
            sleep=AsyncMock(),
        )
        assert out.plans_attempted == 1
        assert out.new_postings == ()
        assert out.failures == ()

    @pytest.mark.asyncio
    async def test_one_failure_does_not_break_others(self) -> None:
        companies = [
            TrackedCompany(provider="greenhouse", company_slug="acme"),
            TrackedCompany(provider="lever",      company_slug="foo"),
        ]

        async def _fetcher(url: str) -> worker.FetchResult:
            if "greenhouse" in url:
                return worker.FetchResult(status=404)  # permanent
            return worker.FetchResult(status=200, payload=_lever_payload())

        out = await worker.run_scan(companies, fetcher=_fetcher, sleep=AsyncMock())
        assert out.plans_attempted == 2
        assert len(out.failures) == 1
        assert out.failures[0].provider == "greenhouse"
        assert out.failures[0].reason == "http_404"
        assert len(out.new_postings) == 1
        assert out.new_postings[0].company_slug == "foo"

    @pytest.mark.asyncio
    async def test_provider_concurrency_cap_honoured(self) -> None:
        # Eight greenhouse companies, cap of 2: max in-flight must be ≤2.
        companies = [
            TrackedCompany(provider="greenhouse", company_slug=f"co{i}")
            for i in range(8)
        ]
        in_flight = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def _fetcher(_: str) -> worker.FetchResult:
            nonlocal in_flight, max_seen
            async with lock:
                in_flight += 1
                max_seen = max(max_seen, in_flight)
            await asyncio.sleep(0.01)
            async with lock:
                in_flight -= 1
            return worker.FetchResult(status=200, payload=_gh_payload())

        out = await worker.run_scan(
            companies, fetcher=_fetcher,
            sleep=AsyncMock(),
            provider_concurrency={"greenhouse": 2},
            global_concurrency=8,
        )
        assert out.plans_attempted == 8
        assert max_seen <= 2

    @pytest.mark.asyncio
    async def test_workday_without_tenant_skipped(self) -> None:
        companies = [
            TrackedCompany(provider="workday", company_slug="x", workday_tenant=None),
        ]
        fetcher = AsyncMock()
        out = await worker.run_scan(companies, fetcher=fetcher, sleep=AsyncMock())
        assert out.plans_attempted == 0
        fetcher.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_within_batch_dedup_via_filter(self) -> None:
        # Two companies returning the same canonical URL → dedup picks one.
        companies = [
            TrackedCompany(provider="greenhouse", company_slug="acme"),
            TrackedCompany(provider="greenhouse", company_slug="acme2"),
        ]

        async def _fetcher(_: str) -> worker.FetchResult:
            return worker.FetchResult(status=200, payload=_gh_payload())

        out = await worker.run_scan(companies, fetcher=_fetcher, sleep=AsyncMock())
        # Both fetched, filter_new_postings dedupes within batch.
        assert out.plans_attempted == 2
        assert len(out.new_postings) == 1
