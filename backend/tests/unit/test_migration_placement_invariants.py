"""Migration placement invariant tests — Rank 6.

As of m9-pr33 (M10), `supabase/migrations/` is the SOLE migration root.
The legacy `database/migrations/` directory has been deleted to remove
the orphan trap that caused the S2 schema-drift incident
(``20260422_widen_generation_jobs_status.sql`` widened
``generation_jobs.status`` from VARCHAR(20) → VARCHAR(30) for
``succeeded_with_warnings`` only in ``database/migrations/`` — production
Supabase never saw it and threw ``value too long for type character
varying(20)``).

These tests now verify (against the single root):
  1. The widen migration exists in ``supabase/migrations/``.
  2. The effective ``generation_jobs.status`` column width in the full
     ``supabase/migrations/`` chain is at least 23 characters (the length
     of ``succeeded_with_warnings``).
  3. All known terminal status strings fit within the column definition.

Tests run fully offline — no DB connection required.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Paths ──────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parents[3]  # …/HireStack AI
_SUPABASE_MIG_DIR = _REPO_ROOT / "supabase" / "migrations"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _supabase_chain_sql() -> str:
    """Return concatenated SQL of all supabase migrations sorted by filename."""
    files = sorted(_SUPABASE_MIG_DIR.glob("*.sql"))
    return "\n".join(f.read_text() for f in files)


def _extract_varchar_width(sql: str, table: str, column: str) -> int | None:
    """
    Scan ``sql`` and return the *last* declared or altered VARCHAR width for
    ``table.column``.

    Handles both:
      CREATE TABLE … (status VARCHAR(20) …)
      ALTER TABLE … ALTER COLUMN status TYPE VARCHAR(30)   ← may be multi-line
    Returns None if the column is not found.
    """
    last_width: int | None = None

    # ── Pattern 1: column definition inside CREATE TABLE block ──────────
    create_block_re = re.compile(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?{re.escape(table)}\b"
        rf".*?\b{re.escape(column)}\s+VARCHAR\((\d+)\)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in create_block_re.finditer(sql):
        last_width = int(m.group(1))

    # ── Pattern 2: ALTER TABLE … ALTER COLUMN … TYPE VARCHAR(n) ─────────
    alter_block_re = re.compile(
        rf"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?{re.escape(table)}\b"
        rf".*?ALTER\s+COLUMN\s+{re.escape(column)}\s+(?:SET\s+DATA\s+)?TYPE\s+VARCHAR\((\d+)\)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in alter_block_re.finditer(sql):
        last_width = int(m.group(1))

    return last_width


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestWidenMigrationPlacement:
    """The 'succeeded_with_warnings' widen migration must live in supabase/."""

    def test_widen_migration_exists_in_supabase_dir(self) -> None:
        """supabase/migrations/ must contain the widen migration file."""
        files = list(_SUPABASE_MIG_DIR.glob("*widen_generation_jobs_status*"))
        assert files, (
            "supabase/migrations/ is missing the generation_jobs status widen migration.  "
            "Production Supabase will fail with 'value too long for type character varying(20)' "
            "when persisting 'succeeded_with_warnings'.  "
            "Create supabase/migrations/20260422000000_widen_generation_jobs_status.sql."
        )

    def test_supabase_widen_migration_contains_alter_statement(self) -> None:
        """The supabase widen migration must contain the actual ALTER TABLE."""
        files = sorted(_SUPABASE_MIG_DIR.glob("*widen_generation_jobs_status*"))
        assert files, "Widen migration file not found in supabase/migrations/"
        content = files[-1].read_text()
        assert re.search(
            r"ALTER\s+TABLE.*generation_jobs.*ALTER\s+COLUMN.*status.*TYPE.*VARCHAR\(\d+\)",
            content,
            re.IGNORECASE | re.DOTALL,
        ), f"Expected ALTER TABLE ... ALTER COLUMN status TYPE VARCHAR(n) in {files[-1].name}"


class TestEffectiveStatusColumnWidth:
    """The supabase migration chain must end up with a wide enough status column."""

    _MIN_REQUIRED = 23  # len('succeeded_with_warnings')

    def test_effective_status_width_is_at_least_23(self) -> None:
        """Full supabase migration chain must define status as VARCHAR(≥23)."""
        sql = _supabase_chain_sql()
        width = _extract_varchar_width(sql, "generation_jobs", "status")
        assert width is not None, (
            "Could not determine generation_jobs.status column width from "
            "supabase/migrations/.  Check that 20260209000000_generation_jobs.sql exists."
        )
        assert width >= self._MIN_REQUIRED, (
            f"generation_jobs.status is VARCHAR({width}) in the supabase migration chain.  "
            f"The status 'succeeded_with_warnings' ({self._MIN_REQUIRED} chars) will overflow.  "
            f"Apply 20260422000000_widen_generation_jobs_status.sql."
        )

    def test_effective_status_width_is_exactly_30(self) -> None:
        """The widen migration targets VARCHAR(30) — pin this so regressions are visible."""
        sql = _supabase_chain_sql()
        width = _extract_varchar_width(sql, "generation_jobs", "status")
        assert width == 30, (
            f"Expected generation_jobs.status to be VARCHAR(30) after the widen migration, "
            f"got VARCHAR({width}).  If the column was intentionally widened further, "
            f"update this test."
        )

    @pytest.mark.parametrize("status", [
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "succeeded_with_warnings",
    ])
    def test_all_terminal_statuses_fit_in_column(self, status: str) -> None:
        """Every status string used by the backend must fit in the column width."""
        sql = _supabase_chain_sql()
        width = _extract_varchar_width(sql, "generation_jobs", "status")
        assert width is not None
        assert len(status) <= width, (
            f"Status '{status}' is {len(status)} chars but column is VARCHAR({width}).  "
            f"Widen the column."
        )
