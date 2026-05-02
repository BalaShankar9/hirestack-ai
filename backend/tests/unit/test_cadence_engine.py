"""A1 — cadence engine unit tests.

Pure-function coverage for the follow-up scheduling policy:
  * sequence: first → linkedin → second → cold_reopen
  * stop conditions: terminal status, response received, max beats
  * business-day arithmetic (skips weekends)
  * past-time guard (snaps to next business day)
  * linkedin skip when no contact
  * beats_due filter
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.cadence_engine import (
    FollowupBeat,
    _add_business_days,
    _coerce_dt,
    _last_template,
    _next_template,
    beats_due,
    next_followup_beat,
)


# Anchor: a Monday at 14:00 UTC (well-defined weekday for arithmetic).
MONDAY_2P = datetime(2026, 5, 4, 14, 0, tzinfo=timezone.utc)
FRIDAY_2P = datetime(2026, 5, 8, 14, 0, tzinfo=timezone.utc)
SUNDAY_2P = datetime(2026, 5, 10, 14, 0, tzinfo=timezone.utc)


def _app(**overrides):
    base = {
        "id": "app-1",
        "user_id": "user-1",
        "status": "submitted",
        "submitted_at": MONDAY_2P.isoformat(),
    }
    base.update(overrides)
    return base


# ── _coerce_dt ────────────────────────────────────────────────────────


def test_coerce_dt_handles_none_and_empty() -> None:
    assert _coerce_dt(None) is None
    assert _coerce_dt("") is None


def test_coerce_dt_handles_iso_with_z() -> None:
    out = _coerce_dt("2026-05-04T14:00:00Z")
    assert out == MONDAY_2P


def test_coerce_dt_handles_naive_string_assumes_utc() -> None:
    out = _coerce_dt("2026-05-04T14:00:00")
    assert out == MONDAY_2P


def test_coerce_dt_handles_naive_datetime_assumes_utc() -> None:
    naive = datetime(2026, 5, 4, 14, 0)
    out = _coerce_dt(naive)
    assert out == MONDAY_2P


def test_coerce_dt_returns_none_on_garbage() -> None:
    assert _coerce_dt("not a date") is None
    assert _coerce_dt(12345) is None


# ── _add_business_days ────────────────────────────────────────────────


def test_business_days_one_from_monday_lands_tuesday() -> None:
    out = _add_business_days(MONDAY_2P, 1)
    assert out.weekday() == 1  # Tuesday
    assert (out.hour, out.minute) == (9, 30)


def test_business_days_one_from_friday_skips_weekend() -> None:
    out = _add_business_days(FRIDAY_2P, 1)
    assert out.weekday() == 0  # Monday
    assert out.date() > FRIDAY_2P.date()


def test_business_days_seven_from_monday() -> None:
    # 7 business days from Monday = following Wednesday (5 weekdays + 2)
    out = _add_business_days(MONDAY_2P, 7)
    assert out.weekday() == 2  # Wednesday
    delta = (out.date() - MONDAY_2P.date()).days
    assert delta == 9  # 7 weekdays + 2 weekend days


def test_business_days_zero_is_noop_on_date_but_snaps_time() -> None:
    out = _add_business_days(MONDAY_2P, 0)
    assert out.date() == MONDAY_2P.date()
    assert (out.hour, out.minute) == (9, 30)


# ── _last_template / _next_template ───────────────────────────────────


def test_last_template_empty_history() -> None:
    assert _last_template([]) is None
    assert _last_template(None) is None  # type: ignore[arg-type]


def test_last_template_picks_latest_in_sequence_order() -> None:
    history = [
        {"template_key": "first", "status": "sent"},
        {"template_key": "second", "status": "sent"},
        {"template_key": "linkedin", "status": "sent"},
    ]
    # 'second' is later in the sequence than 'linkedin' → expect 'second'
    assert _last_template(history) == "second"


def test_last_template_ignores_dismissed_and_expired() -> None:
    history = [
        {"template_key": "first", "status": "sent"},
        {"template_key": "linkedin", "status": "dismissed"},
        {"template_key": "second", "status": "expired"},
    ]
    assert _last_template(history) == "first"


def test_next_template_progression() -> None:
    assert _next_template(None) == "first"
    assert _next_template("first") == "linkedin"
    assert _next_template("linkedin") == "second"
    assert _next_template("second") == "cold_reopen"
    assert _next_template("cold_reopen") is None


def test_next_template_unknown_input_falls_back_to_first() -> None:
    assert _next_template("nope") == "first"  # type: ignore[arg-type]


# ── next_followup_beat: terminal statuses ─────────────────────────────


@pytest.mark.parametrize("status", ["rejected", "offer", "discarded", "withdrawn", "archived", "skip"])
def test_terminal_status_returns_none(status) -> None:
    assert next_followup_beat(_app(status=status)) is None


def test_returns_none_for_non_mapping_application() -> None:
    assert next_followup_beat("not a dict") is None  # type: ignore[arg-type]
    assert next_followup_beat(None) is None  # type: ignore[arg-type]


def test_returns_none_when_no_submitted_at() -> None:
    assert next_followup_beat(_app(submitted_at=None, status="draft")) is None


# ── First beat ────────────────────────────────────────────────────────


def test_first_beat_one_business_day_after_submitted() -> None:
    beat = next_followup_beat(_app(), now=MONDAY_2P)
    assert beat is not None
    assert beat.template_key == "first"
    assert beat.channel == "email"
    assert beat.followup_count == 1
    # Tuesday at 09:30 UTC
    assert beat.scheduled_for == datetime(2026, 5, 5, 9, 30, tzinfo=timezone.utc)
    assert "first nudge" in beat.reason


def test_first_beat_from_friday_lands_on_monday() -> None:
    beat = next_followup_beat(_app(submitted_at=FRIDAY_2P.isoformat()), now=FRIDAY_2P)
    assert beat is not None
    assert beat.scheduled_for.weekday() == 0  # Monday


# ── Second beat (linkedin) ────────────────────────────────────────────


def test_linkedin_beat_when_contact_known() -> None:
    history = [{"template_key": "first", "status": "sent"}]
    beat = next_followup_beat(
        _app(contact_linkedin="https://linkedin.com/in/x"),
        history=history,
        now=MONDAY_2P,
    )
    assert beat is not None
    assert beat.template_key == "linkedin"
    assert beat.channel == "linkedin"
    assert beat.followup_count == 2


def test_linkedin_beat_skipped_when_no_contact_progresses_to_second() -> None:
    history = [{"template_key": "first", "status": "sent"}]
    beat = next_followup_beat(_app(), history=history, now=MONDAY_2P)
    assert beat is not None
    assert beat.template_key == "second"
    assert beat.channel == "email"


# ── Second / cold_reopen suppressed when responded ────────────────────


def test_second_beat_suppressed_when_response_received() -> None:
    history = [
        {"template_key": "first", "status": "sent"},
        {"template_key": "linkedin", "status": "sent"},
    ]
    beat = next_followup_beat(
        _app(response_received_at=MONDAY_2P.isoformat(), status="responded"),
        history=history,
        now=MONDAY_2P,
    )
    assert beat is None


def test_cold_reopen_suppressed_when_response_received() -> None:
    history = [
        {"template_key": "first", "status": "sent"},
        {"template_key": "linkedin", "status": "sent"},
        {"template_key": "second", "status": "sent"},
    ]
    beat = next_followup_beat(
        _app(response_received_at=MONDAY_2P.isoformat(), status="responded"),
        history=history,
        now=MONDAY_2P,
    )
    assert beat is None


# ── Cold reopen path (full sequence with no response) ────────────────


def test_cold_reopen_emitted_when_silent_and_three_beats_done() -> None:
    history = [
        {"template_key": "first", "status": "sent"},
        {"template_key": "linkedin", "status": "sent"},
        {"template_key": "second", "status": "sent"},
    ]
    beat = next_followup_beat(
        _app(contact_linkedin="x"),
        history=history,
        now=MONDAY_2P,
    )
    assert beat is not None
    assert beat.template_key == "cold_reopen"
    assert beat.followup_count == 4


def test_no_more_beats_after_cold_reopen() -> None:
    history = [
        {"template_key": "first", "status": "sent"},
        {"template_key": "linkedin", "status": "sent"},
        {"template_key": "second", "status": "sent"},
        {"template_key": "cold_reopen", "status": "sent"},
    ]
    beat = next_followup_beat(_app(), history=history, now=MONDAY_2P)
    assert beat is None


def test_max_four_beats_enforced_even_with_unusual_history() -> None:
    history = [
        {"template_key": "first", "status": "sent"},
        {"template_key": "first", "status": "sent"},
        {"template_key": "second", "status": "sent"},
        {"template_key": "cold_reopen", "status": "sent"},
    ]
    beat = next_followup_beat(_app(), history=history, now=MONDAY_2P)
    assert beat is None


# ── Past-time guard ───────────────────────────────────────────────────


def test_past_scheduled_time_snaps_to_next_business_day() -> None:
    # Submitted last month → +1 business day is well in the past.
    long_ago = MONDAY_2P - timedelta(days=30)
    beat = next_followup_beat(
        _app(submitted_at=long_ago.isoformat()),
        now=MONDAY_2P,
    )
    assert beat is not None
    # Must be in the future relative to `now`.
    assert beat.scheduled_for > MONDAY_2P
    # Must be a weekday at 09:30 UTC.
    assert beat.scheduled_for.weekday() < 5
    assert (beat.scheduled_for.hour, beat.scheduled_for.minute) == (9, 30)


# ── to_row serialization ──────────────────────────────────────────────


def test_to_row_shape_matches_table_columns() -> None:
    beat = FollowupBeat(
        template_key="first",
        scheduled_for=MONDAY_2P,
        channel="email",
        followup_count=1,
        reason="…",
    )
    row = beat.to_row(
        application_id="app-1",
        user_id="user-1",
        contact_email="hr@example.com",
    )
    assert row["application_id"] == "app-1"
    assert row["user_id"] == "user-1"
    assert row["template_key"] == "first"
    assert row["channel"] == "email"
    assert row["status"] == "pending"
    assert row["followup_count"] == 1
    assert row["contact_email"] == "hr@example.com"
    assert row["contact_linkedin"] is None
    assert row["scheduled_for"] == MONDAY_2P.isoformat()


# ── beats_due ─────────────────────────────────────────────────────────


def test_beats_due_filters_to_pending_and_due() -> None:
    rows = [
        {"id": "a", "status": "pending", "scheduled_for": (MONDAY_2P - timedelta(hours=1)).isoformat()},
        {"id": "b", "status": "pending", "scheduled_for": (MONDAY_2P + timedelta(hours=1)).isoformat()},
        {"id": "c", "status": "sent", "scheduled_for": (MONDAY_2P - timedelta(hours=1)).isoformat()},
        {"id": "d", "status": "draft_ready", "scheduled_for": (MONDAY_2P - timedelta(hours=1)).isoformat()},
        {"id": "e", "status": "pending", "scheduled_for": "garbage"},
    ]
    due = beats_due(rows, now=MONDAY_2P)
    assert [r["id"] for r in due] == ["a"]


def test_beats_due_handles_empty_and_invalid_input() -> None:
    assert beats_due([]) == []
    assert beats_due(None) == []  # type: ignore[arg-type]
    # Non-mapping entries silently skipped.
    assert beats_due([1, "x", None], now=MONDAY_2P) == []  # type: ignore[list-item]


# ── Determinism ───────────────────────────────────────────────────────


def test_engine_is_deterministic_for_same_input() -> None:
    a1 = next_followup_beat(_app(), now=MONDAY_2P)
    a2 = next_followup_beat(_app(), now=MONDAY_2P)
    assert a1 == a2


def test_engine_does_not_mutate_input() -> None:
    app_in = _app()
    snap = dict(app_in)
    history_in = [{"template_key": "first", "status": "sent"}]
    snap_h = [dict(h) for h in history_in]
    next_followup_beat(app_in, history=history_in, now=MONDAY_2P)
    assert app_in == snap
    assert history_in == snap_h
