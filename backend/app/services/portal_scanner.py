"""B1 — portal_scanner (pure-function core).

PURE-FUNCTION fan-out + normalization for the six ATS platforms
HireStack already canonicalizes (Greenhouse, Lever, Ashby, Workday,
Workable, SmartRecruiters).  No HTTP, no cron, no ``job_scan_history``
read — those live in the B1.next worker slice.

This module answers two questions:

  1. Given a tracked company on a given ATS, **what URLs do I fetch?**
     ``plan_fetches(companies)`` → list of ``FetchPlan``.

  2. Given a fetched JSON payload from one of those URLs, **what
     normalized job postings do I store?**
     ``parse_*(payload, company)`` → list of ``JobPosting``.

Plus a stateless dedup helper that filters a candidate list against
a pre-fetched set of canonical URLs the caller already has in scan
history.

Why pure: the cron worker becomes a 30-line glue layer (fetch URL,
call parser, dedup, write rows) that is trivially testable.  The
hard logic — provider URL shapes, JSON layouts, missing fields,
canonicalization — is unit-tested without a network.

HARD RULES:
  * Workday's posting JSON shape varies per tenant; only fields that
    are universally present across observed tenants are extracted.
  * SmartRecruiters and Workable both expose public job-board APIs
    on subpaths of their ``api.smartrecruiters.com`` and
    ``apply.workable.com/api/v3/accounts/{company}/jobs`` hosts; we
    use the documented public endpoints, not the internal ones.
  * Every parser is *defensive*: a malformed item is skipped (logged
    by the worker), never crashes the whole batch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Literal, Mapping, Optional, Sequence

from app.services.url_canonicalizer import canonicalize_url, extract_ats_key

# ── Public types ──────────────────────────────────────────────────────

Provider = Literal[
    "greenhouse", "lever", "ashby", "workday", "workable", "smartrecruiters",
]

PROVIDERS: tuple[Provider, ...] = (
    "greenhouse", "lever", "ashby", "workday", "workable", "smartrecruiters",
)


@dataclass(frozen=True)
class TrackedCompany:
    """One company the user is watching on one ATS."""
    provider: Provider
    company_slug: str             # e.g. 'stripe', 'github', 'acme-corp'
    workday_tenant: Optional[str] = None  # workday only: e.g. 'acme.wd5'


@dataclass(frozen=True)
class FetchPlan:
    """Where to GET to enumerate one company's open postings.

    The worker performs the GET; this module never touches the network.
    """
    provider: Provider
    company_slug: str
    url: str


@dataclass(frozen=True)
class JobPosting:
    """Normalized open posting from any ATS provider.

    ``url_canonical`` is the URL after ``canonicalize_url`` — used as
    the dedup key against ``job_scan_history.url_canonical``.
    """
    provider: Provider
    company_slug: str
    external_id: str              # provider-side job id
    title: str
    location: Optional[str]
    url: str                      # raw apply URL
    url_canonical: str            # canonicalize_url(url)
    posted_at: Optional[datetime] # parsed ISO timestamp; None when unknown
    department: Optional[str] = None


# ── Fetch plan builders ──────────────────────────────────────────────


def _greenhouse_url(slug: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def _lever_url(slug: str) -> str:
    return f"https://api.lever.co/v0/postings/{slug}?mode=json"


def _ashby_url(slug: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false"


def _workday_url(tenant: str, slug: str) -> str:
    # Workday tenant URLs follow {tenant}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    # The board/site segment is the company_slug here.
    return (
        f"https://{tenant}.myworkdayjobs.com/wday/cxs/{tenant}/{slug}/jobs"
    )


def _workable_url(slug: str) -> str:
    return f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"


def _smartrecruiters_url(slug: str) -> str:
    return f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"


def plan_fetches(companies: Sequence[TrackedCompany]) -> list[FetchPlan]:
    """Build one ``FetchPlan`` per tracked company.

    Skips entries whose provider is unknown or which lack required
    fields (e.g. workday without ``workday_tenant``).
    """
    out: list[FetchPlan] = []
    for c in companies:
        if c.provider == "greenhouse":
            url = _greenhouse_url(c.company_slug)
        elif c.provider == "lever":
            url = _lever_url(c.company_slug)
        elif c.provider == "ashby":
            url = _ashby_url(c.company_slug)
        elif c.provider == "workday":
            if not c.workday_tenant:
                continue
            url = _workday_url(c.workday_tenant, c.company_slug)
        elif c.provider == "workable":
            url = _workable_url(c.company_slug)
        elif c.provider == "smartrecruiters":
            url = _smartrecruiters_url(c.company_slug)
        else:
            continue
        out.append(FetchPlan(provider=c.provider, company_slug=c.company_slug, url=url))
    return out


# ── Parsers ──────────────────────────────────────────────────────────


def _parse_iso(value: object) -> Optional[datetime]:
    """Best-effort ISO-8601 parse → tz-aware UTC. Returns None on failure."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        s = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _str_or_none(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    s = str(value).strip()
    return s or None


def _build_posting(
    *, provider: Provider, company_slug: str, external_id: str,
    title: str, url: str, location: Optional[str],
    posted_at: Optional[datetime], department: Optional[str] = None,
) -> Optional[JobPosting]:
    """Validate required fields; return None on missing essentials."""
    if not external_id or not title or not url:
        return None
    return JobPosting(
        provider=provider,
        company_slug=company_slug,
        external_id=str(external_id),
        title=title.strip(),
        location=location,
        url=url,
        url_canonical=canonicalize_url(url),
        posted_at=posted_at,
        department=department,
    )


def parse_greenhouse(payload: Mapping[str, object], company_slug: str) -> list[JobPosting]:
    """Greenhouse boards-api: ``{"jobs": [{id, title, absolute_url, location:{name}, updated_at, departments:[{name}]}]}``."""
    raw_jobs = payload.get("jobs") if isinstance(payload, Mapping) else None
    if not isinstance(raw_jobs, list):
        return []
    out: list[JobPosting] = []
    for j in raw_jobs:
        if not isinstance(j, Mapping):
            continue
        loc = j.get("location")
        loc_name = loc.get("name") if isinstance(loc, Mapping) else None
        depts = j.get("departments")
        dept_name = None
        if isinstance(depts, list) and depts and isinstance(depts[0], Mapping):
            dept_name = _str_or_none(depts[0].get("name"))
        posting = _build_posting(
            provider="greenhouse",
            company_slug=company_slug,
            external_id=str(j.get("id") or "").strip(),
            title=_str_or_none(j.get("title")) or "",
            url=_str_or_none(j.get("absolute_url")) or "",
            location=_str_or_none(loc_name),
            posted_at=_parse_iso(j.get("updated_at")),
            department=dept_name,
        )
        if posting:
            out.append(posting)
    return out


def parse_lever(payload: object, company_slug: str) -> list[JobPosting]:
    """Lever postings API returns a top-level JSON array.

    Each item: ``{id, text, hostedUrl, categories:{location, team}, createdAt}``.
    ``createdAt`` is epoch milliseconds.
    """
    if not isinstance(payload, list):
        return []
    out: list[JobPosting] = []
    for j in payload:
        if not isinstance(j, Mapping):
            continue
        cats = j.get("categories")
        location = team = None
        if isinstance(cats, Mapping):
            location = _str_or_none(cats.get("location"))
            team = _str_or_none(cats.get("team"))
        # createdAt is epoch ms in Lever; convert to ISO for _parse_iso path.
        created = j.get("createdAt")
        posted_at: Optional[datetime] = None
        if isinstance(created, (int, float)) and created > 0:
            try:
                posted_at = datetime.fromtimestamp(
                    float(created) / 1000.0, tz=timezone.utc
                )
            except (OverflowError, OSError, ValueError):
                posted_at = None
        posting = _build_posting(
            provider="lever",
            company_slug=company_slug,
            external_id=str(j.get("id") or "").strip(),
            title=_str_or_none(j.get("text")) or "",
            url=_str_or_none(j.get("hostedUrl")) or "",
            location=location,
            posted_at=posted_at,
            department=team,
        )
        if posting:
            out.append(posting)
    return out


def parse_ashby(payload: Mapping[str, object], company_slug: str) -> list[JobPosting]:
    """Ashby posting-api: ``{"jobs": [{id, title, jobUrl, locationName, publishedAt, departmentName}]}``."""
    raw_jobs = payload.get("jobs") if isinstance(payload, Mapping) else None
    if not isinstance(raw_jobs, list):
        return []
    out: list[JobPosting] = []
    for j in raw_jobs:
        if not isinstance(j, Mapping):
            continue
        posting = _build_posting(
            provider="ashby",
            company_slug=company_slug,
            external_id=str(j.get("id") or "").strip(),
            title=_str_or_none(j.get("title")) or "",
            url=_str_or_none(j.get("jobUrl")) or "",
            location=_str_or_none(j.get("locationName")),
            posted_at=_parse_iso(j.get("publishedAt")),
            department=_str_or_none(j.get("departmentName")),
        )
        if posting:
            out.append(posting)
    return out


def parse_workday(payload: Mapping[str, object], company_slug: str) -> list[JobPosting]:
    """Workday cxs jobs endpoint: ``{"jobPostings": [{title, externalPath, locationsText, postedOn, bulletFields}]}``.

    Workday URLs are tenant-scoped and ``externalPath`` is a relative
    path; the worker is responsible for prefixing the tenant host
    when persisting.  Here we keep the relative path verbatim so dedup
    against canonicalized full URLs still works after the worker
    normalizes them.
    """
    raw_jobs = payload.get("jobPostings") if isinstance(payload, Mapping) else None
    if not isinstance(raw_jobs, list):
        return []
    out: list[JobPosting] = []
    for j in raw_jobs:
        if not isinstance(j, Mapping):
            continue
        rel = _str_or_none(j.get("externalPath")) or ""
        if not rel:
            continue
        # external_id: trailing job id segment from externalPath.
        external_id = rel.rstrip("/").split("/")[-1] or rel
        posting = _build_posting(
            provider="workday",
            company_slug=company_slug,
            external_id=external_id,
            title=_str_or_none(j.get("title")) or "",
            url=rel,  # worker prefixes tenant host
            location=_str_or_none(j.get("locationsText")),
            posted_at=_parse_iso(j.get("postedOn")),
        )
        if posting:
            out.append(posting)
    return out


def parse_workable(payload: Mapping[str, object], company_slug: str) -> list[JobPosting]:
    """Workable v3 accounts/jobs: ``{"results": [{shortcode, title, url, location:{city,country}, published}]}``."""
    raw_jobs = payload.get("results") if isinstance(payload, Mapping) else None
    if not isinstance(raw_jobs, list):
        return []
    out: list[JobPosting] = []
    for j in raw_jobs:
        if not isinstance(j, Mapping):
            continue
        loc = j.get("location")
        loc_str = None
        if isinstance(loc, Mapping):
            city = _str_or_none(loc.get("city"))
            country = _str_or_none(loc.get("country"))
            loc_str = ", ".join(p for p in (city, country) if p) or None
        posting = _build_posting(
            provider="workable",
            company_slug=company_slug,
            external_id=str(j.get("shortcode") or j.get("id") or "").strip(),
            title=_str_or_none(j.get("title")) or "",
            url=_str_or_none(j.get("url")) or "",
            location=loc_str,
            posted_at=_parse_iso(j.get("published")),
            department=_str_or_none(j.get("department")),
        )
        if posting:
            out.append(posting)
    return out


def parse_smartrecruiters(payload: Mapping[str, object], company_slug: str) -> list[JobPosting]:
    """SmartRecruiters /v1/companies/{slug}/postings: ``{"content": [{id, name, ref, location:{city,country}, releasedDate, department:{label}}]}``."""
    raw_jobs = payload.get("content") if isinstance(payload, Mapping) else None
    if not isinstance(raw_jobs, list):
        return []
    out: list[JobPosting] = []
    for j in raw_jobs:
        if not isinstance(j, Mapping):
            continue
        loc = j.get("location")
        loc_str = None
        if isinstance(loc, Mapping):
            city = _str_or_none(loc.get("city"))
            country = _str_or_none(loc.get("country"))
            loc_str = ", ".join(p for p in (city, country) if p) or None
        dept = j.get("department")
        dept_label = _str_or_none(dept.get("label")) if isinstance(dept, Mapping) else None
        posting = _build_posting(
            provider="smartrecruiters",
            company_slug=company_slug,
            external_id=str(j.get("id") or "").strip(),
            title=_str_or_none(j.get("name")) or "",
            url=_str_or_none(j.get("ref")) or "",
            location=loc_str,
            posted_at=_parse_iso(j.get("releasedDate")),
            department=dept_label,
        )
        if posting:
            out.append(posting)
    return out


# ── Dispatch + dedup ─────────────────────────────────────────────────


_PARSERS: dict[Provider, object] = {
    "greenhouse":      parse_greenhouse,
    "lever":           parse_lever,
    "ashby":           parse_ashby,
    "workday":         parse_workday,
    "workable":        parse_workable,
    "smartrecruiters": parse_smartrecruiters,
}


def parse_payload(provider: Provider, payload: object, company_slug: str) -> list[JobPosting]:
    """Dispatch to the right per-provider parser."""
    fn = _PARSERS.get(provider)
    if fn is None:
        return []
    return fn(payload, company_slug)  # type: ignore[operator]


def filter_new_postings(
    postings: Sequence[JobPosting],
    *,
    seen_url_canonicals: Iterable[str],
) -> list[JobPosting]:
    """Drop postings whose canonical URL is already in scan history.

    The caller supplies ``seen_url_canonicals`` (typically a SELECT of
    ``url_canonical FROM job_scan_history WHERE company_slug=ANY(...)``).
    Within the input batch, also dedupes by ``url_canonical`` so two
    feeds yielding the same posting only emit once.
    """
    seen: set[str] = {u for u in seen_url_canonicals if u}
    out: list[JobPosting] = []
    for p in postings:
        if not p.url_canonical or p.url_canonical in seen:
            continue
        seen.add(p.url_canonical)
        out.append(p)
    return out


__all__ = [
    "Provider", "PROVIDERS",
    "TrackedCompany", "FetchPlan", "JobPosting",
    "plan_fetches",
    "parse_greenhouse", "parse_lever", "parse_ashby",
    "parse_workday", "parse_workable", "parse_smartrecruiters",
    "parse_payload", "filter_new_postings",
]
