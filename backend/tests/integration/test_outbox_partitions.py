"""
Integration test: `events_outbox` partition rotation (M7-A / ADR-0037).

Validates the contract from `docs/architecture/IMPLEMENTATION_MILESTONES.md`
M7-A: "next-month partition pre-created on staging at any point in time."

Two test classes:

1. `TestRotationMigrationStatic` — runs always. Verifies the migration
   file structure so a refactor that breaks the rotation contract is
   caught in unit-CI without a database.

2. `TestRotationLiveDB` — opt-in. Skipped unless `INTEGRATION_DB_URL`
   env var is set (staging CI / local manual). Connects, calls the
   rotation function, asserts ≥4 future months exist.

Run locally:
    INTEGRATION_DB_URL=postgresql://... pytest \\
        backend/tests/integration/test_outbox_partitions.py -v
"""
from __future__ import annotations

import datetime as dt
import os
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


# ─────────────────────────────────────────────────────────────────
# Static contract tests (always run)
# ─────────────────────────────────────────────────────────────────
class TestRotationMigrationStatic:
    """Lock the structure of the rotation migration. If any of these
    fail, ADR-0037 is being violated."""

    def setup_method(self) -> None:
        assert MIGRATION.exists(), f"Missing migration: {MIGRATION}"
        self.sql = MIGRATION.read_text(encoding="utf-8")

    def test_installs_pg_cron(self) -> None:
        assert re.search(
            r"CREATE\s+EXTENSION\s+IF\s+NOT\s+EXISTS\s+pg_cron",
            self.sql,
            re.IGNORECASE,
        ), "pg_cron extension install missing — ADR-0037 violation"

    def test_creates_audit_table_with_rls(self) -> None:
        assert "partition_rotation_audit" in self.sql
        assert re.search(
            r"ALTER\s+TABLE\s+public\.partition_rotation_audit\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
            self.sql,
            re.IGNORECASE,
        ), "partition_rotation_audit must have RLS enabled"

    def test_function_exists_with_signature(self) -> None:
        assert re.search(
            r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.ensure_events_outbox_partitions\s*\(\s*p_months_ahead\s+integer",
            self.sql,
            re.IGNORECASE,
        ), "ensure_events_outbox_partitions(integer) signature changed — ADR-0037 contract"

    def test_function_is_security_definer(self) -> None:
        # The function runs from cron context; SECURITY DEFINER + locked
        # search_path is required for safe scheduling.
        assert "SECURITY DEFINER" in self.sql
        assert re.search(
            r"SET\s+search_path\s*=\s*public,\s*pg_temp",
            self.sql,
            re.IGNORECASE,
        ), "Function must pin search_path (security)"

    def test_grants_locked_to_service_role(self) -> None:
        assert re.search(
            r"REVOKE\s+ALL\s+ON\s+FUNCTION\s+public\.ensure_events_outbox_partitions",
            self.sql,
            re.IGNORECASE,
        )
        assert re.search(
            r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.ensure_events_outbox_partitions\(integer\)\s+TO\s+service_role",
            self.sql,
            re.IGNORECASE,
        )

    def test_bootstrap_call_present(self) -> None:
        # Migration must call the function so the P0-1 gap is closed
        # on the same migration that lands.
        assert re.search(
            r"SELECT\s+public\.ensure_events_outbox_partitions\(4\)",
            self.sql,
            re.IGNORECASE,
        ), "Migration must bootstrap-call the function or P0-1 isn't closed"

    def test_cron_job_scheduled_daily(self) -> None:
        assert "events-outbox-rotation" in self.sql
        assert re.search(
            r"cron\.schedule\s*\(\s*'events-outbox-rotation'",
            self.sql,
            re.IGNORECASE,
        )
        # 00:01 UTC daily — '1 0 * * *'
        assert "'1 0 * * *'" in self.sql, "Daily 00:01 UTC schedule changed"

    def test_safety_header_present(self) -> None:
        # Migration safety override per check_migration_safety.py
        assert re.search(
            r"--\s*SAFETY:.*ADR-0037",
            self.sql,
        ), "Migration must declare its SAFETY override referencing ADR-0037"


# ─────────────────────────────────────────────────────────────────
# Live database tests (opt-in via env var)
# ─────────────────────────────────────────────────────────────────
INTEGRATION_DB_URL = os.environ.get("INTEGRATION_DB_URL", "").strip()
LIVE_REASON = "INTEGRATION_DB_URL not set; live partition test skipped"


@pytest.mark.skipif(not INTEGRATION_DB_URL, reason=LIVE_REASON)
class TestRotationLiveDB:
    """Live-DB contract:
    after migration applies + bootstrap call, partitions for the
    current month and the next 4 months MUST exist.
    """

    @pytest.fixture(scope="class")
    def conn(self):
        try:
            import psycopg2  # type: ignore
        except ImportError:
            pytest.skip("psycopg2 not installed; cannot run live DB test")
        c = psycopg2.connect(INTEGRATION_DB_URL)
        c.autocommit = True
        yield c
        c.close()

    def _expected_partition_names(self, months_ahead: int = 4) -> list[str]:
        today = dt.date.today().replace(day=1)
        names: list[str] = []
        for i in range(months_ahead + 1):
            year = today.year + ((today.month - 1 + i) // 12)
            month = ((today.month - 1 + i) % 12) + 1
            names.append(f"events_outbox_{year:04d}_{month:02d}")
        return names

    def test_function_callable(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT public.ensure_events_outbox_partitions(4);"
            )
            row = cur.fetchone()
            assert row is not None
            assert isinstance(row[0], int) and row[0] >= 0

    def test_next_four_months_exist(self, conn) -> None:
        # Call rotation first (idempotent), then verify presence.
        with conn.cursor() as cur:
            cur.execute("SELECT public.ensure_events_outbox_partitions(4);")
            cur.execute(
                """
                SELECT inhrelid::regclass::text AS partition
                FROM pg_inherits
                WHERE inhparent = 'public.events_outbox'::regclass
                """
            )
            present = {r[0].replace("public.", "") for r in cur.fetchall()}
        for expected in self._expected_partition_names(4):
            assert expected in present, (
                f"Missing partition {expected}; rotation contract broken. "
                f"Present: {sorted(present)}"
            )

    def test_audit_row_recorded(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ran_at FROM public.partition_rotation_audit
                WHERE table_name = 'events_outbox'
                ORDER BY ran_at DESC LIMIT 1
                """
            )
            row = cur.fetchone()
        assert row is not None, "No audit row — rotation function did not record"
        # Last run must be within the last 5 minutes (we just called it).
        last_run = row[0]
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=dt.timezone.utc)
        age = dt.datetime.now(dt.timezone.utc) - last_run
        assert age < dt.timedelta(minutes=5), (
            f"Audit row stale ({age}); rotation did not actually run"
        )

    def test_cron_job_active(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT active, schedule FROM cron.job WHERE jobname = 'events-outbox-rotation';"
            )
            row = cur.fetchone()
        assert row is not None, "Cron job 'events-outbox-rotation' missing — ADR-0037 violation"
        active, schedule = row
        assert active is True, "Cron job is inactive"
        assert schedule == "1 0 * * *", f"Schedule changed to {schedule!r}"
