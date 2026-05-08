from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping

import pytest

from app.core.database import TABLES
from app.services.auto_prep import AUTO_PREP_REQUESTED_MODULES, AutoPrepService
from app.services.batch_evaluator import ScoringResult
from app.services.batch_persister_core import make_dedup_key


class _FakeDB:
    def __init__(self, *, now: datetime) -> None:
        self.now = now
        self.tracked_rows: list[dict[str, Any]] = [
            {
                "id": "tc-1",
                "user_id": "u1",
                "company_slug": "acme",
                "display_name": "Acme",
                "enabled": True,
            }
        ]
        self.scan_rows: list[dict[str, Any]] = []
        self.application_rows: list[dict[str, Any]] = []
        self.created_rows: list[dict[str, Any]] = []

    async def query(
        self,
        table: str,
        filters: list[tuple] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
        offset: int | None = None,
    ) -> List[Mapping[str, Any]]:
        if table == TABLES["tracked_companies"]:
            rows = list(self.tracked_rows)
        elif table == TABLES["job_scan_history"]:
            rows = list(self.scan_rows)
        elif table == TABLES["applications"]:
            rows = list(self.application_rows)
        else:
            rows = []

        for field, op, value in filters or []:
            if op == "==":
                rows = [row for row in rows if row.get(field) == value]

        if order_by:
            rows.sort(key=lambda row: row.get(order_by) or "", reverse=(order_direction == "DESCENDING"))
        if offset:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def create(
        self,
        table: str,
        data: dict[str, Any],
        doc_id: str | None = None,
    ) -> str:
        assert table == TABLES["applications"]
        new_id = doc_id or f"app-{len(self.created_rows) + 1}"
        row = {**data, "id": new_id}
        self.created_rows.append(row)
        self.application_rows.append(row)
        return new_id


@pytest.mark.asyncio
async def test_prepare_recent_discoveries_creates_application_and_queues_job() -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    db = _FakeDB(now=now)
    db.scan_rows = [
        {
            "company_slug": "acme",
            "url_canonical": "https://jobs.example.com/roles/1",
            "role_title": "Staff Engineer",
            "first_seen": now.isoformat(),
            "last_seen": now.isoformat(),
        },
        {
            "company_slug": "acme",
            "url_canonical": "https://jobs.example.com/roles/duplicate",
            "role_title": "Duplicate Role",
            "first_seen": now.isoformat(),
            "last_seen": now.isoformat(),
        },
    ]
    db.application_rows = [
        {
            "id": "existing-1",
            "user_id": "u1",
            "confirmed_facts": {
                "dedup_key": make_dedup_key(
                    user_id="u1",
                    canonical_url="https://jobs.example.com/roles/duplicate",
                )
            },
        }
    ]

    queued: list[dict[str, Any]] = []

    def scorer_factory(user_id: str):
        assert user_id == "u1"

        async def _scorer(entry):
            return ScoringResult(
                canonical_url=entry.canonical_url,
                fit_score=4.7,
                title="Staff Engineer",
                company="Acme",
            )

        return _scorer

    def jd_loader_factory():
        async def _loader(entry):
            assert entry.canonical_url == "https://jobs.example.com/roles/1"
            return "Build distributed systems and own platform reliability."

        return _loader

    async def job_creator(**kwargs):
        queued.append(kwargs)
        return f"job-{kwargs['application_id']}"

    service = AutoPrepService(
        db=db,
        scorer_factory=scorer_factory,
        jd_loader_factory=jd_loader_factory,
        job_creator=job_creator,
    )

    result = await service.prepare_recent_discoveries("u1", now=now)

    assert result["recent_discoveries"] == 2
    assert result["candidates_considered"] == 1
    assert result["ranked_count"] == 1
    assert result["skipped_existing"] == 1
    assert result["applications_created"] == 1
    assert result["jobs_queued"] == 1
    assert len(db.created_rows) == 1
    created = db.created_rows[0]
    confirmed_facts = created["confirmed_facts"]
    assert created["title"] == "Staff Engineer"
    assert confirmed_facts["source"] == "tracked_company_auto_prep"
    assert confirmed_facts["job_title"] == "Staff Engineer"
    assert confirmed_facts["jobTitle"] == "Staff Engineer"
    assert confirmed_facts["jd_text"].startswith("Build distributed systems")
    assert confirmed_facts["jdText"].startswith("Build distributed systems")
    assert queued == [
        {
            "application_id": "app-1",
            "user_id": "u1",
            "requested_modules": list(AUTO_PREP_REQUESTED_MODULES),
            "application_modules": None,
        }
    ]


@pytest.mark.asyncio
async def test_prepare_recent_discoveries_skips_when_jd_enrichment_fails() -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    db = _FakeDB(now=now)
    db.scan_rows = [
        {
            "company_slug": "acme",
            "url_canonical": "https://jobs.example.com/roles/2",
            "role_title": "Platform Engineer",
            "first_seen": now.isoformat(),
            "last_seen": now.isoformat(),
        }
    ]

    def scorer_factory(_: str):
        async def _scorer(entry):
            return ScoringResult(
                canonical_url=entry.canonical_url,
                fit_score=4.8,
                title="Platform Engineer",
                company="Acme",
            )

        return _scorer

    def jd_loader_factory():
        async def _loader(_entry):
            return ""

        return _loader

    queued: list[dict[str, Any]] = []

    async def job_creator(**kwargs):
        queued.append(kwargs)
        return "job-unused"

    service = AutoPrepService(
        db=db,
        scorer_factory=scorer_factory,
        jd_loader_factory=jd_loader_factory,
        job_creator=job_creator,
    )

    result = await service.prepare_recent_discoveries("u1", now=now)

    assert result["applications_created"] == 0
    assert result["jobs_queued"] == 0
    assert result["enrichment_failures"] == 1
    assert db.created_rows == []
    assert queued == []