"""Unit tests for ScanHistoryService.

These tests never touch a real Supabase instance — they mock the fluent
client chain (``db.table(...).select(...).eq(...).execute()``).

Contract under test:
  • First scan for a URL creates a new row with times_seen=1, is_repost=False.
  • Subsequent scans increment times_seen AND only mark is_repost=True when
    BOTH times_seen >= 2 AND days-since-first_seen >= 90.
  • URLs with tracking params are canonicalized BEFORE storage/lookup so
    ?utm_source=x doesn't fragment the dedup set.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.scan_history_service import ScanHistoryService


def _build_fluent_mock(existing_row: dict | None = None) -> MagicMock:
    """Build a MagicMock that supports the Supabase-py fluent chain.

    Every chainable method returns the same mock so calls like
    ``db.table("x").select("*").eq("a", "b").execute()`` all resolve.
    ``execute()`` returns an object with ``.data`` = ``[existing_row]``
    (or ``[]`` if ``existing_row`` is None).
    """
    db = MagicMock()
    for method in ("table", "select", "insert", "upsert", "update", "delete",
                   "eq", "order", "limit"):
        getattr(db, method).return_value = db
    execute_result = MagicMock()
    execute_result.data = [existing_row] if existing_row else []
    db.execute.return_value = execute_result
    return db


def test_first_scan_creates_entry():
    db = _build_fluent_mock(existing_row=None)
    svc = ScanHistoryService(db)
    result = svc.record_scan(
        "https://boards.greenhouse.io/acme/jobs/123",
        company_slug="acme",
        role_title="AI Engineer",
    )
    assert result["times_seen"] == 1
    assert result["is_repost"] is False
    assert result["days_span"] == 0
    # Ensure upsert was called with canonical URL
    db.upsert.assert_called_once()
    stored = db.upsert.call_args[0][0]
    assert stored["url_canonical"] == "https://boards.greenhouse.io/acme/jobs/123"
    assert stored["company_slug"] == "acme"
    assert stored["times_seen"] == 1


def test_subsequent_scan_marks_as_repost_when_over_90_days_and_multiple_seen():
    now = datetime.now(timezone.utc)
    existing = {
        "id": "scan-1",
        "url_canonical": "https://boards.greenhouse.io/acme/jobs/123",
        "times_seen": 1,
        "first_seen": (now - timedelta(days=100)).isoformat(),
        "last_seen": (now - timedelta(days=50)).isoformat(),
    }
    db = _build_fluent_mock(existing_row=existing)
    svc = ScanHistoryService(db)
    result = svc.record_scan(
        "https://boards.greenhouse.io/acme/jobs/123",
        company_slug="acme",
        role_title="AI Engineer",
    )
    assert result["times_seen"] == 2
    assert result["is_repost"] is True
    assert result["days_span"] >= 90
    db.update.assert_called()


def test_reposting_requires_both_multiple_seen_and_90d_span():
    # Seen 3 times but all within 30 days — not a repost.
    now = datetime.now(timezone.utc)
    existing = {
        "id": "scan-2",
        "url_canonical": "https://jobs.lever.co/acme/abc",
        "times_seen": 3,
        "first_seen": (now - timedelta(days=20)).isoformat(),
        "last_seen": (now - timedelta(days=5)).isoformat(),
    }
    db = _build_fluent_mock(existing_row=existing)
    svc = ScanHistoryService(db)
    result = svc.record_scan(
        "https://jobs.lever.co/acme/abc",
        company_slug="acme",
        role_title="PM",
    )
    assert result["is_repost"] is False
    assert result["days_span"] < 90


def test_reposting_requires_multiple_sightings_even_if_old():
    # Single sighting 120 days ago (second scan now) — this is the
    # 2nd sighting, so at times_seen=2 with 120d span it IS a repost.
    now = datetime.now(timezone.utc)
    existing = {
        "id": "scan-3",
        "url_canonical": "https://jobs.ashbyhq.com/acme/xyz",
        "times_seen": 1,
        "first_seen": (now - timedelta(days=120)).isoformat(),
        "last_seen": (now - timedelta(days=120)).isoformat(),
    }
    db = _build_fluent_mock(existing_row=existing)
    svc = ScanHistoryService(db)
    result = svc.record_scan(
        "https://jobs.ashbyhq.com/acme/xyz",
        company_slug="acme",
        role_title="Eng",
    )
    assert result["times_seen"] == 2
    assert result["is_repost"] is True


def test_strips_tracking_before_store_and_lookup():
    db = _build_fluent_mock(existing_row=None)
    svc = ScanHistoryService(db)
    svc.record_scan(
        "https://boards.greenhouse.io/acme/jobs/123?utm_source=linkedin",
        company_slug="acme",
        role_title="Eng",
    )
    # Lookup should be canonical
    eq_calls = db.eq.call_args_list
    assert any(
        call.args == ("url_canonical", "https://boards.greenhouse.io/acme/jobs/123")
        for call in eq_calls
    ), f"Expected canonical lookup, got: {[c.args for c in eq_calls]}"
    # Upsert should also store canonical
    stored = db.upsert.call_args[0][0]
    assert stored["url_canonical"] == "https://boards.greenhouse.io/acme/jobs/123"


def test_company_slug_lowercased():
    db = _build_fluent_mock(existing_row=None)
    svc = ScanHistoryService(db)
    svc.record_scan(
        "https://boards.greenhouse.io/AcmeCorp/jobs/1",
        company_slug="AcmeCorp",
        role_title="Eng",
    )
    stored = db.upsert.call_args[0][0]
    assert stored["company_slug"] == "acmecorp"


def test_unknown_company_slug_fallback():
    db = _build_fluent_mock(existing_row=None)
    svc = ScanHistoryService(db)
    svc.record_scan(
        "https://example.com/careers/123",
        company_slug="",
        role_title="",
    )
    stored = db.upsert.call_args[0][0]
    assert stored["company_slug"] == "unknown"


def test_graceful_on_malformed_first_seen():
    # If first_seen is unparseable, treat as 0 days span (defensive)
    existing = {
        "id": "scan-bad",
        "url_canonical": "https://boards.greenhouse.io/a/jobs/1",
        "times_seen": 2,
        "first_seen": "not-a-date",
        "last_seen": "also-bad",
    }
    db = _build_fluent_mock(existing_row=existing)
    svc = ScanHistoryService(db)
    result = svc.record_scan(
        "https://boards.greenhouse.io/a/jobs/1",
        company_slug="a",
        role_title="x",
    )
    # Malformed dates should not raise and should not mark as repost.
    assert result["is_repost"] is False
