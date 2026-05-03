# HireStack AI — Career-Ops Integration Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. Execute one sprint at a time, one task at a time. TDD: test first, fail, implement, pass, commit.

**Goal:** Merge every valuable innovation from `reference/career-ops/` into HireStack AI as native features across existing surfaces (Job Board, New Application, Workspace, Evidence Vault, Analytics, Career Nexus, Career Lab). Ship a public Ghost-Job Radar as a viral acquisition tool. Bake the "fewer, better" anti-spray philosophy into the product.

**Non-goals:** Don't duplicate career-ops's CLI/TUI/markdown-as-DB architecture. Don't add net-new sidebar entries that feel grafted-on — every feature lands on an existing page.

**Architecture:** All 20+ career-ops features map to existing HireStack surfaces via extensions to current chains, routes, and pages. One consolidated DB migration. Celery-style scheduled jobs via the existing Redis Streams worker (`backend/app/worker.py`). Public endpoints added under a new `/api/public/*` prefix with strict rate-limiting.

**Reference source:** `reference/career-ops/` (read-only reference clone — don't edit).

**Existing context to preserve:**
- `applications.status VARCHAR(50) DEFAULT 'draft'` — free-text, don't break existing data. Introduce `status_canonical` alongside.
- `applications.scorecard JSONB` — already used by agent pipeline. A–G blocks go in a new `scorecard_ag JSONB` column.
- Worker is Redis Streams, not Celery. Follow-up scheduling uses a Postgres `scheduled_for` + beat-style poller we add to the worker.
- RLS pattern uses `DO $$ BEGIN CREATE POLICY ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;`.
- Routes are aggregated in `backend/app/api/routes/__init__.py` — every new router must be included there.

**Tech:** Python 3.11+ / FastAPI / asyncio / Pydantic / Supabase (Postgres + RLS) / Redis Streams / Next.js 14 / TypeScript / Tailwind / shadcn/ui / Chrome MV3 extension.

---

## Sprint Overview

| Sprint | Theme | Ships | Duration |
|--------|-------|-------|----------|
| 1 | **Trust Layer** | Ghost-Job Detector, Public `/ghost-check`, Anti-Spray Gate, Canonical States, Scan History | Week 1–2 |
| 2 | **Retention Loop** | Follow-up Cadence Tracker, 4 draft templates, Weekly "Career Ops Report" email | Week 3–4 |
| 3 | **Signal Layer** | Rejection Pattern Detector, A–G Scorecard tab, 6 Archetype Presets | Week 5–6 |
| 4 | **Voice & Quality** | Story Bank with STAR+R, Writing Samples UX, "I'm Choosing You" tone directive, Professional Writing blocklist, Evidence Vault split (Proof Points + Artifacts) | Week 7–8 |
| 5 | **Power Tools** | Batch Evaluation, LinkedIn Contact-Type Framework, Deep Research 6-axis prompt merge, Training/Project ROI evaluator | Week 9–10 |
| 6 | **Distribution** | Chrome Extension + Live Apply, Shareable Outcome Cards, Public Benchmarks, Brand/Landing rewrite | Week 11–12 |

Each sprint is independently shippable. Ghost Radar (Sprint 1) is the viral hook — prioritize it.

---

## Sprint 1 — Trust Layer

Delivers: Ghost-Job Detector chain, public `/ghost-check` landing page, `/api/public/ghost-check` unauth endpoint, anti-spray score gate in Workspace, canonical status enum, scan-history table.

### File Structure (Sprint 1)

```
ai_engine/chains/
├── posting_legitimacy.py                    # NEW — Block G signal scoring
└── prompts/
    └── posting_legitimacy_system.md         # NEW

backend/app/
├── api/routes/
│   ├── public.py                            # NEW — unauth ghost-check, rate-limited
│   └── intel.py                             # EDIT — add /legitimacy endpoint
├── services/
│   ├── scan_history_service.py              # NEW — dedup + repost detection
│   └── url_canonicalizer.py                 # NEW — normalize URLs for dedup
└── core/
    └── rate_limit.py                        # EDIT — add per-IP ghost-check bucket

frontend/src/
├── app/
│   ├── ghost-check/                         # NEW — public viral landing page
│   │   ├── page.tsx
│   │   ├── layout.tsx
│   │   └── components/
│   │       ├── url-input.tsx
│   │       ├── result-card.tsx
│   │       ├── signals-table.tsx
│   │       └── share-buttons.tsx
│   └── (dashboard)/
│       ├── job-board/                       # EDIT — add legitimacy badges
│       ├── new/                             # EDIT — intake gate
│       └── applications/[id]/               # EDIT — anti-spray button state
├── components/
│   └── legitimacy/
│       ├── legitimacy-badge.tsx             # NEW — reusable badge
│       └── legitimacy-tooltip.tsx           # NEW
└── lib/
    └── api/public.ts                        # NEW — public API client

backend/tests/unit/
└── test_chains/
    ├── test_posting_legitimacy.py           # NEW
    └── test_scan_history.py                 # NEW

supabase/migrations/
└── 20260502000000_career_ops_integration.sql # NEW — the ONE consolidated migration
```

---

### Task 1.1: Consolidated DB Migration

**File:** `supabase/migrations/20260502000000_career_ops_integration.sql`

This is the single source of truth for *all* 6 sprints of schema changes. Apply once; every feature references its tables.

- [ ] **Step 1: Write the migration**

See the full SQL in `supabase/migrations/20260502000000_career_ops_integration.sql` (co-authored with this plan). Key tables:
- `applications.status_canonical`, `legitimacy_tier`, `legitimacy_signals`, `archetype_preset`, `scorecard_ag` (added columns)
- `job_scan_history` (ghost detection — repost signal)
- `application_followups` (Sprint 2)
- `story_bank` (Sprint 4)
- `archetype_presets` + seed data (Sprint 3)
- `writing_samples` (Sprint 4)
- `proof_points` (Sprint 4)
- `public_ghost_scans` (Sprint 1 — anonymized aggregation for weekly index)

- [ ] **Step 2: Dry-run against Supabase local**

```bash
cd "/Users/balabollineni/HireStack AI"
supabase db reset --local --no-seed  # then apply all migrations
# or (safer, non-destructive):
supabase db diff --file career_ops_check
```

Expected: no errors, all new tables visible.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260502000000_career_ops_integration.sql
git commit -m "feat(db): career-ops integration — ghost detection, followups, story bank, archetype presets"
```

---

### Task 1.2: URL Canonicalizer Service

**Files:**
- Create `backend/app/services/url_canonicalizer.py`
- Create `backend/tests/unit/test_services/test_url_canonicalizer.py`

Canonicalize URLs so we can detect reposts and dedupe scans. `boards.greenhouse.io/acme/jobs/12345?utm_source=x` → `boards.greenhouse.io/acme/jobs/12345`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/unit/test_services/test_url_canonicalizer.py
import pytest
from app.services.url_canonicalizer import canonicalize_url, extract_ats_key


def test_strips_utm_parameters():
    url = "https://boards.greenhouse.io/acme/jobs/12345?utm_source=linkedin&utm_medium=feed"
    assert canonicalize_url(url) == "https://boards.greenhouse.io/acme/jobs/12345"


def test_preserves_non_tracking_params():
    url = "https://jobs.lever.co/acme/abc123?team=eng"
    assert canonicalize_url(url) == "https://jobs.lever.co/acme/abc123?team=eng"


def test_lowercases_scheme_and_host():
    url = "HTTPS://Jobs.Ashbyhq.com/Acme/xyz"
    assert canonicalize_url(url) == "https://jobs.ashbyhq.com/Acme/xyz"


def test_strips_trailing_slash():
    url = "https://boards.greenhouse.io/acme/jobs/123/"
    assert canonicalize_url(url) == "https://boards.greenhouse.io/acme/jobs/123"


def test_extracts_greenhouse_job_id():
    url = "https://boards.greenhouse.io/acme/jobs/4987123"
    key = extract_ats_key(url)
    assert key == ("greenhouse", "acme", "4987123")


def test_extracts_lever_key():
    url = "https://jobs.lever.co/acme/abc-123-def"
    assert extract_ats_key(url) == ("lever", "acme", "abc-123-def")


def test_extracts_ashby_key():
    url = "https://jobs.ashbyhq.com/acme/7fbd3a9e-123"
    assert extract_ats_key(url) == ("ashby", "acme", "7fbd3a9e-123")


def test_unknown_url_returns_none():
    assert extract_ats_key("https://example.com/careers") is None
```

- [ ] **Step 2: Run test to see it fail**

```bash
cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_services/test_url_canonicalizer.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'app.services.url_canonicalizer'`

- [ ] **Step 3: Implement**

```python
# backend/app/services/url_canonicalizer.py
"""URL canonicalization for job-posting dedup and repost detection.

Strips tracking parameters, normalizes scheme/host case, removes trailing
slashes, and extracts (platform, company, job_id) tuples from known ATS URLs.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "gh_jid", "gclid", "fbclid", "mc_cid", "mc_eid",
    "ref", "referrer", "source", "src",
}

_ATS_PATTERNS = [
    # (platform, regex, group_names)
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/([^/]+)/jobs/(\d+)"), ("company", "job_id")),
    ("lever", re.compile(r"jobs\.lever\.co/([^/]+)/([^/?#]+)"), ("company", "job_id")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([^/?#]+)"), ("company", "job_id")),
    ("workday", re.compile(r"([^.]+)\.myworkdayjobs\.com/[^/]+/job/[^/]+/([^/?#]+)"), ("company", "job_id")),
    ("workable", re.compile(r"apply\.workable\.com/([^/]+)/j/([^/?#]+)"), ("company", "job_id")),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com/([^/]+)/([^/?#]+)"), ("company", "job_id")),
]


def canonicalize_url(url: str) -> str:
    """Normalize URL: lowercase host/scheme, strip tracking params, strip trailing slash."""
    if not url:
        return url
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path
    # Strip tracking params
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() not in _TRACKING_PARAMS]
    query = urlencode(kept)
    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_ats_key(url: str) -> Optional[tuple[str, str, str]]:
    """Return (platform, company, job_id) if URL matches a known ATS pattern."""
    if not url:
        return None
    for platform, pattern, _ in _ATS_PATTERNS:
        m = pattern.search(url)
        if m:
            return (platform, m.group(1), m.group(2))
    return None
```

- [ ] **Step 4: Run tests to see them pass**

```bash
cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_services/test_url_canonicalizer.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/url_canonicalizer.py backend/tests/unit/test_services/test_url_canonicalizer.py
git commit -m "feat(services): URL canonicalizer for ATS dedup and repost detection"
```

---

### Task 1.3: Scan History Service

**Files:**
- Create `backend/app/services/scan_history_service.py`
- Create `backend/tests/unit/test_services/test_scan_history_service.py`

Persist every scanned URL to `job_scan_history`; return `times_seen` and days-since-first-seen for the reposting signal.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/unit/test_services/test_scan_history_service.py
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta
from app.services.scan_history_service import ScanHistoryService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.table = MagicMock(return_value=db)
    db.select = MagicMock(return_value=db)
    db.insert = MagicMock(return_value=db)
    db.upsert = MagicMock(return_value=db)
    db.update = MagicMock(return_value=db)
    db.eq = MagicMock(return_value=db)
    db.execute = MagicMock(return_value=MagicMock(data=[]))
    return db


def test_first_scan_creates_entry(mock_db):
    mock_db.execute = MagicMock(return_value=MagicMock(data=[]))
    svc = ScanHistoryService(mock_db)
    result = svc.record_scan("https://boards.greenhouse.io/acme/jobs/123",
                             company_slug="acme", role_title="AI Engineer")
    assert result["times_seen"] == 1
    assert result["is_repost"] is False


def test_subsequent_scan_increments(mock_db):
    existing = {
        "id": "scan-1",
        "url_canonical": "https://boards.greenhouse.io/acme/jobs/123",
        "times_seen": 1,
        "first_seen": (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
        "last_seen": (datetime.now(timezone.utc) - timedelta(days=50)).isoformat(),
    }
    mock_db.execute = MagicMock(return_value=MagicMock(data=[existing]))
    svc = ScanHistoryService(mock_db)
    result = svc.record_scan("https://boards.greenhouse.io/acme/jobs/123",
                             company_slug="acme", role_title="AI Engineer")
    assert result["times_seen"] == 2
    assert result["is_repost"] is True  # 2+ seen AND >= 90d span
    assert result["days_span"] >= 90


def test_reposting_requires_both_multiple_seen_and_90d_span(mock_db):
    # Seen 3 times but all within 30 days — not a repost
    existing = {
        "id": "scan-2",
        "url_canonical": "https://jobs.lever.co/acme/abc",
        "times_seen": 3,
        "first_seen": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(),
        "last_seen": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
    }
    mock_db.execute = MagicMock(return_value=MagicMock(data=[existing]))
    svc = ScanHistoryService(mock_db)
    result = svc.record_scan("https://jobs.lever.co/acme/abc",
                             company_slug="acme", role_title="PM")
    assert result["is_repost"] is False


def test_strips_tracking_before_store(mock_db):
    svc = ScanHistoryService(mock_db)
    svc.record_scan("https://boards.greenhouse.io/acme/jobs/123?utm_source=x",
                    company_slug="acme", role_title="Eng")
    upsert_call = mock_db.upsert.call_args
    stored = upsert_call[0][0]
    assert stored["url_canonical"] == "https://boards.greenhouse.io/acme/jobs/123"
```

- [ ] **Step 2: Run test to fail**

```bash
cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_services/test_scan_history_service.py -v 2>&1 | head
```

- [ ] **Step 3: Implement**

```python
# backend/app/services/scan_history_service.py
"""Scan-history service: dedup + repost detection for ghost-job signal."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from app.services.url_canonicalizer import canonicalize_url

logger = structlog.get_logger("hirestack.scan_history")

_REPOST_MIN_SEEN = 2
_REPOST_MIN_DAYS_SPAN = 90


class ScanHistoryService:
    def __init__(self, db):
        self.db = db

    def record_scan(
        self, url: str, company_slug: str, role_title: str
    ) -> dict[str, Any]:
        canonical = canonicalize_url(url)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check existing
        result = (
            self.db.table("job_scan_history")
            .select("*")
            .eq("url_canonical", canonical)
            .execute()
        )
        existing = (result.data or [None])[0]

        if existing:
            times_seen = int(existing["times_seen"]) + 1
            first_seen = existing["first_seen"]
            try:
                first_dt = datetime.fromisoformat(str(first_seen).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                first_dt = datetime.now(timezone.utc)
            days_span = (datetime.now(timezone.utc) - first_dt).days
            self.db.table("job_scan_history").update({
                "last_seen": now_iso,
                "times_seen": times_seen,
            }).eq("id", existing["id"]).execute()
            is_repost = times_seen >= _REPOST_MIN_SEEN and days_span >= _REPOST_MIN_DAYS_SPAN
            return {
                "times_seen": times_seen,
                "first_seen": first_seen,
                "last_seen": now_iso,
                "days_span": days_span,
                "is_repost": is_repost,
            }

        # New entry
        self.db.table("job_scan_history").upsert({
            "url_canonical": canonical,
            "company_slug": company_slug.lower() if company_slug else "unknown",
            "role_title": role_title or "",
            "first_seen": now_iso,
            "last_seen": now_iso,
            "times_seen": 1,
        }, on_conflict="url_canonical").execute()
        return {
            "times_seen": 1,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "days_span": 0,
            "is_repost": False,
        }
```

- [ ] **Step 4: Run tests to pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scan_history_service.py backend/tests/unit/test_services/test_scan_history_service.py
git commit -m "feat(services): scan history service with repost detection"
```

---

### Task 1.4: Posting Legitimacy Chain

**Files:**
- Create `ai_engine/chains/posting_legitimacy.py`
- Create `ai_engine/chains/prompts/posting_legitimacy_system.md`
- Create `backend/tests/unit/test_chains/test_posting_legitimacy.py`

Implements career-ops Block G. Input: JD text + URL + optional page metadata. Output: `LegitimacyReport` with tier + signal table.

- [ ] **Step 1: Write the system prompt**

Create `ai_engine/chains/prompts/posting_legitimacy_system.md` with the full ethical framing + signals table from `reference/career-ops/modes/_shared.md` (Posting Legitimacy section):

- The three tiers (`high_confidence` / `caution` / `suspicious`)
- The weighted signal table (posting age, apply button state, JD specificity, requirements realism, layoff news, reposting pattern, salary transparency, role-company fit)
- Edge-case handling (government, evergreen, niche/exec, startup, no date, recruiter-sourced)
- Mandatory ethical framing: "present signals, not accusations"
- Output JSON schema matching `LegitimacyReport` below

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/unit/test_chains/test_posting_legitimacy.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_engine.chains.posting_legitimacy import (
    PostingLegitimacyChain, LegitimacyReport, Signal, LegitimacyTier,
)


@pytest.fixture
def mock_client():
    c = MagicMock()
    c.complete_json = AsyncMock()
    return c


def test_legitimacy_report_schema():
    r = LegitimacyReport(
        tier="high_confidence",
        score=0.9,
        signals=[
            Signal(name="posting_age", value="7 days ago", weight="positive", source="page"),
        ],
        context_notes=["Recent posting"],
        summary="Multiple positive signals indicate an active opening.",
    )
    assert r.tier == "high_confidence"
    assert len(r.signals) == 1


@pytest.mark.asyncio
async def test_chain_high_confidence(mock_client):
    mock_client.complete_json.return_value = {
        "tier": "high_confidence",
        "score": 0.88,
        "signals": [
            {"name": "posting_age", "value": "5 days", "weight": "positive", "source": "page"},
            {"name": "apply_button_active", "value": "active", "weight": "positive", "source": "page"},
        ],
        "context_notes": [],
        "summary": "Active and fresh.",
    }
    chain = PostingLegitimacyChain(ai_client=mock_client)
    report = await chain.evaluate(
        jd_text="We're hiring a Senior Engineer to build...",
        url="https://boards.greenhouse.io/acme/jobs/123",
        page_metadata={"posted_date": "2026-04-28", "apply_button": "active"},
        scan_history={"times_seen": 1, "is_repost": False},
    )
    assert report.tier == "high_confidence"
    assert report.score > 0.8


@pytest.mark.asyncio
async def test_chain_suspicious_reposting(mock_client):
    mock_client.complete_json.return_value = {
        "tier": "suspicious",
        "score": 0.25,
        "signals": [
            {"name": "reposting", "value": "3 times over 120 days", "weight": "concerning", "source": "scan_history"},
            {"name": "posting_age", "value": "75 days ago", "weight": "concerning", "source": "page"},
        ],
        "context_notes": ["Consider that Staff+ roles legitimately stay open longer"],
        "summary": "Multiple ghost indicators.",
    }
    chain = PostingLegitimacyChain(ai_client=mock_client)
    report = await chain.evaluate(
        jd_text="Senior Engineer needed.",
        url="https://jobs.lever.co/acme/abc",
        page_metadata={"posted_date": "2026-02-15"},
        scan_history={"times_seen": 3, "is_repost": True, "days_span": 120},
    )
    assert report.tier == "suspicious"
    assert report.score < 0.4


@pytest.mark.asyncio
async def test_defaults_to_caution_on_no_signals(mock_client):
    # Simulate LLM returning insufficient data
    mock_client.complete_json.return_value = {
        "tier": "caution",
        "score": 0.5,
        "signals": [],
        "context_notes": ["Limited data available"],
        "summary": "Insufficient data to make a high-confidence assessment.",
    }
    chain = PostingLegitimacyChain(ai_client=mock_client)
    report = await chain.evaluate(
        jd_text="", url="", page_metadata={}, scan_history=None,
    )
    assert report.tier == "caution"
```

- [ ] **Step 3: Run test to fail**

```bash
cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_chains/test_posting_legitimacy.py -v 2>&1 | head
```

- [ ] **Step 4: Implement**

```python
# ai_engine/chains/posting_legitimacy.py
"""Posting Legitimacy Chain (career-ops Block G adaptation).

Three-tier assessment — high_confidence / caution / suspicious —
based on weighted signals. Ethical framing: we present signals,
never make accusations.
"""
from __future__ import annotations

import pathlib
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ai_engine.client import AIClient, get_ai_client

LegitimacyTier = Literal["high_confidence", "caution", "suspicious"]
SignalWeight = Literal["positive", "neutral", "concerning"]

_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "posting_legitimacy_system.md"


class Signal(BaseModel):
    name: str
    value: str
    weight: SignalWeight
    source: str = Field(description="page | scan_history | web_search | jd_text | qualitative")


class LegitimacyReport(BaseModel):
    tier: LegitimacyTier
    score: float = Field(ge=0.0, le=1.0, description="0=suspicious, 1=high_confidence")
    signals: list[Signal] = Field(default_factory=list)
    context_notes: list[str] = Field(default_factory=list)
    summary: str


class PostingLegitimacyChain:
    """Evaluate a job posting for ghost-job / active-opening signals."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        self.ai_client = ai_client or get_ai_client()
        self.system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")

    async def evaluate(
        self,
        jd_text: str,
        url: str,
        page_metadata: dict | None = None,
        scan_history: dict | None = None,
    ) -> LegitimacyReport:
        """Run Block G evaluation. Inputs can be sparse — the chain
        defaults to 'caution' if it cannot form a confident tier."""
        user_prompt = self._build_user_prompt(jd_text, url, page_metadata, scan_history)
        raw = await self.ai_client.complete_json(
            system=self.system_prompt,
            user=user_prompt,
            schema=LegitimacyReport.model_json_schema(),
        )
        return LegitimacyReport(**raw)

    def _build_user_prompt(
        self, jd_text: str, url: str,
        page_metadata: dict | None, scan_history: dict | None,
    ) -> str:
        pm = page_metadata or {}
        sh = scan_history or {}
        return (
            f"URL: {url or '(not provided)'}\n"
            f"Posted date: {pm.get('posted_date', 'unknown')}\n"
            f"Apply button: {pm.get('apply_button', 'unknown')}\n"
            f"Scan history: seen {sh.get('times_seen', 1)}x, span {sh.get('days_span', 0)}d, "
            f"is_repost={sh.get('is_repost', False)}\n\n"
            f"JD TEXT:\n{jd_text[:8000] if jd_text else '(not provided)'}\n\n"
            "Evaluate per Block G rules. Return JSON matching the schema. "
            "If data is insufficient for a high-confidence tier, default to 'caution' "
            "with a context note — NEVER default to 'suspicious' without evidence."
        )
```

- [ ] **Step 5: Run tests to pass**

- [ ] **Step 6: Commit**

```bash
git add ai_engine/chains/posting_legitimacy.py ai_engine/chains/prompts/posting_legitimacy_system.md backend/tests/unit/test_chains/test_posting_legitimacy.py
git commit -m "feat(ai): posting legitimacy chain (ghost-job detection, career-ops Block G)"
```

---

### Task 1.5: Public Ghost-Check Endpoint

**Files:**
- Create `backend/app/api/routes/public.py`
- Edit `backend/app/api/routes/__init__.py` — include `public_router`
- Edit `backend/app/core/rate_limit.py` — add `public_ghost_check` bucket

Unauthenticated endpoint at `POST /api/public/ghost-check` — accepts `{ url: string, jd_text?: string }`, returns `LegitimacyReport`. Aggressive rate limit: 10/hour/IP, 100/day/IP. Logs anonymized hash to `public_ghost_scans` for the weekly index.

- [ ] **Step 1: Add rate-limit bucket**

Edit `backend/app/core/rate_limit.py`:

```python
# Add to existing rate-limit config
PUBLIC_GHOST_CHECK_PER_HOUR = 10
PUBLIC_GHOST_CHECK_PER_DAY = 100
```

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/integration/test_public_ghost_check.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ghost_check_returns_tier(async_client: AsyncClient):
    resp = await async_client.post("/api/public/ghost-check", json={
        "url": "https://boards.greenhouse.io/acme/jobs/123",
        "jd_text": "We're hiring a Senior Engineer...",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] in ("high_confidence", "caution", "suspicious")
    assert "signals" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_ghost_check_rate_limit(async_client: AsyncClient):
    for i in range(11):
        resp = await async_client.post("/api/public/ghost-check", json={
            "url": f"https://example.com/{i}",
        })
    # The 11th request should be rate-limited
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_ghost_check_requires_url(async_client: AsyncClient):
    resp = await async_client.post("/api/public/ghost-check", json={})
    assert resp.status_code == 422
```

- [ ] **Step 3: Implement the route**

```python
# backend/app/api/routes/public.py
"""Public (unauthenticated) endpoints.

Aggressively rate-limited. Designed to support viral tools like the Ghost-Job Radar
without requiring user signup. Results are logged anonymized (sha256(url)) so we can
publish aggregate stats without exposing individual queries.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ai_engine.chains.posting_legitimacy import PostingLegitimacyChain, LegitimacyReport
from app.core.db import get_supabase
from app.core.rate_limit import rate_limit_check
from app.services.scan_history_service import ScanHistoryService
from app.services.url_canonicalizer import canonicalize_url, extract_ats_key

router = APIRouter()

_chain = PostingLegitimacyChain()


class GhostCheckRequest(BaseModel):
    url: str = Field(min_length=4)
    jd_text: Optional[str] = None


@router.post("/ghost-check", response_model=LegitimacyReport)
async def ghost_check(req: GhostCheckRequest, request: Request) -> LegitimacyReport:
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_check(
        key=f"public_ghost_check:{client_ip}",
        per_hour=10, per_day=100,
    )

    canonical = canonicalize_url(req.url)
    ats = extract_ats_key(canonical)
    company_slug = ats[1] if ats else "unknown"

    db = get_supabase()
    history = ScanHistoryService(db).record_scan(
        canonical, company_slug=company_slug, role_title=""
    )

    report = await _chain.evaluate(
        jd_text=req.jd_text or "",
        url=canonical,
        page_metadata={},
        scan_history=history,
    )

    # Anonymized log
    url_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    try:
        db.table("public_ghost_scans").insert({
            "url_hash": url_hash,
            "company_slug": company_slug,
            "tier": report.tier,
            "signals": [s.model_dump() for s in report.signals],
        }).execute()
    except Exception:
        # Non-fatal — aggregation is a nice-to-have
        pass

    return report
```

- [ ] **Step 4: Wire into router aggregator**

Edit `backend/app/api/routes/__init__.py`:

```python
from app.api.routes.public import router as public_router
# ...
router.include_router(public_router, prefix="/public", tags=["Public (unauth)"])
```

- [ ] **Step 5: Run tests to pass**

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/public.py backend/app/api/routes/__init__.py backend/app/core/rate_limit.py backend/tests/integration/test_public_ghost_check.py
git commit -m "feat(api): public /ghost-check endpoint (unauth, rate-limited)"
```

---

### Task 1.6: Authenticated Legitimacy Endpoint (for Job Board badges)

**File:** `backend/app/api/routes/intel.py` — ADD a method

- [ ] **Step 1: Add endpoint `POST /api/intel/legitimacy`**

Same chain call, but authenticated, no rate limit for logged-in users. Returns the full `LegitimacyReport`. Stores tier + signals on `applications.legitimacy_tier` + `applications.legitimacy_signals` when `application_id` is provided.

```python
# Add to backend/app/api/routes/intel.py
from ai_engine.chains.posting_legitimacy import PostingLegitimacyChain, LegitimacyReport
from app.services.scan_history_service import ScanHistoryService
from app.services.url_canonicalizer import canonicalize_url, extract_ats_key

_legitimacy_chain = PostingLegitimacyChain()


class LegitimacyRequest(BaseModel):
    url: str
    jd_text: str | None = None
    application_id: str | None = None
    company_name: str | None = None
    role_title: str | None = None


@router.post("/legitimacy", response_model=LegitimacyReport)
async def legitimacy(
    req: LegitimacyRequest,
    user=Depends(get_current_user),
    db=Depends(get_supabase),
) -> LegitimacyReport:
    canonical = canonicalize_url(req.url)
    ats = extract_ats_key(canonical)
    company_slug = (req.company_name or (ats[1] if ats else "unknown")).lower()
    history = ScanHistoryService(db).record_scan(
        canonical, company_slug=company_slug, role_title=req.role_title or "",
    )
    report = await _legitimacy_chain.evaluate(
        jd_text=req.jd_text or "",
        url=canonical,
        page_metadata={},
        scan_history=history,
    )
    if req.application_id:
        db.table("applications").update({
            "legitimacy_tier": report.tier,
            "legitimacy_signals": {"signals": [s.model_dump() for s in report.signals],
                                    "score": report.score,
                                    "summary": report.summary},
        }).eq("id", req.application_id).eq("user_id", str(user.id)).execute()
    return report
```

- [ ] **Step 2: Write integration test** (mock the chain, assert persistence)

- [ ] **Step 3: Commit**

```bash
git commit -am "feat(api): authenticated /intel/legitimacy with persistence"
```

---

### Task 1.7: Public `/ghost-check` Frontend Page

**Files:**
- Create `frontend/src/app/ghost-check/page.tsx`
- Create `frontend/src/app/ghost-check/layout.tsx`
- Create `frontend/src/app/ghost-check/components/url-input.tsx`
- Create `frontend/src/app/ghost-check/components/result-card.tsx`
- Create `frontend/src/app/ghost-check/components/signals-table.tsx`
- Create `frontend/src/app/ghost-check/components/share-buttons.tsx`
- Create `frontend/src/lib/api/public.ts`

Public SEO-optimized landing. Hero → URL input → result card with tier, signals, share buttons. CTA at bottom: "Want this built into your job search? Try HireStack free."

- [ ] **Step 1: Layout + metadata**

```tsx
// frontend/src/app/ghost-check/layout.tsx
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Ghost Job Radar — Free tool by HireStack AI",
  description:
    "Paste any job URL. We'll tell you if it's a real, active opening or a ghost job. Free, no signup required.",
  openGraph: {
    title: "Ghost Job Radar — Stop wasting time on fake jobs",
    description:
      "Instant legitimacy check for any job posting. Powered by HireStack AI.",
  },
};

export default function GhostCheckLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-background">{children}</div>;
}
```

- [ ] **Step 2: Page**

```tsx
// frontend/src/app/ghost-check/page.tsx
"use client";
import { useState } from "react";
import { UrlInput } from "./components/url-input";
import { ResultCard } from "./components/result-card";
import { ShareButtons } from "./components/share-buttons";
import { checkGhostJob, type GhostCheckResult } from "@/lib/api/public";

export default function GhostCheckPage() {
  const [result, setResult] = useState<GhostCheckResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(url: string, jdText?: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await checkGhostJob(url, jdText);
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <header className="mb-12 text-center">
        <h1 className="text-5xl font-bold tracking-tight">
          Ghost Job Radar
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Paste any job URL. We'll tell you if it's a real active opening — or a ghost.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Free. No signup. Powered by <a href="/" className="underline">HireStack AI</a>.
        </p>
      </header>

      <UrlInput onSubmit={onSubmit} loading={loading} />

      {error && (
        <div className="mt-6 rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
          {error}
        </div>
      )}

      {result && (
        <section className="mt-10">
          <ResultCard result={result} />
          <ShareButtons result={result} />
        </section>
      )}

      <footer className="mt-20 rounded-xl border bg-muted/30 p-8 text-center">
        <h2 className="text-2xl font-semibold">Want this built into your job search?</h2>
        <p className="mt-2 text-muted-foreground">
          HireStack AI scores every job you're considering, auto-drafts follow-ups, and tells you
          when <em>not</em> to apply.
        </p>
        <a
          href="/signup"
          className="mt-6 inline-block rounded-lg bg-primary px-6 py-3 font-medium text-primary-foreground"
        >
          Try HireStack free →
        </a>
      </footer>
    </main>
  );
}
```

- [ ] **Step 3: Components + API client**

(Full component code provided in the implementation session — standard shadcn/ui patterns. URL input is a textarea + optional JD text area. ResultCard shows tier pill with color (green/yellow/red), score, summary. SignalsTable lists each signal with its weight color. ShareButtons: Tweet + LinkedIn + Copy-link buttons with a prewritten share text.)

- [ ] **Step 4: API client**

```tsx
// frontend/src/lib/api/public.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Signal = {
  name: string;
  value: string;
  weight: "positive" | "neutral" | "concerning";
  source: string;
};

export type GhostCheckResult = {
  tier: "high_confidence" | "caution" | "suspicious";
  score: number;
  signals: Signal[];
  context_notes: string[];
  summary: string;
};

export async function checkGhostJob(url: string, jdText?: string): Promise<GhostCheckResult> {
  const res = await fetch(`${API_BASE}/api/public/ghost-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, jd_text: jdText || undefined }),
  });
  if (res.status === 429) {
    throw new Error("Rate limit hit. Please try again in an hour (or sign up — it's free).");
  }
  if (!res.ok) {
    throw new Error("Could not check this URL. Please try again.");
  }
  return res.json();
}
```

- [ ] **Step 5: Playwright e2e test**

```ts
// frontend/e2e/ghost-check.spec.ts
import { test, expect } from "@playwright/test";

test("ghost check page loads and accepts a URL", async ({ page }) => {
  await page.goto("/ghost-check");
  await expect(page.getByRole("heading", { name: /Ghost Job Radar/i })).toBeVisible();
  await page.fill('[name="url"]', "https://boards.greenhouse.io/acme/jobs/123");
  await page.click('button[type="submit"]');
  await expect(page.locator('[data-testid="result-card"]')).toBeVisible({ timeout: 15000 });
});
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ghost-check frontend/src/lib/api/public.ts frontend/e2e/ghost-check.spec.ts
git commit -m "feat(public): Ghost Job Radar landing page with viral share"
```

---

### Task 1.8: Legitimacy Badges in Job Board

**File:** `frontend/src/app/(dashboard)/job-board/` (existing), plus new `frontend/src/components/legitimacy/legitimacy-badge.tsx`

Show a small badge on every job card: ✓ Likely real / ⚠ Caution / ⚠ Possible ghost. Clicking opens a tooltip with the signals table.

- [ ] **Step 1: Build the reusable badge component**

```tsx
// frontend/src/components/legitimacy/legitimacy-badge.tsx
import { cn } from "@/lib/utils";

export type LegitimacyTier = "high_confidence" | "caution" | "suspicious";

const STYLES: Record<LegitimacyTier, { label: string; cls: string }> = {
  high_confidence: { label: "Likely real", cls: "bg-emerald-500/15 text-emerald-600" },
  caution: { label: "Caution", cls: "bg-amber-500/15 text-amber-600" },
  suspicious: { label: "Possible ghost", cls: "bg-rose-500/15 text-rose-600" },
};

export function LegitimacyBadge({ tier }: { tier?: LegitimacyTier | null }) {
  if (!tier) return null;
  const s = STYLES[tier];
  return (
    <span
      className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", s.cls)}
      data-testid={`legitimacy-${tier}`}
    >
      {s.label}
    </span>
  );
}
```

- [ ] **Step 2: Wire into Job Board cards**

Edit the job-card component under `frontend/src/app/(dashboard)/job-board/` to fetch/display `legitimacy_tier` from the application record.

- [ ] **Step 3: Commit**

```bash
git commit -am "feat(job-board): legitimacy badges on job cards"
```

---

### Task 1.9: Anti-Spray Gate in Workspace

**File:** `frontend/src/app/(dashboard)/applications/[id]/` — the "Generate Application Pack" button

When the application's composite fit score (from Critic/Optimizer) is below 4.0/5, the generate button is disabled with a dismissible override dialog: *"This role scores X.X/5 — HireStack recommends against spending time on roles below 4.0. Want to override?"*

- [ ] **Step 1: Read existing Workspace page**
- [ ] **Step 2: Add gate logic + override dialog**
- [ ] **Step 3: Track override in `analytics` table as `event_type='antispray_override'`** — so we can measure how often users ignore us
- [ ] **Step 4: Commit**

```bash
git commit -am "feat(workspace): anti-spray gate below 4.0 fit score"
```

---

### Task 1.10: Canonical Status Backfill

Write a one-time data migration inside the consolidated SQL file that maps existing `applications.status` values to `status_canonical`:

| Existing value | Canonical |
|---|---|
| `draft` | `evaluated` |
| `generating` | `evaluated` |
| `complete` / `generated` | `evaluated` |
| `applied` | `applied` |
| `offered` / `offer` | `offer` |
| `rejected` | `rejected` |
| `interview` | `interview` |
| anything else | `evaluated` |

Plus: if `callback_received_at IS NOT NULL` → `status_canonical = 'answered'` (unless already past that state).

---

### Sprint 1 Completion Criteria

- [ ] `supabase/migrations/20260502000000_career_ops_integration.sql` applied without errors
- [ ] `POST /api/public/ghost-check` returns a valid `LegitimacyReport` for a known URL
- [ ] `POST /api/intel/legitimacy` persists to `applications.legitimacy_tier`
- [ ] `/ghost-check` page renders and a user can submit a URL and see tier + signals
- [ ] Job Board cards show legitimacy badges
- [ ] Anti-spray gate blocks generation below 4.0/5 with override
- [ ] All new tests pass
- [ ] Rate-limit triggers at 11th request/hour

**Success metric:** Ship `/ghost-check` publicly + post to r/jobs, r/cscareerquestions, LinkedIn within 48h of deploy. Target: ≥1k scans in first week.

---

## Sprint 2 — Retention Loop (Follow-ups)

Delivers: Follow-up cadence tracker, 4 draft templates, weekly "Career Ops Report" email, dashboard tab.

### Architecture

```
Redis Streams worker (existing)
  └─ NEW consumer: followup_beat (runs every 15min)
       ├─ Scans `application_followups WHERE scheduled_for <= now() AND status='pending'`
       ├─ For each: generates draft via FollowupDrafterChain
       └─ Updates status='draft_ready' + notifies user (in-app + email digest)

Weekly digest (Sunday 09:00 user TZ):
  └─ Aggregates: applications applied this week, follow-ups due, new ≥4.0 matches
  └─ Email template via Postmark/SES (existing provider)
```

### File Structure (Sprint 2)

```
ai_engine/chains/
├── followup_drafter.py                 # NEW
└── prompts/
    ├── followup_first.md               # NEW
    ├── followup_linkedin.md            # NEW
    ├── followup_second.md              # NEW
    └── followup_cold_reopen.md         # NEW

backend/app/
├── services/
│   ├── followup_service.py             # NEW — CRUD + cadence rules
│   └── weekly_digest_service.py        # NEW
├── api/routes/
│   └── followups.py                    # NEW
└── workers/                             # NEW directory (if not exists)
    ├── followup_beat.py                # NEW
    └── weekly_digest_beat.py           # NEW

frontend/src/app/(dashboard)/applications/
├── followups/                          # NEW tab
│   └── page.tsx
└── components/
    └── followup-card.tsx               # NEW
```

### Tasks (Sprint 2)

- [ ] **Task 2.1:** FollowupDrafter chain with 4 prompts (first / linkedin / second / cold-reopen)
- [ ] **Task 2.2:** `FollowupService` — cadence rules (applied=7d, responded=3d, interview=1d), extract contacts from notes, urgency tiering (URGENT / OVERDUE / waiting / COLD)
- [ ] **Task 2.3:** `/api/followups/due`, `/api/followups/{id}/send`, `/api/followups/{id}/dismiss`
- [ ] **Task 2.4:** `followup_beat` worker — polls every 15min, generates drafts, marks ready
- [ ] **Task 2.5:** `WeeklyDigestService` + `weekly_digest_beat` — Sunday 09:00 user TZ
- [ ] **Task 2.6:** Dashboard `/applications/followups` tab — URGENT/OVERDUE/waiting/COLD columns
- [ ] **Task 2.7:** Email templates (HTML) for digest + follow-up-ready notifications
- [ ] **Task 2.8:** e2e: user sees overdue follow-up, clicks "Review draft", edits, sends

### Sprint 2 Completion Criteria

- [ ] Follow-ups auto-generate drafts on schedule
- [ ] Dashboard tab shows urgency pills
- [ ] Sunday digest emails send
- [ ] 40%+ open rate on digest (post-launch measurement)

---

## Sprint 3 — Signal Layer (Patterns + Scorecard + Archetypes)

Delivers: Rejection Pattern Detector analytics, A–G scorecard tab per application, 6 archetype presets + onboarding picker.

### File Structure (Sprint 3)

```
ai_engine/chains/
├── rejection_patterns.py               # NEW — aggregates outcomes
└── ag_scorecard_builder.py             # NEW — builds A-G from existing pipeline outputs

backend/app/
├── api/routes/
│   ├── analytics.py                    # EDIT — add /patterns
│   └── archetypes.py                   # NEW
└── services/
    ├── pattern_analyzer.py             # NEW
    └── archetype_service.py            # NEW

frontend/src/app/(dashboard)/
├── career-analytics/
│   └── patterns/                       # NEW
│       └── page.tsx
├── applications/[id]/
│   └── scorecard/                      # NEW tab
│       └── page.tsx
└── nexus/                              # EDIT — add archetype picker step
```

### Tasks (Sprint 3)

- [ ] **Task 3.1:** `pattern_analyzer.py` — funnel, score-vs-outcome, archetype performance, top blockers, tech-stack gaps, recommended score threshold
- [ ] **Task 3.2:** `/api/analytics/patterns` endpoint
- [ ] **Task 3.3:** `/career-analytics/patterns/page.tsx` — full dashboard
- [ ] **Task 3.4:** Auto-surface banner on Dashboard after 5+ rejections: *"Notice a pattern?"* → links to Patterns page
- [ ] **Task 3.5:** `ag_scorecard_builder.py` — compose A–G blocks from existing Benchmark / Critic / Optimizer / CompanyIntel outputs (no new LLM call — just reshape). Persist to `applications.scorecard_ag`.
- [ ] **Task 3.6:** Scorecard tab — visually striking, shows all 7 blocks + global score
- [ ] **Task 3.7:** Archetype preset picker in Career Nexus onboarding — 6 cards, pick one, influences future evaluations
- [ ] **Task 3.8:** Wire archetype into Critic / DocGenerator chains — pull from `applications.archetype_preset`

### Sprint 3 Completion Criteria

- [ ] Patterns page renders full report with ≥5 applications
- [ ] Recommended score threshold is data-derived and displayed
- [ ] Every application has an A–G scorecard tab
- [ ] User can pick one of 6 archetype presets and it influences subsequent generations

---

## Sprint 4 — Voice & Quality

Delivers: Story Bank (STAR+R), Writing Samples UX, "I'm Choosing You" tone directive, Professional Writing blocklist, Evidence Vault split (Proof Points + Artifacts).

### File Structure (Sprint 4)

```
ai_engine/chains/
├── story_bank_manager.py               # NEW
└── prompts/
    ├── story_bank_system.md            # NEW
    └── drafter_revision.md             # EDIT — add "I'm choosing you" directive + blocklist

ai_engine/agents/
├── critic.py                           # EDIT — enforce blocklist
└── style_signal_deriver.py             # EDIT — consume writing_samples
backend/app/
├── api/routes/
│   ├── story_bank.py                   # NEW
│   ├── writing_samples.py              # NEW
│   └── proof_points.py                 # NEW
└── services/
    ├── story_bank_service.py           # NEW
    └── proof_points_service.py         # NEW

frontend/src/app/(dashboard)/
├── evidence/                           # EDIT — split into tabs
│   ├── page.tsx                        # tabs: Proof Points | Artifacts | Stories
│   ├── stories/
│   ├── proofs/
│   └── artifacts/
└── nexus/
    └── writing-samples/                # NEW — upload/paste
```

### Tasks (Sprint 4)

- [ ] **Task 4.1:** `story_bank` table CRUD + STAR+R schema (S, T, A, R, Reflection, tags, archetype_affinity)
- [ ] **Task 4.2:** Auto-prompt after each Interview Simulator session: *"Save this as a reusable story?"*
- [ ] **Task 4.3:** Interview-prep chain pulls from story bank first, flags gaps
- [ ] **Task 4.4:** Writing samples UI — drag-drop or paste; call existing `style_signal_deriver.py`; cache derived style on profile
- [ ] **Task 4.5:** Update `drafter_revision.md` system prompt with "I'm choosing you" directive + banned phrases
- [ ] **Task 4.6:** Critic agent enforces: flag any draft containing banned phrases ("passionate about", "would love the opportunity", "strong fit", "hit the ground running", "team player")
- [ ] **Task 4.7:** Evidence Vault split — Proof Points (claims + metrics), Artifacts (files/links), Stories (STAR+R bank)

### Sprint 4 Completion Criteria

- [ ] User can build a story bank, stories persist
- [ ] Interview prep maps questions to bank with gap flagging
- [ ] Writing samples influence output voice (measurable via style-signal-derived JSON on profile)
- [ ] Drafts no longer contain banned phrases (Critic verified)

---

## Sprint 5 — Power Tools

Delivers: Batch Evaluation, LinkedIn Contact-Type Framework, Deep Research 6-axis merge, Training/Project ROI evaluator.

### Tasks (Sprint 5)

- [ ] **Task 5.1:** Batch scoring pipeline — lightweight Benchmark+Gap only, parallelizable via Redis Streams fan-out. UI: textarea of URLs → progress grid → ranked table
- [ ] **Task 5.2:** Refactor `linkedin_advisor.py` — 4 contact-type branches (Recruiter / HM / Peer / Interviewer) with distinct 3-sentence frameworks and 300-char enforcement
- [ ] **Task 5.3:** Merge 6-axis deep-research prompt into `company_intel.py` (AI strategy / Recent moves / Eng culture / Challenges / Competitors / Candidate angle)
- [ ] **Task 5.4:** Training ROI chain — "Is this course worth it for [target archetype]?" evaluates cert/course metadata against user profile + market demand
- [ ] **Task 5.5:** Project ROI chain — "Is this portfolio project worth building?" ranks by gap-closure value
- [ ] **Task 5.6:** Surface both in Career Lab

### Sprint 5 Completion Criteria

- [ ] User can paste 10+ URLs, get parallel scores in <60s
- [ ] LinkedIn message generator asks contact type, produces a 4-way-distinct result
- [ ] Company Intel reports now have the 6-axis structure
- [ ] Career Lab has an "Evaluate" section (training + project)

---

## Sprint 6 — Distribution

Delivers: Chrome Extension with Live Apply, Shareable Outcome Cards, Public Benchmarks, Brand rewrite.

### File Structure (Sprint 6)

```
extension/                              # NEW — Chrome MV3
├── manifest.json
├── src/
│   ├── background.ts
│   ├── content/
│   │   ├── detector.ts                 # detect ATS page type
│   │   ├── form-parser.ts              # extract form questions
│   │   └── overlay.tsx                 # "Powered by HireStack" pills
│   ├── popup/
│   │   ├── popup.html
│   │   └── popup.tsx
│   └── lib/
│       └── api.ts
├── package.json
└── README.md

backend/app/api/routes/
└── apply.py                            # NEW — /api/apply/answer

frontend/src/
├── app/
│   ├── o/[slug]/                       # NEW — public outcome card landing
│   │   ├── page.tsx
│   │   └── opengraph-image.tsx
│   └── benchmarks/                     # NEW — public archetype benchmarks
│       └── [archetype]/
│           └── page.tsx
```

### Tasks (Sprint 6)

- [ ] **Task 6.1:** Chrome extension scaffold (MV3, TypeScript, webpack/vite)
- [ ] **Task 6.2:** Content script detects Lever/Greenhouse/Ashby/Workday/LinkedIn application pages
- [ ] **Task 6.3:** Popup shows: "Not evaluated yet? [Quick eval]" or "Evaluated (4.2/5) — Fill form with HireStack"
- [ ] **Task 6.4:** Overlay injects "⚠ Possible ghost" pill next to suspicious jobs directly on Greenhouse/Ashby/LinkedIn listings (uses `/api/public/ghost-check` for anonymous users)
- [ ] **Task 6.5:** `/api/apply/answer` — given `application_id` + form question, returns a tailored answer using existing scorecard + profile
- [ ] **Task 6.6:** Outcome Cards — after an offer is recorded, `/o/{share-slug}` renders a branded OG card (opengraph-image.tsx pattern). "I evaluated X jobs, applied to Y, got Z offers — built with HireStack"
- [ ] **Task 6.7:** Public archetype benchmarks — anonymized aggregates per archetype, SEO-optimized
- [ ] **Task 6.8:** Brand rewrite — `frontend/src/app/page.tsx` hero + 4 promises, `opengraph-image.tsx`, `README.md` case-study narrative

### Sprint 6 Completion Criteria

- [ ] Extension installable from Chrome Web Store (submit during sprint)
- [ ] Live Apply fills form fields on Greenhouse/Ashby with one click
- [ ] Outcome card shareable + renders correctly on LinkedIn/X OG previews
- [ ] Landing page leads with "We tell you when NOT to apply"

---

## Viral Growth Mechanics

Each sprint includes a distribution loop:

| Loop | Sprint | Trigger | Expected impact |
|---|---|---|---|
| Ghost Job Radar (public) | 1 | Launch | PR, organic social |
| Weekly "Career Ops Report" email | 2 | Every Sunday | 40%+ open, forwards |
| Shareable outcome cards | 6 | After every offer | LinkedIn impressions |
| Chrome extension | 6 | Every ATS page visit | In-context brand impressions |
| Public archetype benchmarks | 6 | SEO long-tail | Organic search |
| Anti-spray banner | 1 | Below 4.0 gate | Tweetable philosophy |

**Launch PR angle (day Sprint 1 ships):**
- Post to r/jobs, r/cscareerquestions, r/layoffs, r/recruitinghell
- Post on X with: "We built a free tool that tells you if a job posting is a ghost. No signup. [link]"
- Post on LinkedIn with the anti-spray positioning
- Reach out to job-search newsletters (DevTernity, NowHiring, Levels.fyi)

---

## Success Metrics (cumulative)

| Week | Ship | Metric |
|---|---|---|
| 2 | Ghost Radar | ≥1k public scans |
| 4 | Follow-up digest | ≥40% open rate on Sunday digest |
| 6 | Scorecard + Patterns | ≥70% of WAU have viewed their scorecard at least once |
| 8 | Voice quality | ≥20% lift in document-quality survey vs baseline |
| 10 | Batch eval | ≥25% of Pro users use batch mode monthly |
| 12 | Extension | ≥5k installs; ≥30% of new signups from extension |

---

## Rollback Plan

Each sprint's migration uses `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` — safe to re-apply. To rollback a feature:

1. Feature flag via `NEXT_PUBLIC_FEATURE_<NAME>` env var — disable the UI
2. New columns/tables remain but are unused
3. Code revert: `git revert <sprint-merge-commit>`

Critical: **never drop columns in a rollback** — only hide them. Data preservation is absolute.

---

## References (read-only)

All source material is cloned under `reference/career-ops/`:
- `reference/career-ops/modes/_shared.md` — Global rules, archetypes, writing style, Block G
- `reference/career-ops/modes/oferta.md` — Full A–G evaluation spec
- `reference/career-ops/modes/followup.md` — Follow-up cadence rules
- `reference/career-ops/modes/patterns.md` — Rejection pattern analysis
- `reference/career-ops/modes/contacto.md` — LinkedIn contact-type frameworks
- `reference/career-ops/modes/apply.md` — Live apply workflow
- `reference/career-ops/modes/batch.md` — Batch processing architecture
- `reference/career-ops/modes/deep.md` — 6-axis deep research prompt
- `reference/career-ops/modes/auto-pipeline.md` — "I'm choosing you" tone
- `reference/career-ops/interview-prep/story-bank.md` — STAR+R format
- `reference/career-ops/check-liveness.mjs` / `liveness-core.mjs` — Ghost-detection signal logic
- `reference/career-ops/followup-cadence.mjs` — Cadence implementation
- `reference/career-ops/analyze-patterns.mjs` — Pattern detection implementation

---

## Open Questions (resolve during execution)

1. **Email provider** — Confirm Postmark vs SES vs Resend for weekly digest (check `backend/app/core/config.py`)
2. **User timezone** — Where is it stored? (Needed for "Sunday 09:00 user TZ" digest)
3. **Chrome extension hosting** — Publish under personal or company developer account?
4. **Rate-limit backend** — Current implementation (`backend/app/core/rate_limit.py`) uses Redis? Confirm for per-IP buckets on `/public/*`

---

## Execution Order (recommended)

1. **Day 1:** Apply DB migration, write plan review
2. **Day 2–3:** Sprint 1 Tasks 1.2, 1.3, 1.4 (services + chain, TDD)
3. **Day 4:** Sprint 1 Tasks 1.5, 1.6 (APIs)
4. **Day 5–6:** Sprint 1 Tasks 1.7, 1.8, 1.9 (frontend + gate)
5. **Day 7:** Ghost Radar launch + PR push
6. **Week 2+:** Sprints 2–6 in order

---

**End of plan. Execute one sprint at a time, one task at a time, TDD throughout.**
