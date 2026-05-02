"""ATLAS v2 — Validation Swarm.

Cross-checks claims in a :class:`CandidateProfile` against external
zero-config sources. Returns a :class:`CandidateValidationReport`
with one :class:`CandidateValidationClaim` per check, each marked
``verified | unverified | conflicted``.

Three validators run in parallel (``asyncio.gather``):

1. **GitHubCommitValidator** — for skills the candidate claims
   AND has GitHub provenance for, confirms the language appears in
   their public repo languages mix. Does NOT re-fetch GitHub —
   relies on the provenance the fusion layer already attached so the
   swarm stays cheap and offline-friendly.

2. **DateConsistencyValidator** — pure-logic over
   ``profile.experience``: flags overlapping full-time roles and
   employment gaps > 6 months. No I/O.

3. **CompanyExistsValidator** — Wikidata
   ``wbsearchentities`` API per claimed company. Free, anonymous,
   no key. Treats network failure as ``unverified`` (NOT
   ``conflicted``) — absence of evidence ≠ evidence of absence.

Hard rules:
- Pure async, never raises (per-validator failures degrade to
  empty claim lists with a WARNING log).
- All HTTP I/O optional via injectable ``http_client=`` for hermetic
  unit tests.
- Stdlib ``%s`` logging, never kwargs structlog.
- Activation is the caller's choice — the swarm class is always
  importable; gating env flag (``ATLAS_VALIDATION_SWARM_ENABLED``)
  is checked at the wiring site (Slice 3.2), not here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ai_engine.agents.artifact_contracts import (
    CandidateProfile,
    CandidateValidationClaim,
    CandidateValidationReport,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

_DEFAULT_HTTP_TIMEOUT_S = 6.0
_GAP_THRESHOLD_MONTHS = 6
_WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
_WIKIDATA_USER_AGENT = "hirestack-ai/1.0 (+https://hirestack.ai)"
_MAX_COMPANIES_TO_CHECK = 10  # bounded to keep wall-clock predictable

# Common alias map — claim language vs. GitHub `repos.languages` keys.
# Conservative: only obvious 1:1 normalizations, no fuzzy matching
# (the skill_graph already covers semantic equivalence elsewhere).
_LANG_ALIASES: Dict[str, str] = {
    "node.js": "javascript",
    "nodejs": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "py": "python",
    "golang": "go",
    "c#": "csharp",
    "objective-c": "objective-c",
    "objc": "objective-c",
    "ecmascript": "javascript",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_lang(raw: str) -> str:
    s = (raw or "").strip().lower()
    return _LANG_ALIASES.get(s, s)


_DATE_PATTERNS: Tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y-%m",
    "%Y/%m",
    "%b %Y",
    "%B %Y",
    "%Y",
)


def _parse_date(raw: Any) -> Optional[datetime]:
    """Best-effort parse to a `datetime`; returns None on failure.

    Accepts strings or anything that already has `.year`/`.month`.
    "Present" / "current" / empty → None (caller decides what that means).
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    if s.lower() in {"present", "current", "now", "ongoing"}:
        return None
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # last-ditch: 4-digit year embedded
    m = re.search(r"\b(19|20)\d{2}\b", s)
    if m:
        try:
            return datetime(int(m.group(0)), 1, 1)
        except ValueError:
            return None
    return None


def _months_between(a: datetime, b: datetime) -> int:
    """Whole months between two datetimes (a <= b expected)."""
    return (b.year - a.year) * 12 + (b.month - a.month)


# ---------------------------------------------------------------------------
# Validator 1 — GitHub commit / language coverage
# ---------------------------------------------------------------------------

class GitHubCommitValidator:
    """Confirms claimed languages appear in the candidate's GitHub repos.

    Reads the provenance the fusion layer already attached to each
    skill (``CandidateSkill.source`` and the GitHub languages list
    cached on the profile). No network I/O — keeps the swarm fast.
    """

    name = "github_commits"

    async def validate(self, profile: CandidateProfile) -> List[CandidateValidationClaim]:
        if "github" not in (profile.sources_used or []):
            return []  # nothing to cross-check

        # Pull GitHub-provided languages from the profile's experience
        # blob (fusion layer stashes them under "github_languages").
        gh_langs = self._extract_github_languages(profile)
        if gh_langs is None:
            return []  # provenance present but no language map — skip

        gh_lang_set = {_normalize_lang(l) for l in gh_langs if l}

        out: List[CandidateValidationClaim] = []
        for sk in profile.skills:
            sources = [str(getattr(p, "source", "")).lower()
                       for p in (getattr(sk, "provenance", None) or [])]
            if not any("github" in s for s in sources):
                continue  # only validate skills GitHub claims to back
            norm = _normalize_lang(sk.name)
            if not norm:
                continue
            if norm in gh_lang_set:
                out.append(CandidateValidationClaim(
                    claim=f"GitHub repos use {sk.name}",
                    validator=self.name,
                    status="verified",
                    detail=f"language present in public repo mix",
                ))
            else:
                # Conflict: candidate's GitHub provenance claims this
                # skill but the actual repo language list doesn't show
                # it. Flag it.
                out.append(CandidateValidationClaim(
                    claim=f"GitHub repos use {sk.name}",
                    validator=self.name,
                    status="conflicted",
                    detail="skill cited from GitHub but not in repo language list",
                ))
        return out

    @staticmethod
    def _extract_github_languages(profile: CandidateProfile) -> Optional[List[str]]:
        """Find the languages list the fusion layer stashed.

        Looks in ``profile.experience`` for an entry tagged
        ``source="github"`` carrying a ``languages`` list, or a
        top-level ``github_languages`` key on any experience dict.
        """
        for exp in profile.experience or []:
            if not isinstance(exp, dict):
                continue
            if exp.get("source") == "github":
                langs = exp.get("languages")
                if isinstance(langs, list):
                    return [str(l) for l in langs]
            if isinstance(exp.get("github_languages"), list):
                return [str(l) for l in exp["github_languages"]]
        return None


# ---------------------------------------------------------------------------
# Validator 2 — date consistency (no overlaps, no big gaps)
# ---------------------------------------------------------------------------

class DateConsistencyValidator:
    """Pure-logic checker: no overlapping FT roles, no gaps > 6mo."""

    name = "date_consistency"

    async def validate(self, profile: CandidateProfile) -> List[CandidateValidationClaim]:
        # Build (start, end, label) for parseable entries.
        entries: List[Tuple[datetime, datetime, str]] = []
        for exp in profile.experience or []:
            if not isinstance(exp, dict):
                continue
            start = _parse_date(exp.get("start_date") or exp.get("start"))
            end = _parse_date(exp.get("end_date") or exp.get("end")) or datetime.now(timezone.utc).replace(tzinfo=None)
            if start is None:
                continue
            if end < start:
                continue
            label = str(exp.get("title") or exp.get("company") or "role")
            entries.append((start, end, label))

        if not entries:
            return []

        entries.sort(key=lambda t: t[0])

        out: List[CandidateValidationClaim] = []

        # Overlap check (only flag overlaps > 1 month — avoids
        # noise from end-of-month↔start-of-month transitions).
        for i in range(len(entries) - 1):
            s1, e1, l1 = entries[i]
            s2, e2, l2 = entries[i + 1]
            if s2 < e1 and _months_between(s2, e1) > 1:
                out.append(CandidateValidationClaim(
                    claim=f"Overlapping roles: '{l1}' and '{l2}'",
                    validator=self.name,
                    status="conflicted",
                    detail=(
                        f"{l1} ends {e1.date()} but {l2} starts {s2.date()} "
                        f"({_months_between(s2, e1)}mo overlap)"
                    ),
                ))

        # Gap check (gaps strictly > threshold).
        for i in range(len(entries) - 1):
            _, e1, l1 = entries[i]
            s2, _, l2 = entries[i + 1]
            if s2 > e1:
                gap = _months_between(e1, s2)
                if gap > _GAP_THRESHOLD_MONTHS:
                    out.append(CandidateValidationClaim(
                        claim=f"Employment gap between '{l1}' and '{l2}'",
                        validator=self.name,
                        status="unverified",
                        detail=f"{gap}mo gap ({e1.date()} → {s2.date()})",
                    ))

        # If we found nothing wrong, emit one verified summary claim
        # so downstream UI can show a green tick rather than silence.
        if not out and len(entries) >= 1:
            out.append(CandidateValidationClaim(
                claim="Employment timeline is consistent",
                validator=self.name,
                status="verified",
                detail=f"{len(entries)} role(s), no overlaps or large gaps",
            ))

        return out


# ---------------------------------------------------------------------------
# Validator 3 — company existence via Wikidata
# ---------------------------------------------------------------------------

class CompanyExistsValidator:
    """Confirms claimed companies exist as Wikidata entities."""

    name = "company_exists"

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        timeout_s: float = _DEFAULT_HTTP_TIMEOUT_S,
    ) -> None:
        self._client = http_client
        self._timeout_s = timeout_s

    async def validate(self, profile: CandidateProfile) -> List[CandidateValidationClaim]:
        companies = self._collect_companies(profile)
        if not companies:
            return []

        client, owns = await self._get_client()
        out: List[CandidateValidationClaim] = []
        try:
            sem = asyncio.Semaphore(4)  # polite to the API

            async def _check(company: str) -> CandidateValidationClaim:
                async with sem:
                    return await self._check_one(client, company)

            results = await asyncio.gather(
                *(_check(c) for c in companies), return_exceptions=True
            )
            for r in results:
                if isinstance(r, CandidateValidationClaim):
                    out.append(r)
                elif isinstance(r, Exception):
                    logger.warning("CompanyExistsValidator: per-company check raised: %s", r)
        finally:
            if owns and hasattr(client, "aclose"):
                try:
                    await client.aclose()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("CompanyExistsValidator client close failed: %s", exc)
        return out

    @staticmethod
    def _collect_companies(profile: CandidateProfile) -> List[str]:
        seen: List[str] = []
        seen_norm: set = set()
        for exp in profile.experience or []:
            if not isinstance(exp, dict):
                continue
            name = (exp.get("company") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen_norm:
                continue
            seen_norm.add(key)
            seen.append(name)
            if len(seen) >= _MAX_COMPANIES_TO_CHECK:
                break
        return seen

    async def _check_one(self, client: Any, company: str) -> CandidateValidationClaim:
        params = {
            "action": "wbsearchentities",
            "search": company,
            "language": "en",
            "type": "item",
            "format": "json",
            "limit": 1,
        }
        try:
            resp = await client.get(_WIKIDATA_API_URL, params=params)
        except Exception as exc:
            logger.warning("CompanyExistsValidator GET failed for %s: %s", company, exc)
            return CandidateValidationClaim(
                claim=f"Company exists: {company}",
                validator=self.name,
                status="unverified",
                detail=f"network error: {exc.__class__.__name__}",
            )

        status = getattr(resp, "status_code", 0)
        if status != 200:
            return CandidateValidationClaim(
                claim=f"Company exists: {company}",
                validator=self.name,
                status="unverified",
                detail=f"wikidata HTTP {status}",
            )
        try:
            payload = resp.json()
        except Exception as exc:
            logger.warning("CompanyExistsValidator JSON parse failed: %s", exc)
            return CandidateValidationClaim(
                claim=f"Company exists: {company}",
                validator=self.name,
                status="unverified",
                detail="wikidata returned non-JSON",
            )

        hits = payload.get("search") or [] if isinstance(payload, dict) else []
        if hits:
            hit = hits[0]
            qid = hit.get("id", "")
            label = hit.get("label", company)
            return CandidateValidationClaim(
                claim=f"Company exists: {company}",
                validator=self.name,
                status="verified",
                detail=f"matched wikidata entity {qid} ({label})",
            )
        return CandidateValidationClaim(
            claim=f"Company exists: {company}",
            validator=self.name,
            status="unverified",
            detail="no wikidata match",
        )

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        headers = {
            "User-Agent": _WIKIDATA_USER_AGENT,
            "Accept": "application/json",
        }
        return (
            httpx.AsyncClient(timeout=self._timeout_s, headers=headers),
            True,
        )


# ---------------------------------------------------------------------------
# Public swarm
# ---------------------------------------------------------------------------

class ValidationSwarm:
    """Fans out three zero-config validators in parallel."""

    def __init__(
        self,
        *,
        github_validator: Optional[GitHubCommitValidator] = None,
        date_validator: Optional[DateConsistencyValidator] = None,
        company_validator: Optional[CompanyExistsValidator] = None,
    ) -> None:
        # All injectable for hermetic tests; default to real instances.
        self._github = github_validator or GitHubCommitValidator()
        self._date = date_validator or DateConsistencyValidator()
        self._company = company_validator or CompanyExistsValidator()

    async def validate(self, profile: CandidateProfile) -> CandidateValidationReport:
        if profile is None:
            return CandidateValidationReport(
                created_by_agent="atlas.validation_swarm",
                claims=[],
                verified_count=0,
                conflicted_count=0,
            )

        t0 = time.perf_counter()
        results = await asyncio.gather(
            self._safe(self._github.validate(profile), self._github.name),
            self._safe(self._date.validate(profile), self._date.name),
            self._safe(self._company.validate(profile), self._company.name),
            return_exceptions=False,
        )

        claims: List[CandidateValidationClaim] = []
        for sub in results:
            claims.extend(sub)

        verified = sum(1 for c in claims if c.status == "verified")
        conflicted = sum(1 for c in claims if c.status == "conflicted")

        logger.info(
            "ValidationSwarm: %d claims (%d verified, %d conflicted) in %.2fs",
            len(claims), verified, conflicted, time.perf_counter() - t0,
        )

        return CandidateValidationReport(
            created_by_agent="atlas.validation_swarm",
            parent_artifact_ids=[],
            claims=claims,
            verified_count=verified,
            conflicted_count=conflicted,
        )

    @staticmethod
    async def _safe(coro, name: str) -> List[CandidateValidationClaim]:
        try:
            out = await coro
            return out or []
        except Exception as exc:
            logger.warning("ValidationSwarm validator %s raised: %s", name, exc)
            return []
