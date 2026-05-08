from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Mapping

import pytest

from app.core.database import TABLES
from app.services.cadence import CadenceService


class _FakeDB:
    def __init__(
        self,
        applications: list[dict[str, Any]] | None = None,
        followups: list[dict[str, Any]] | None = None,
        fail_followups: bool = False,
    ) -> None:
        self.applications = applications or []
        self.followups = followups or []
        self.fail_followups = fail_followups

    async def query(
        self,
        table: str,
        filters: list[tuple] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
        offset: int | None = None,
    ) -> List[Mapping[str, Any]]:
        if table == TABLES["applications"]:
            rows = list(self.applications)
        elif table == TABLES["application_followups"]:
            if self.fail_followups:
                raise RuntimeError("missing table")
            rows = list(self.followups)
        else:  # pragma: no cover
            raise AssertionError(f"unexpected table {table!r}")

        for field, op, value in filters or []:
            if op == "==":
                rows = [row for row in rows if row.get(field) == value]

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
    submitted_at: str = "2026-05-04T14:00:00+00:00",
    company_name: str = "Acme",
    job_title: str = "Engineer",
    response_received_at: str | None = None,
    contact_linkedin: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "user_id": "u1",
        "status": status,
        "submitted_at": submitted_at,
        "company_name": company_name,
        "job_title": job_title,
        "response_received_at": response_received_at,
        "contact_linkedin": contact_linkedin,
    }


def _followup(
    *,
    id: str,
    application_id: str,
    scheduled_for: str,
    status: str = "pending",
    template_key: str = "first",
    channel: str = "email",
    followup_count: int = 1,
    sent_at: str | None = None,
    draft: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "user_id": "u1",
        "application_id": application_id,
        "scheduled_for": scheduled_for,
        "status": status,
        "template_key": template_key,
        "channel": channel,
        "followup_count": followup_count,
        "sent_at": sent_at,
        "draft": dict(draft or {}),
    }


@pytest.mark.asyncio
async def test_compute_dashboard_sorts_into_actionable_buckets() -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    db = _FakeDB(
        applications=[
            _app(id="responded", status="responded", response_received_at=(now - timedelta(hours=2)).isoformat(), company_name="Beta", job_title="PM"),
            _app(id="overdue", company_name="Gamma", job_title="Designer"),
            _app(id="waiting", submitted_at=now.isoformat(), company_name="Delta", job_title="Engineer"),
            _app(id="cold", company_name="Epsilon", job_title="Analyst"),
        ],
        followups=[
            _followup(
                id="f-urgent",
                application_id="responded",
                scheduled_for=(now - timedelta(hours=1)).isoformat(),
                status="draft_ready",
                followup_count=1,
                draft={"subject": "Re: PM", "body": "Reply today", "placeholders_missing": []},
            ),
            _followup(
                id="f-overdue",
                application_id="overdue",
                scheduled_for=(now - timedelta(days=2)).isoformat(),
                status="pending",
                followup_count=1,
            ),
            _followup(
                id="f-cold-1",
                application_id="cold",
                scheduled_for=(now - timedelta(days=9)).isoformat(),
                status="sent",
                followup_count=1,
                sent_at=(now - timedelta(days=9)).isoformat(),
            ),
            _followup(
                id="f-cold-2",
                application_id="cold",
                scheduled_for=(now - timedelta(days=2)).isoformat(),
                status="sent",
                template_key="second",
                followup_count=2,
                sent_at=(now - timedelta(days=2)).isoformat(),
            ),
        ],
    )

    payload = await CadenceService(db=db).compute_dashboard(
        "u1",
        user_context={"full_name": "Ada Lovelace"},
        now=now,
    )

    assert payload["metadata"] == {
        "total_tracked": 4,
        "actionable_count": 2,
        "urgent_count": 1,
        "overdue_count": 1,
        "waiting_count": 1,
        "cold_count": 1,
        "closed_count": 0,
    }
    assert payload["buckets"]["urgent"][0]["application_id"] == "responded"
    assert payload["buckets"]["urgent"][0]["draft_body"] == "Reply today"
    assert payload["buckets"]["overdue"][0]["application_id"] == "overdue"
    assert payload["buckets"]["overdue"][0]["days_overdue"] == 2
    assert payload["buckets"]["waiting"][0]["application_id"] == "waiting"
    assert payload["buckets"]["cold"][0]["application_id"] == "cold"


@pytest.mark.asyncio
async def test_compute_dashboard_degrades_when_followup_table_missing() -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    db = _FakeDB(
        applications=[_app(id="waiting", submitted_at=now.isoformat())],
        fail_followups=True,
    )

    payload = await CadenceService(db=db).compute_dashboard("u1", now=now)

    assert payload["metadata"]["waiting_count"] == 1
    assert payload["buckets"]["waiting"][0]["template_key"] == "first"