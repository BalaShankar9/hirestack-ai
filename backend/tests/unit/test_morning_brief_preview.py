from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Mapping

import pytest

from app.core.database import TABLES
from app.services.cadence import CadenceService
from app.services.morning_brief_preview import MorningBriefPreviewService


class _FakeDB:
    def __init__(
        self,
        applications: list[dict[str, Any]] | None = None,
        followups: list[dict[str, Any]] | None = None,
        tracked: list[dict[str, Any]] | None = None,
        jobs: list[dict[str, Any]] | None = None,
        signals: list[dict[str, Any]] | None = None,
    ) -> None:
        self.applications = applications or []
        self.followups = followups or []
        self.tracked = tracked or []
        self.jobs = jobs or []
        self.signals = signals or []

    async def query(
        self,
        table: str,
        filters: list[tuple] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
        offset: int | None = None,
    ) -> List[Mapping[str, Any]]:
        rows_map = {
            TABLES["applications"]: self.applications,
            TABLES["application_followups"]: self.followups,
            TABLES["tracked_companies"]: self.tracked,
            TABLES["job_scan_history"]: self.jobs,
            TABLES["outcome_signals"]: self.signals,
        }
        rows = list(rows_map.get(table, []))
        for field, op, value in filters or []:
            if op == "==":
                rows = [row for row in rows if row.get(field) == value]
            elif op == ">=":
                rows = [row for row in rows if (row.get(field) or "") >= value]
            elif op == "<":
                rows = [row for row in rows if (row.get(field) or "") < value]
            elif op == "in":
                rows = [row for row in rows if row.get(field) in value]
        if order_by:
            rows.sort(
                key=lambda row: row.get(order_by) or "",
                reverse=(order_direction == "DESCENDING"),
            )
        if limit is not None:
            rows = rows[:limit]
        return rows


def _app(
    *,
    id: str,
    status: str = "submitted",
    updated_at: str,
    submitted_at: str | None = None,
    response_received_at: str | None = None,
    company_name: str = "Acme",
    job_title: str = "Engineer",
    title: str | None = None,
    confirmed_facts: dict[str, Any] | None = None,
    cv_html: str | None = None,
    cover_letter_html: str | None = None,
    personal_statement_html: str | None = None,
    portfolio_html: str | None = None,
    generated_documents: dict[str, str] | None = None,
    scorecard: dict[str, Any] | None = None,
    benchmark: dict[str, Any] | None = None,
    gaps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "user_id": "u1",
        "status": status,
        "updated_at": updated_at,
        "submitted_at": submitted_at or updated_at,
        "response_received_at": response_received_at,
        "company_name": company_name,
        "job_title": job_title,
        "title": title or job_title,
        "confirmed_facts": confirmed_facts or {},
        "cv_html": cv_html,
        "cover_letter_html": cover_letter_html,
        "personal_statement_html": personal_statement_html,
        "portfolio_html": portfolio_html,
        "generated_documents": generated_documents or {},
        "scorecard": scorecard,
        "benchmark": benchmark,
        "gaps": gaps,
    }


def _followup(*, application_id: str, scheduled_for: str, status: str = "pending", template_key: str = "first", sent_at: str | None = None, followup_count: int = 1) -> dict[str, Any]:
    return {
        "id": f"f-{application_id}-{template_key}",
        "user_id": "u1",
        "application_id": application_id,
        "scheduled_for": scheduled_for,
        "status": status,
        "template_key": template_key,
        "channel": "email",
        "followup_count": followup_count,
        "sent_at": sent_at,
        "draft": {},
    }


@pytest.mark.asyncio
async def test_build_preview_prefers_real_morning_brief_inputs() -> None:
    now = datetime(2026, 5, 7, 9, 0, tzinfo=timezone.utc)
    db = _FakeDB(
        applications=[
            _app(
                id="ready",
                status="evaluated",
                updated_at=(now - timedelta(hours=2)).isoformat(),
                company_name="Acme",
                job_title="Platform Engineer",
                confirmed_facts={"company": "Acme", "jobTitle": "Platform Engineer"},
                cv_html="<p>CV</p>",
                cover_letter_html="<p>CL</p>",
                scorecard={"overall": 88},
            ),
            _app(id="due", updated_at=(now - timedelta(days=1)).isoformat(), company_name="Acme", job_title="Platform Engineer"),
            _app(id="stale", updated_at=(now - timedelta(days=20)).isoformat(), company_name="Globex", job_title="Staff Engineer"),
            _app(id="win", updated_at=(now - timedelta(days=1)).isoformat(), response_received_at=(now - timedelta(hours=12)).isoformat(), company_name="Initech", job_title="Product Manager"),
        ],
        followups=[
            _followup(application_id="due", scheduled_for=(now - timedelta(hours=1)).isoformat(), status="pending"),
        ],
        tracked=[
            {"user_id": "u1", "company_slug": "stripe", "display_name": "Stripe"},
        ],
        jobs=[
            {
                "company_slug": "stripe",
                "role_title": "Backend Engineer",
                "url_canonical": "https://jobs.example/1",
                "last_seen": (now - timedelta(hours=6)).isoformat(),
            }
        ],
        signals=[
            {
                "user_id": "u1",
                "application_id": "win",
                "signal_type": "interview",
                "created_at": (now - timedelta(hours=12)).isoformat(),
            }
        ],
    )

    preview = await MorningBriefPreviewService(
        db=db,
        cadence_service=CadenceService(db=db),
    ).build_preview("u1", user_context={"full_name": "Ada Lovelace"}, now=now)

    assert preview is not None
    assert preview["source"] == "morning_brief"
    assert preview["section_counts"] == {"ready": 1, "beats": 2, "jobs": 1, "stale": 1, "wins": 1}
    assert preview["action_label"] == "Review cadence"
    assert "Morning, Ada." in preview["body_text"]
    assert "Ready to apply:" in preview["body_text"]
    assert "Today's follow-ups:" in preview["body_text"]
    assert "Wins yesterday:" in preview["body_text"]


@pytest.mark.asyncio
async def test_build_preview_returns_none_when_all_sections_empty() -> None:
    now = datetime(2026, 5, 7, 9, 0, tzinfo=timezone.utc)
    db = _FakeDB(applications=[_app(id="quiet", updated_at=now.isoformat())])

    preview = await MorningBriefPreviewService(
        db=db,
        cadence_service=CadenceService(db=db),
    ).build_preview("u1", now=now)

    assert preview is None