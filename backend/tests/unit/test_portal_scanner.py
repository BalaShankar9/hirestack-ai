"""B1 — portal_scanner unit tests.

Pure-function core (no HTTP). Coverage:
  * plan_fetches: per-provider URL shape, workday-without-tenant skip,
    unknown provider skip, preserves order.
  * Each parse_* honors documented JSON shape, skips malformed items,
    returns empty list on wrong-shape root.
  * canonicalize_url is wired (tracking params stripped from posting URL).
  * filter_new_postings: scan-history dedup, in-batch dedup, empty
    canonical drop.
  * parse_payload dispatches correctly + unknown provider returns [].
  * Determinism + input immutability.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.portal_scanner import (
    PROVIDERS,
    FetchPlan,
    JobPosting,
    TrackedCompany,
    filter_new_postings,
    parse_ashby,
    parse_greenhouse,
    parse_lever,
    parse_payload,
    parse_smartrecruiters,
    parse_workable,
    parse_workday,
    plan_fetches,
)


# ── plan_fetches ─────────────────────────────────────────────────────


def test_plan_fetches_greenhouse_url_shape() -> None:
    plans = plan_fetches([TrackedCompany(provider="greenhouse", company_slug="stripe")])
    assert plans == [FetchPlan(
        provider="greenhouse", company_slug="stripe",
        url="https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true",
    )]


def test_plan_fetches_lever_url_shape() -> None:
    plans = plan_fetches([TrackedCompany(provider="lever", company_slug="netflix")])
    assert plans[0].url == "https://api.lever.co/v0/postings/netflix?mode=json"


def test_plan_fetches_ashby_url_shape() -> None:
    plans = plan_fetches([TrackedCompany(provider="ashby", company_slug="ramp")])
    assert plans[0].url.startswith("https://api.ashbyhq.com/posting-api/job-board/ramp")


def test_plan_fetches_workday_url_includes_tenant_and_site() -> None:
    plans = plan_fetches([TrackedCompany(
        provider="workday", company_slug="External", workday_tenant="acme.wd5",
    )])
    assert plans[0].url == "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme.wd5/External/jobs"


def test_plan_fetches_workday_without_tenant_is_skipped() -> None:
    plans = plan_fetches([TrackedCompany(provider="workday", company_slug="x")])
    assert plans == []


def test_plan_fetches_workable_url_shape() -> None:
    plans = plan_fetches([TrackedCompany(provider="workable", company_slug="acme")])
    assert plans[0].url == "https://apply.workable.com/api/v3/accounts/acme/jobs"


def test_plan_fetches_smartrecruiters_url_shape() -> None:
    plans = plan_fetches([TrackedCompany(provider="smartrecruiters", company_slug="hooli")])
    assert plans[0].url == "https://api.smartrecruiters.com/v1/companies/hooli/postings"


def test_plan_fetches_unknown_provider_is_skipped() -> None:
    bogus = TrackedCompany.__new__(TrackedCompany)
    object.__setattr__(bogus, "provider", "myspace")
    object.__setattr__(bogus, "company_slug", "tom")
    object.__setattr__(bogus, "workday_tenant", None)
    plans = plan_fetches([bogus])
    assert plans == []


def test_plan_fetches_preserves_input_order() -> None:
    plans = plan_fetches([
        TrackedCompany(provider="lever", company_slug="a"),
        TrackedCompany(provider="greenhouse", company_slug="b"),
        TrackedCompany(provider="ashby", company_slug="c"),
    ])
    assert [p.company_slug for p in plans] == ["a", "b", "c"]


def test_plan_fetches_covers_all_providers() -> None:
    plans = plan_fetches([
        TrackedCompany(provider=p, company_slug="x",
                       workday_tenant=("t" if p == "workday" else None))
        for p in PROVIDERS
    ])
    assert {p.provider for p in plans} == set(PROVIDERS)


# ── Greenhouse parser ────────────────────────────────────────────────


def test_parse_greenhouse_happy_path() -> None:
    payload = {"jobs": [{
        "id": 12345, "title": " Senior Engineer ",
        "absolute_url": "https://boards.greenhouse.io/stripe/jobs/12345?utm_source=ref",
        "location": {"name": "Remote"},
        "departments": [{"name": "Engineering"}],
        "updated_at": "2026-05-01T12:34:56Z",
    }]}
    out = parse_greenhouse(payload, "stripe")
    assert len(out) == 1
    p = out[0]
    assert p.provider == "greenhouse"
    assert p.company_slug == "stripe"
    assert p.external_id == "12345"
    assert p.title == "Senior Engineer"
    assert p.location == "Remote"
    assert p.department == "Engineering"
    # tracking param stripped via canonicalize_url
    assert "utm_source" not in p.url_canonical
    assert p.posted_at == datetime(2026, 5, 1, 12, 34, 56, tzinfo=timezone.utc)


def test_parse_greenhouse_missing_jobs_returns_empty() -> None:
    assert parse_greenhouse({}, "stripe") == []
    assert parse_greenhouse({"jobs": "not a list"}, "stripe") == []
    assert parse_greenhouse("not a dict", "stripe") == []  # type: ignore[arg-type]


def test_parse_greenhouse_skips_items_without_required_fields() -> None:
    payload = {"jobs": [
        {"id": 1, "title": "ok", "absolute_url": "https://x/j/1"},  # OK
        {"id": "", "title": "no id", "absolute_url": "https://x/j/2"},  # bad
        {"id": 3, "title": "", "absolute_url": "https://x/j/3"},  # bad
        {"id": 4, "title": "no url", "absolute_url": ""},  # bad
        "not a dict",  # bad
    ]}
    out = parse_greenhouse(payload, "x")
    assert len(out) == 1
    assert out[0].external_id == "1"


# ── Lever parser ─────────────────────────────────────────────────────


def test_parse_lever_happy_path_with_epoch_ms() -> None:
    payload = [{
        "id": "abc-123", "text": "Staff Engineer",
        "hostedUrl": "https://jobs.lever.co/netflix/abc-123",
        "categories": {"location": "Los Gatos", "team": "Platform"},
        "createdAt": 1746100000000,  # 2025-05-01-ish
    }]
    out = parse_lever(payload, "netflix")
    assert len(out) == 1
    p = out[0]
    assert p.external_id == "abc-123"
    assert p.title == "Staff Engineer"
    assert p.location == "Los Gatos"
    assert p.department == "Platform"
    assert p.posted_at is not None
    assert p.posted_at.tzinfo is timezone.utc


def test_parse_lever_top_level_must_be_list() -> None:
    assert parse_lever({"jobs": []}, "x") == []
    assert parse_lever(None, "x") == []


def test_parse_lever_handles_missing_categories() -> None:
    payload = [{"id": "1", "text": "Eng", "hostedUrl": "https://x/j/1"}]
    out = parse_lever(payload, "x")
    assert out[0].location is None
    assert out[0].department is None
    assert out[0].posted_at is None


# ── Ashby parser ─────────────────────────────────────────────────────


def test_parse_ashby_happy_path() -> None:
    payload = {"jobs": [{
        "id": "uuid-1", "title": "PM",
        "jobUrl": "https://jobs.ashbyhq.com/ramp/uuid-1",
        "locationName": "NYC",
        "departmentName": "Product",
        "publishedAt": "2026-04-30T08:00:00Z",
    }]}
    out = parse_ashby(payload, "ramp")
    assert len(out) == 1
    p = out[0]
    assert p.external_id == "uuid-1"
    assert p.location == "NYC"
    assert p.department == "Product"


def test_parse_ashby_empty_payload() -> None:
    assert parse_ashby({}, "x") == []


# ── Workday parser ───────────────────────────────────────────────────


def test_parse_workday_happy_path_uses_external_path() -> None:
    payload = {"jobPostings": [{
        "title": "Senior Engineer",
        "externalPath": "/job/Remote/Senior-Engineer_R-1234",
        "locationsText": "Remote, USA",
        "postedOn": "2026-04-29T00:00:00Z",
    }]}
    out = parse_workday(payload, "External")
    assert len(out) == 1
    p = out[0]
    # external_id is the trailing segment
    assert p.external_id == "Senior-Engineer_R-1234"
    assert p.url == "/job/Remote/Senior-Engineer_R-1234"
    assert p.location == "Remote, USA"


def test_parse_workday_skips_items_without_external_path() -> None:
    payload = {"jobPostings": [
        {"title": "x", "externalPath": ""},
        {"title": "y"},
    ]}
    assert parse_workday(payload, "x") == []


# ── Workable parser ──────────────────────────────────────────────────


def test_parse_workable_happy_path_combines_city_country() -> None:
    payload = {"results": [{
        "shortcode": "ABCD1234", "title": "DevOps",
        "url": "https://apply.workable.com/acme/j/ABCD1234",
        "location": {"city": "Austin", "country": "USA"},
        "department": "Infra",
        "published": "2026-04-28T10:00:00Z",
    }]}
    out = parse_workable(payload, "acme")
    assert len(out) == 1
    p = out[0]
    assert p.external_id == "ABCD1234"
    assert p.location == "Austin, USA"
    assert p.department == "Infra"


def test_parse_workable_handles_partial_location() -> None:
    payload = {"results": [{
        "shortcode": "X", "title": "Eng", "url": "https://x/j",
        "location": {"city": "Berlin"},
    }]}
    assert parse_workable(payload, "x")[0].location == "Berlin"


# ── SmartRecruiters parser ───────────────────────────────────────────


def test_parse_smartrecruiters_happy_path() -> None:
    payload = {"content": [{
        "id": "sr-1", "name": "Eng Manager",
        "ref": "https://careers.smartrecruiters.com/Hooli/eng-manager",
        "location": {"city": "Palo Alto", "country": "USA"},
        "department": {"label": "Engineering"},
        "releasedDate": "2026-04-27T15:00:00Z",
    }]}
    out = parse_smartrecruiters(payload, "hooli")
    assert len(out) == 1
    p = out[0]
    assert p.title == "Eng Manager"
    assert p.location == "Palo Alto, USA"
    assert p.department == "Engineering"


def test_parse_smartrecruiters_missing_content_returns_empty() -> None:
    assert parse_smartrecruiters({}, "x") == []


# ── Dispatch ─────────────────────────────────────────────────────────


def test_parse_payload_dispatches_to_correct_parser() -> None:
    payload = {"jobs": [{
        "id": 1, "title": "x",
        "absolute_url": "https://boards.greenhouse.io/x/jobs/1",
    }]}
    out = parse_payload("greenhouse", payload, "x")
    assert len(out) == 1
    assert out[0].provider == "greenhouse"


def test_parse_payload_unknown_provider_returns_empty() -> None:
    assert parse_payload("myspace", {"jobs": []}, "x") == []  # type: ignore[arg-type]


# ── filter_new_postings ──────────────────────────────────────────────


def _posting(url: str, ext_id: str = "1", provider="greenhouse", slug="x") -> JobPosting:
    from app.services.url_canonicalizer import canonicalize_url
    return JobPosting(
        provider=provider, company_slug=slug, external_id=ext_id, title="t",
        location=None, url=url, url_canonical=canonicalize_url(url),
        posted_at=None,
    )


def test_filter_new_postings_drops_seen_canonicals() -> None:
    p1 = _posting("https://x/j/1", "1")
    p2 = _posting("https://x/j/2", "2")
    out = filter_new_postings([p1, p2], seen_url_canonicals=[p1.url_canonical])
    assert [p.external_id for p in out] == ["2"]


def test_filter_new_postings_dedupes_within_batch() -> None:
    a = _posting("https://x/j/1?utm_source=a", "1")
    b = _posting("https://x/j/1?utm_source=b", "2")  # same canonical after strip
    assert a.url_canonical == b.url_canonical
    out = filter_new_postings([a, b], seen_url_canonicals=[])
    assert len(out) == 1
    assert out[0].external_id == "1"  # first wins


def test_filter_new_postings_drops_empty_canonical() -> None:
    bogus = JobPosting(
        provider="greenhouse", company_slug="x", external_id="1", title="t",
        location=None, url="", url_canonical="", posted_at=None,
    )
    assert filter_new_postings([bogus], seen_url_canonicals=[]) == []


def test_filter_new_postings_handles_empty_inputs() -> None:
    assert filter_new_postings([], seen_url_canonicals=[]) == []
    assert filter_new_postings([], seen_url_canonicals=["a", "b"]) == []


# ── Determinism / immutability ───────────────────────────────────────


def test_parse_greenhouse_is_deterministic() -> None:
    payload = {"jobs": [{"id": 1, "title": "t", "absolute_url": "https://x/j/1"}]}
    a = parse_greenhouse(payload, "x")
    b = parse_greenhouse(payload, "x")
    assert a == b


def test_filter_does_not_mutate_inputs() -> None:
    p = _posting("https://x/j/1", "1")
    postings = [p]
    seen = {"https://x/j/2"}
    snap_postings = list(postings)
    snap_seen = set(seen)
    filter_new_postings(postings, seen_url_canonicals=seen)
    assert postings == snap_postings
    assert seen == snap_seen
