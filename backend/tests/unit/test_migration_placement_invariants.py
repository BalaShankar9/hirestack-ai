"""Migration placement invariant tests — Rank 6.

Supabase deploys from ``supabase/migrations/``.
Legacy patches land in ``database/migrations/``.

If a critical schema change only goes into ``database/migrations/`` it is an
*orphan* — production Supabase never sees it.  This happened with
``20260422_widen_generation_jobs_status.sql`` (VARCHAR 20→30 for
``succeeded_with_warnings``), which caused a live Postgres error when the
backend tried to persist the new status.

These tests verify:
  1. The widen migration exists in *both* directories.
  2. The effective ``generation_jobs.status`` column width in the full
     ``supabase/migrations/`` chain is at least 23 characters (the length of
     ``succeeded_with_warnings``).
  3. A curated sentinel list of critical migrations from ``database/migrations/``
     each have a corresponding counterpart in ``supabase/migrations/``.
  4. All known terminal status strings fit within the column definition.

Tests run fully offline — no DB connection required.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Paths ──────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parents[3]  # …/HireStack AI
_SUPABASE_MIG_DIR = _REPO_ROOT / "supabase" / "migrations"
_DATABASE_MIG_DIR = _REPO_ROOT / "database" / "migrations"

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
    # Match CREATE TABLE [IF NOT EXISTS] [public.]<table> … <column> VARCHAR(n)
    create_block_re = re.compile(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?{re.escape(table)}\b"
        rf".*?\b{re.escape(column)}\s+VARCHAR\((\d+)\)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in create_block_re.finditer(sql):
        last_width = int(m.group(1))

    # ── Pattern 2: ALTER TABLE … ALTER COLUMN … TYPE VARCHAR(n) ─────────
    # The ALTER TABLE and ALTER COLUMN may span multiple lines.
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
    """The 'succeeded_with_warnings' widen migration must live in both dirs."""

    def test_widen_migration_exists_in_supabase_dir(self) -> None:
        """supabase/migrations/ must contain the widen migration file."""
        files = list(_SUPABASE_MIG_DIR.glob("*widen_generation_jobs_status*"))
        assert files, (
            "supabase/migrations/ is missing the generation_jobs status widen migration.  "
            "Production Supabase will fail with 'value too long for type character varying(20)' "
            "when persisting 'succeeded_with_warnings'.  "
            "Create supabase/migrations/20260422000000_widen_generation_jobs_status.sql."
        )

    def test_widen_migration_exists_in_database_dir(self) -> None:
        """database/migrations/ must also retain the source-of-truth file."""
        files = list(_DATABASE_MIG_DIR.glob("*widen_generation_jobs_status*"))
        assert files, (
            "database/migrations/ is missing the widen migration — this is the human-readable "
            "record.  Both directories should have this file."
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


class TestCriticalMigrationsMirrored:
    """
    Known-critical ``database/migrations/`` files must each have a functional
    counterpart in ``supabase/migrations/``.

    When you add a new migration to database/migrations/ that changes production
    schema, add its *intent* to _REQUIRED_INTENTS below so this test continues
    to guard against future orphans.
    """

    # Each entry is (database/ stem hint, supabase/ stem hint).
    # We use partial-name matching so timestamp prefixes don't matter.
    _REQUIRED_INTENTS: list[tuple[str, str]] = [
        # (database/ partial name,   supabase/ partial name)
        ("add_resume_html",          "add_resume_html"),
        ("knowledge_library",        "knowledge_library"),
        ("widen_generation_jobs",    "widen_generation_jobs"),
    ]

    def _supabase_stems(self) -> list[str]:
        return [f.stem for f in _SUPABASE_MIG_DIR.glob("*.sql")]

    def _database_stems(self) -> list[str]:
        return [f.stem for f in _DATABASE_MIG_DIR.glob("*.sql")]

    @pytest.mark.parametrize("db_hint,supa_hint", _REQUIRED_INTENTS)
    def test_migration_mirrored(self, db_hint: str, supa_hint: str) -> None:
        """A database/migrations/ file matching *db_hint* must be mirrored in supabase/."""
        db_stems = self._database_stems()
        supa_stems = self._supabase_stems()

        # Confirm the source exists
        db_match = [s for s in db_stems if db_hint in s]
        assert db_match, (
            f"database/migrations/ has no file matching '{db_hint}'.  "
            f"Remove this entry from _REQUIRED_INTENTS if the migration was retired."
        )

        # Confirm the mirror exists
        supa_match = [s for s in supa_stems if supa_hint in s]
        assert supa_match, (
            f"supabase/migrations/ has no file matching '{supa_hint}'.  "
            f"This migration is ORPHANED — production Supabase will never apply it.  "
            f"Create supabase/migrations/<timestamp>_{supa_hint}.sql."
        )
