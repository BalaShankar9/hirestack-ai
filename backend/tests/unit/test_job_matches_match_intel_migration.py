"""Pin additive migration for richer job-match scoring fields.

Both schema trees must add the same columns so application-layer
job_sync writes do not diverge between local and Supabase paths.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_MIGRATION = REPO_ROOT / "database" / "migrations" / "20260506_job_matches_match_intel.sql"
SUPABASE_MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260506010000_job_matches_match_intel.sql"


def _read(path: Path) -> str:
    assert path.exists(), f"Migration missing: {path}"
    return path.read_text()


def test_database_migration_adds_missing_skills_and_recommendation() -> None:
    sql = _read(DB_MIGRATION)
    assert "ALTER TABLE job_matches" in sql
    assert "ADD COLUMN IF NOT EXISTS missing_skills JSONB" in sql
    assert "ADD COLUMN IF NOT EXISTS recommendation VARCHAR(20)" in sql
    assert "DEFAULT '[]'::jsonb" in sql
    assert "DEFAULT 'consider'" in sql


def test_supabase_migration_adds_missing_skills_and_recommendation() -> None:
    sql = _read(SUPABASE_MIGRATION)
    assert "ALTER TABLE public.job_matches" in sql
    assert "ADD COLUMN IF NOT EXISTS missing_skills JSONB" in sql
    assert "ADD COLUMN IF NOT EXISTS recommendation VARCHAR(20)" in sql
    assert "DEFAULT '[]'::jsonb" in sql
    assert "DEFAULT 'consider'" in sql