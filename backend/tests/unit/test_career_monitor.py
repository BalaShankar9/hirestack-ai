"""Focused tests for AutonomousCareerMonitor watchlist scan integration."""

from __future__ import annotations

from typing import Any, List, Mapping

import pytest

from app.core.database import TABLES
from app.services.career_monitor import AutonomousCareerMonitor
from app.services.portal_scanner_scheduler import TickResult


class _FakeDB:
    def __init__(self) -> None:
        self.alert_rows: list[dict[str, Any]] = []
        self.mission_rows: list[dict[str, Any]] = []
        self.tracked_company_rows: list[dict[str, Any]] = []

    async def query(
        self,
        table: str,
        filters: list[tuple] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
        offset: int | None = None,
    ) -> List[Mapping[str, Any]]:
        if table == TABLES["career_alerts"]:
            out = list(self.alert_rows)
            for field, op, value in filters or []:
                if op == "==":
                    out = [row for row in out if row.get(field) == value]
            return out[:limit] if limit is not None else out
        if table == TABLES["missions"]:
            out = list(self.mission_rows)
            for field, op, value in filters or []:
                if op == "==":
                    out = [row for row in out if row.get(field) == value]
            if order_by:
                out.sort(
                    key=lambda row: row.get(order_by) or "",
                    reverse=(order_direction == "DESCENDING"),
                )
            return out[:limit] if limit is not None else out
        if table == TABLES["tracked_companies"]:
            out = list(self.tracked_company_rows)
            for field, op, value in filters or []:
                if op == "==":
                    out = [row for row in out if row.get(field) == value]
            if order_by:
                out.sort(
                    key=lambda row: row.get(order_by) or "",
                    reverse=(order_direction == "DESCENDING"),
                )
            return out[:limit] if limit is not None else out
        return []

    async def create(
        self,
        table: str,
        data: dict[str, Any],
        doc_id: str | None = None,
    ) -> str:
        assert table == TABLES["career_alerts"]
        row = {**data, "id": doc_id or f"alert-{len(self.alert_rows) + 1}"}
        self.alert_rows.append(row)
        return row["id"]


@pytest.mark.asyncio
async def test_check_tracked_company_discoveries_creates_alert(monkeypatch) -> None:
    db = _FakeDB()
    monitor = AutonomousCareerMonitor(db=db)

    async def _fake_run_user_scan_tick(user_id: str, *, db, fetcher):
        assert user_id == "u1"
        assert db is monitor.db
        assert callable(fetcher)
        return TickResult(
            scanned_count=3,
            plans_attempted=3,
            new_postings_count=2,
            failure_count=1,
            marked_scanned_count=3,
        )

    monkeypatch.setattr("app.services.career_monitor.run_user_scan_tick", _fake_run_user_scan_tick)
    monkeypatch.setattr(
        "app.services.career_monitor.make_httpx_fetcher",
        lambda: (lambda _url: None),
    )
    async def _fake_prepare_recent_discoveries(self, user_id: str):
        assert user_id == "u1"
        return {
            "status": "disabled",
            "applications_created": 0,
            "jobs_queued": 0,
            "skipped_existing": 0,
            "below_threshold": 0,
            "score_failures": 0,
            "enrichment_failures": 0,
            "queue_failures": 0,
        }

    monkeypatch.setattr(
        "app.services.career_monitor.AutoPrepService.prepare_recent_discoveries",
        _fake_prepare_recent_discoveries,
    )

    result = await monitor._check_tracked_company_discoveries("u1")

    assert result == {
        "alerts": 1,
        "new_postings": 2,
        "scanned_companies": 3,
        "plans_attempted": 3,
        "failures": 1,
        "marked_scanned": 3,
        "auto_prep_status": "disabled",
        "auto_prep_applications": 0,
        "auto_prep_jobs": 0,
        "auto_prep_skipped_existing": 0,
        "auto_prep_below_threshold": 0,
        "auto_prep_score_failures": 0,
        "auto_prep_enrichment_failures": 0,
        "auto_prep_queue_failures": 0,
    }
    assert len(db.alert_rows) == 1
    alert = db.alert_rows[0]
    assert alert["alert_type"] == "tracked_company_discovery"
    assert alert["action_url"] == "/tracked-companies"
    assert alert["metadata"]["new_postings_count"] == 2


@pytest.mark.asyncio
async def test_check_tracked_company_discoveries_creates_auto_prep_alert(monkeypatch) -> None:
    db = _FakeDB()
    monitor = AutonomousCareerMonitor(db=db)

    async def _fake_run_user_scan_tick(user_id: str, *, db, fetcher):
        assert user_id == "u1"
        assert db is monitor.db
        assert callable(fetcher)
        return TickResult(
            scanned_count=2,
            plans_attempted=2,
            new_postings_count=2,
            failure_count=0,
            marked_scanned_count=2,
        )

    async def _fake_prepare_recent_discoveries(self, user_id: str):
        assert user_id == "u1"
        return {
            "status": "ok",
            "applications_created": 2,
            "jobs_queued": 2,
            "skipped_existing": 1,
            "below_threshold": 0,
            "score_failures": 0,
            "enrichment_failures": 0,
            "queue_failures": 0,
            "application_ids": ["app-1", "app-2"],
            "job_ids": ["job-1", "job-2"],
        }

    monkeypatch.setattr("app.services.career_monitor.run_user_scan_tick", _fake_run_user_scan_tick)
    monkeypatch.setattr(
        "app.services.career_monitor.make_httpx_fetcher",
        lambda: (lambda _url: None),
    )
    monkeypatch.setattr(
        "app.services.career_monitor.AutoPrepService.prepare_recent_discoveries",
        _fake_prepare_recent_discoveries,
    )

    result = await monitor._check_tracked_company_discoveries("u1")

    assert result["alerts"] == 2
    assert result["auto_prep_status"] == "ok"
    assert result["auto_prep_applications"] == 2
    assert result["auto_prep_jobs"] == 2
    assert len(db.alert_rows) == 2
    assert [alert["alert_type"] for alert in db.alert_rows] == [
        "tracked_company_discovery",
        "auto_prep_ready",
    ]
    assert db.alert_rows[1]["metadata"]["application_ids"] == ["app-1", "app-2"]


@pytest.mark.asyncio
async def test_run_full_scan_preserves_discovery_metrics(monkeypatch) -> None:
    monitor = AutonomousCareerMonitor(db=_FakeDB())

    async def _zero(_: str) -> int:
        return 0

    async def _discover(_: str) -> dict[str, Any]:
        return {
            "alerts": 1,
            "new_postings": 4,
            "scanned_companies": 5,
            "plans_attempted": 5,
            "failures": 0,
            "marked_scanned": 5,
        }

    async def _mission_sync(_: str) -> dict[str, Any]:
        return {
            "alerts": 0,
            "status": "ok",
            "missions_considered": 2,
            "missions_synced": 2,
            "scanned_applications": 11,
            "matched_applications": 3,
            "drafts_created": 2,
            "drafts_updated": 1,
            "draft_count": 4,
        }

    monkeypatch.setattr(monitor, "_check_profile_staleness", _zero)
    monkeypatch.setattr(monitor, "_check_evidence_decay", _zero)
    monkeypatch.setattr(monitor, "_check_document_freshness", _zero)
    monkeypatch.setattr(monitor, "_check_quality_regression", _zero)
    monkeypatch.setattr(monitor, "_check_interview_prep", _zero)
    monkeypatch.setattr(monitor, "_check_opportunity_match", _zero)
    monkeypatch.setattr(monitor, "_check_tracked_company_discoveries", _discover)
    monkeypatch.setattr(monitor, "_check_mission_inbox_sync", _mission_sync)

    result = await monitor.run_full_scan("u1")

    assert result["alerts_created"] == 1
    assert result["checks"]["tracked_company_discoveries"] == {
        "status": "ok",
        "alerts": 1,
        "new_postings": 4,
        "scanned_companies": 5,
        "plans_attempted": 5,
        "failures": 0,
        "marked_scanned": 5,
    }
    assert result["checks"]["mission_inbox_sync"] == {
        "status": "ok",
        "alerts": 0,
        "missions_considered": 2,
        "missions_synced": 2,
        "scanned_applications": 11,
        "matched_applications": 3,
        "drafts_created": 2,
        "drafts_updated": 1,
        "draft_count": 4,
    }


@pytest.mark.asyncio
async def test_check_mission_inbox_sync_returns_aggregated_metrics(monkeypatch) -> None:
    monitor = AutonomousCareerMonitor(db=_FakeDB())

    async def _fake_sync_user_missions(self, user_id: str, *, statuses=("active",), per_mission_limit=250):
        assert user_id == "u1"
        assert statuses == ("active",)
        return {
            "status": "ok",
            "missions_considered": 3,
            "missions_synced": 2,
            "created": 4,
            "updated": 2,
            "matched_applications": 5,
            "scanned_applications": 14,
            "draft_count": 7,
            "ready_for_user_promoted": 0,
            "ready_for_user_count": 0,
        }

    monkeypatch.setattr(
        "app.services.career_monitor.MissionControlService.sync_user_missions",
        _fake_sync_user_missions,
    )

    result = await monitor._check_mission_inbox_sync("u1")

    assert result == {
        "alerts": 0,
        "status": "ok",
        "missions_considered": 3,
        "missions_synced": 2,
        "scanned_applications": 14,
        "matched_applications": 5,
        "drafts_created": 4,
        "drafts_updated": 2,
        "draft_count": 7,
        "ready_for_user_promoted": 0,
        "ready_for_user_count": 0,
    }


@pytest.mark.asyncio
async def test_check_mission_inbox_sync_creates_ready_alert(monkeypatch) -> None:
    db = _FakeDB()
    monitor = AutonomousCareerMonitor(db=db)

    async def _fake_sync_user_missions(self, user_id: str, *, statuses=("active",), per_mission_limit=250):
        assert user_id == "u1"
        return {
            "status": "ok",
            "missions_considered": 1,
            "missions_synced": 1,
            "created": 2,
            "updated": 1,
            "matched_applications": 3,
            "scanned_applications": 9,
            "draft_count": 3,
            "ready_for_user_promoted": 2,
            "ready_for_user_count": 2,
        }

    monkeypatch.setattr(
        "app.services.career_monitor.MissionControlService.sync_user_missions",
        _fake_sync_user_missions,
    )

    result = await monitor._check_mission_inbox_sync("u1")

    assert result == {
        "alerts": 1,
        "status": "ok",
        "missions_considered": 1,
        "missions_synced": 1,
        "scanned_applications": 9,
        "matched_applications": 3,
        "drafts_created": 2,
        "drafts_updated": 1,
        "draft_count": 3,
        "ready_for_user_promoted": 2,
        "ready_for_user_count": 2,
    }
    assert len(db.alert_rows) == 1
    alert = db.alert_rows[0]
    assert alert["alert_type"] == "mission_inbox_ready"
    assert alert["action_url"] == "/missions"
    assert alert["metadata"]["ready_for_user_promoted"] == 2


@pytest.mark.asyncio
async def test_list_candidate_user_ids_unions_active_missions_and_enabled_watchlists() -> None:
    db = _FakeDB()
    db.mission_rows = [
        {"user_id": "u1", "status": "active", "created_at": "2026-05-09T00:00:00+00:00"},
        {"user_id": "u2", "status": "paused", "created_at": "2026-05-08T00:00:00+00:00"},
        {"user_id": "u3", "status": "active", "created_at": "2026-05-07T00:00:00+00:00"},
    ]
    db.tracked_company_rows = [
        {"user_id": "u3", "enabled": True, "last_scanned_at": "2026-05-09T00:00:00+00:00"},
        {"user_id": "u4", "enabled": True, "last_scanned_at": None},
        {"user_id": "u5", "enabled": False, "last_scanned_at": None},
    ]

    monitor = AutonomousCareerMonitor(db=db)

    assert await monitor.list_candidate_user_ids(limit=10) == ["u1", "u3", "u4"]


@pytest.mark.asyncio
async def test_run_scheduled_scan_batch_scans_candidate_users(monkeypatch) -> None:
    monitor = AutonomousCareerMonitor(db=_FakeDB())

    async def _fake_candidates(limit: int = 50):
        assert limit == 2
        return ["u1", "u2"]

    async def _fake_run_full_scan(user_id: str):
        return {"alerts_created": 1 if user_id == "u1" else 0}

    monkeypatch.setattr(monitor, "list_candidate_user_ids", _fake_candidates)
    monkeypatch.setattr(monitor, "run_full_scan", _fake_run_full_scan)

    result = await monitor.run_scheduled_scan_batch(limit=2)

    assert result == {
        "status": "ok",
        "candidate_count": 2,
        "scans_run": 2,
        "failures": 0,
        "alerts_created": 1,
        "user_ids": ["u1", "u2"],
    }