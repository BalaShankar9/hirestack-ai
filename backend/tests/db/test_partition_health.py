"""Partition health invariants for `events_outbox` rotation (m12-pr16).

Companion to `backend/tests/integration/test_outbox_partitions.py` — that
file pins migration *structure* and (opt-in) live-DB behaviour. This
file pins:

1. The pure time math the SQL function depends on (year roll, format).
2. Cross-file contract between the migration's bootstrap call, the cron
   command, and the runbook's alert window.
3. The exception-path audit invariant (silent failures must still leave
   a trace) — text-pinned in the migration.
4. Audit-table schema columns the alerting query depends on.

If any of these break, the daily rotation may keep running while the
runbook silently no longer matches reality. ADR-0037.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260508120000_outbox_partition_rotation.sql"
)
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "outbox-partitions.md"
ADR = REPO_ROOT / "docs" / "adrs" / "0037-partition-rotation-strategy.md"

# Bounds asserted in the SQL `RAISE EXCEPTION` clause.
MAX_MONTHS_AHEAD = 24
MIN_MONTHS_AHEAD = 0
# Bootstrap + cron call this with months_ahead=4 (must match).
EXPECTED_MONTHS_AHEAD = 4
# Daily 00:01 UTC schedule.
EXPECTED_CRON = "1 0 * * *"
# Runbook alert window (cron cadence 24h + 12h grace = 36h).
RUNBOOK_ALERT_HOURS = 36


# ── Pure helper that mirrors the SQL function's loop -----------------


def _expected_partition_names(today: dt.date, months_ahead: int) -> list[str]:
    """Mirror of the SQL loop:

        FOR i IN 0..p_months_ahead LOOP
            start_d := date_trunc('month', now()) + (i || ' month')::interval;
            pname   := format('events_outbox_%s', to_char(start_d, 'YYYY_MM'));

    Returns ``months_ahead + 1`` partition names (current + next N).
    """
    base = today.replace(day=1)
    names: list[str] = []
    for i in range(months_ahead + 1):
        year = base.year + ((base.month - 1 + i) // 12)
        month = ((base.month - 1 + i) % 12) + 1
        names.append(f"events_outbox_{year:04d}_{month:02d}")
    return names


# ── Time-math invariants --------------------------------------------


def test_partition_name_format_zero_pads_year_and_month() -> None:
    names = _expected_partition_names(dt.date(2026, 5, 9), months_ahead=0)
    assert names == ["events_outbox_2026_05"]


def test_partition_name_includes_current_month_plus_n() -> None:
    """months_ahead=4 yields 5 names (current + next four)."""
    names = _expected_partition_names(dt.date(2026, 5, 9), months_ahead=4)
    assert len(names) == 5
    assert names[0] == "events_outbox_2026_05"
    assert names[-1] == "events_outbox_2026_09"


def test_partition_name_rolls_year_at_december() -> None:
    """Starting in Nov 2026, ahead=4 must include 2027_01 through 2027_03."""
    names = _expected_partition_names(dt.date(2026, 11, 30), months_ahead=4)
    assert names == [
        "events_outbox_2026_11",
        "events_outbox_2026_12",
        "events_outbox_2027_01",
        "events_outbox_2027_02",
        "events_outbox_2027_03",
    ]


def test_partition_name_handles_two_year_span_at_max_lookahead() -> None:
    """months_ahead=24 from Nov 2026 spans 25 months across 3 calendar years."""
    names = _expected_partition_names(dt.date(2026, 11, 30), months_ahead=24)
    assert len(names) == 25
    assert names[0] == "events_outbox_2026_11"
    assert names[-1] == "events_outbox_2028_11"
    # Strict monotonic ordering — no duplicates, no skipped months.
    assert names == sorted(names)
    assert len(set(names)) == 25


def test_partition_name_day_of_month_does_not_affect_partition() -> None:
    """``date_trunc('month', ...)`` makes day-of-month irrelevant. The
    SQL function uses it; the test helper must too."""
    a = _expected_partition_names(dt.date(2026, 5, 1), months_ahead=2)
    b = _expected_partition_names(dt.date(2026, 5, 31), months_ahead=2)
    assert a == b


# ── Migration <-> runbook <-> ADR cross-file contracts ---------------


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert MIGRATION.exists(), f"Missing migration: {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


def test_bootstrap_and_cron_use_identical_months_ahead(migration_sql: str) -> None:
    """If bootstrap creates 4 months and cron creates fewer, the system
    drifts to under-provisioned the moment the bootstrap horizon passes."""
    bootstrap = re.findall(
        r"SELECT\s+public\.ensure_events_outbox_partitions\((\d+)\)",
        migration_sql,
        re.IGNORECASE,
    )
    cron = re.findall(
        r"ensure_events_outbox_partitions\((\d+)\)\s*;\s*\$cmd\$",
        migration_sql,
        re.IGNORECASE,
    )
    assert bootstrap, "bootstrap call missing"
    assert cron, "cron command argument missing"
    bootstrap_n = {int(x) for x in bootstrap}
    cron_n = {int(x) for x in cron}
    assert bootstrap_n == cron_n == {EXPECTED_MONTHS_AHEAD}, (
        f"bootstrap={bootstrap_n} cron={cron_n} expected={EXPECTED_MONTHS_AHEAD}"
    )


def test_function_rejects_negative_and_overlarge_months_ahead(migration_sql: str) -> None:
    """0 ≤ p_months_ahead ≤ 24 is the safety guard. If removed, a typo
    in the cron command could create thousands of partitions."""
    assert re.search(
        r"p_months_ahead\s*<\s*0\s+OR\s+p_months_ahead\s*>\s*24",
        migration_sql,
        re.IGNORECASE,
    ), "Bounds check on p_months_ahead missing — runaway-partition guard removed"
    # And the human-readable bounds in the error must match the constants.
    assert re.search(
        r"between\s+0\s+and\s+24",
        migration_sql,
        re.IGNORECASE,
    )


def test_exception_path_records_audit_row_with_error_message(migration_sql: str) -> None:
    """If the rotation function raises (e.g. permission denied on a
    child table), the EXCEPTION block MUST still write an audit row
    so the staleness alert fires on the audit-row freshness, not on
    the lack of an audit row."""
    # Look for the exception handler followed by an INSERT into the audit
    # table that includes ``err_msg`` (the captured error message).
    assert re.search(
        r"EXCEPTION\s+WHEN\s+OTHERS\s+THEN[\s\S]+?"
        r"INSERT\s+INTO\s+public\.partition_rotation_audit[\s\S]+?"
        r"err_msg",
        migration_sql,
        re.IGNORECASE,
    ), "Exception path must insert an audit row with the error message"


def test_audit_table_columns_pinned(migration_sql: str) -> None:
    """The Prometheus alerting query reads these columns; renaming any
    of them silently breaks the alert."""
    required = [
        ("table_name", "text"),
        ("ran_at", "timestamptz"),
        ("months_ahead", "integer"),
        ("partitions_created", "integer"),
        ("error_message", "text"),
    ]
    for col, sqltype in required:
        # Allow flexible whitespace; column declared on its own line.
        assert re.search(
            rf"\b{col}\s+{sqltype}\b",
            migration_sql,
            re.IGNORECASE,
        ), f"audit column {col} {sqltype} renamed/removed"


def test_cron_command_calls_function_and_nothing_else(migration_sql: str) -> None:
    """The cron command body must be a bare function call. A wrapper
    that swallows errors would mask P0-1 regressions."""
    cmd_match = re.search(
        r"\$cmd\$\s*(.+?)\s*\$cmd\$",
        migration_sql,
        re.DOTALL,
    )
    assert cmd_match, "Cron command body not found"
    body = cmd_match.group(1).strip().rstrip(";").strip()
    assert body == f"SELECT public.ensure_events_outbox_partitions({EXPECTED_MONTHS_AHEAD})", body


def test_cron_schedule_is_daily_at_one_past_midnight_utc(migration_sql: str) -> None:
    assert f"'{EXPECTED_CRON}'" in migration_sql, (
        f"Cron schedule changed away from {EXPECTED_CRON!r}"
    )


def test_runbook_alert_window_matches_cron_cadence_plus_grace() -> None:
    """Runbook claims the alert fires when the audit row is > 36h old.
    The cron runs every 24h, so 36h = 1.5 cycles = one missed run + 12h
    grace. If the runbook drifts (e.g. someone updates the cron to
    twice-daily and forgets the alert), this test catches it."""
    assert RUNBOOK.exists(), f"Missing runbook: {RUNBOOK}"
    text = RUNBOOK.read_text(encoding="utf-8")
    assert f"> {RUNBOOK_ALERT_HOURS}h" in text, (
        f"Runbook alert window {RUNBOOK_ALERT_HOURS}h missing — "
        "cron cadence + grace contract drifted"
    )


def test_adr_marked_accepted() -> None:
    """ADR-0037 must remain Accepted; downgrading it without a
    superseding ADR would orphan the migration."""
    assert ADR.exists(), f"Missing ADR: {ADR}"
    text = ADR.read_text(encoding="utf-8")
    assert re.search(r"Status:\s*Accepted", text, re.IGNORECASE), (
        "ADR-0037 status changed away from Accepted"
    )


def test_safety_header_references_adr_0037(migration_sql: str) -> None:
    """`scripts/governance/check_migration_safety.py` greps for this
    header. Without it the migration is a hard CI fail."""
    assert re.search(r"--\s*SAFETY:.*ADR-0037", migration_sql), (
        "SAFETY header missing or no longer references ADR-0037"
    )


# ── Pure-helper sanity vs. constants ---------------------------------


def test_helper_count_matches_expected_months_ahead_constant() -> None:
    """Lock the relationship: helper(N) returns N+1 names."""
    n = EXPECTED_MONTHS_AHEAD
    assert len(_expected_partition_names(dt.date(2026, 5, 9), n)) == n + 1
