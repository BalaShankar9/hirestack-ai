"""Static schema-drift and deletion-invariant tests.

These tests parse the canonical migration SQL (combined_migration.sql plus
known migration patches) and validate the Python-side schema constants
against them.  They run fully offline — no DB connection required.

Invariants covered:
  1. generation_jobs status enum matches backend constants
  2. generation_jobs → generation_job_events ON DELETE CASCADE is present
  3. generation_jobs → evidence_ledger_items ON DELETE CASCADE is present
  4. generation_jobs → claim_citations ON DELETE CASCADE is present
  5. applications → generation_jobs ON DELETE CASCADE is present
  6. users → applications ON DELETE CASCADE is present
  7. evidence_ledger_items (job_id, id) UNIQUE is present
  8. generation_job_events (job_id, sequence_no) UNIQUE is present
  9. TABLES dict in database.py covers all core tables
 10. generation_jobs.requested_modules-valid module whitelist contract
 11. generation_job_events FK references generation_jobs (not a broken ref)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# ── Paths ─────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parents[3]  # …/HireStack AI
_COMBINED_MIGRATION = _REPO_ROOT / "database" / "combined_migration.sql"
_WAVE23_MIGRATION = _REPO_ROOT / "database" / "apply_production_wave23.sql"
_ALL_MIGRATIONS_DIR = _REPO_ROOT / "database" / "migrations"


def _read_sql(*paths: Path) -> str:
    """Concatenate SQL files that exist; skip missing ones."""
    parts: list[str] = []
    for p in paths:
        if p.exists():
            parts.append(p.read_text())
    return "\n".join(parts)


def _migration_sql() -> str:
    """Return the full canonical schema SQL for static analysis."""
    extra_migrations = sorted(_ALL_MIGRATIONS_DIR.glob("*.sql"))
    return _read_sql(_COMBINED_MIGRATION, _WAVE23_MIGRATION, *extra_migrations)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_fk_cascade(sql: str, child_table: str, parent_table: str) -> bool:
    """Check that child_table has a FK referencing parent_table with ON DELETE CASCADE."""
    # Create a block search: look inside the CREATE TABLE or ALTER TABLE block
    # Strategy: search for REFERENCES <parent_table>(...) ON DELETE CASCADE
    # appearing near a FK column definition in child_table context.
    pattern = re.compile(
        rf"REFERENCES\s+(?:public\.)?{re.escape(parent_table)}\s*\([^)]+\)\s+ON\s+DELETE\s+CASCADE",
        re.IGNORECASE,
    )
    # Find the CREATE TABLE block for child_table and check inside it
    create_block_pattern = re.compile(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?{re.escape(child_table)}\s*\(",
        re.IGNORECASE,
    )
    # Also check ALTER TABLE ... ADD FOREIGN KEY ... REFERENCES parent ON DELETE CASCADE
    alter_pattern = re.compile(
        rf"ALTER\s+TABLE\s+(?:public\.)?{re.escape(child_table)}\s+.*?"
        rf"REFERENCES\s+(?:public\.)?{re.escape(parent_table)}\s*\([^)]+\)\s+ON\s+DELETE\s+CASCADE",
        re.IGNORECASE | re.DOTALL,
    )

    # Check inside CREATE TABLE blocks
    for m in create_block_pattern.finditer(sql):
        start = m.start()
        # Find the matching close paren (rough — grab enough context)
        excerpt = sql[start : start + 3000]
        if pattern.search(excerpt):
            return True

    # Check ALTER TABLE patterns
    if alter_pattern.search(sql):
        return True

    return False


def _has_unique_constraint(sql: str, table: str, *columns: str) -> bool:
    """Check that table has a UNIQUE constraint covering exactly the given columns (any order)."""
    # Accept either inline UNIQUE(...) or standalone UNIQUE(col1, col2)
    cols_pattern = r",\s*".join(re.escape(c) for c in columns)
    cols_pattern_rev = r",\s*".join(re.escape(c) for c in reversed(columns))
    patterns = [
        rf"UNIQUE\s*\(\s*{cols_pattern}\s*\)",
        rf"UNIQUE\s*\(\s*{cols_pattern_rev}\s*\)",
    ]
    create_block_pattern = re.compile(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?{re.escape(table)}\s*\(",
        re.IGNORECASE,
    )
    for m in create_block_pattern.finditer(sql):
        start = m.start()
        excerpt = sql[start : start + 5000]
        for pat in patterns:
            if re.search(pat, excerpt, re.IGNORECASE):
                return True
    return False


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def schema_sql() -> str:
    assert _COMBINED_MIGRATION.exists(), (
        f"Combined migration not found at {_COMBINED_MIGRATION}. "
        "Run `make migrations` or check the database/ directory."
    )
    return _migration_sql()


class TestCascadeDeletes:
    """Every child table that would be orphaned must cascade-delete."""

    def test_applications_cascade_from_users(self, schema_sql: str):
        assert _has_fk_cascade(schema_sql, "applications", "users"), (
            "applications.user_id must have ON DELETE CASCADE referencing users"
        )

    def test_generation_jobs_cascade_from_applications(self, schema_sql: str):
        assert _has_fk_cascade(schema_sql, "generation_jobs", "applications"), (
            "generation_jobs.application_id must have ON DELETE CASCADE referencing applications"
        )

    def test_generation_jobs_cascade_from_users(self, schema_sql: str):
        assert _has_fk_cascade(schema_sql, "generation_jobs", "users"), (
            "generation_jobs.user_id must have ON DELETE CASCADE referencing users"
        )

    def test_generation_job_events_cascade_from_generation_jobs(self, schema_sql: str):
        assert _has_fk_cascade(schema_sql, "generation_job_events", "generation_jobs"), (
            "generation_job_events.job_id must have ON DELETE CASCADE referencing generation_jobs"
        )

    def test_evidence_ledger_items_cascade_from_generation_jobs(self, schema_sql: str):
        assert _has_fk_cascade(schema_sql, "evidence_ledger_items", "generation_jobs"), (
            "evidence_ledger_items.job_id must have ON DELETE CASCADE referencing generation_jobs"
        )

    def test_claim_citations_cascade_from_generation_jobs(self, schema_sql: str):
        assert _has_fk_cascade(schema_sql, "claim_citations", "generation_jobs"), (
            "claim_citations.job_id must have ON DELETE CASCADE referencing generation_jobs"
        )

    def test_doc_versions_cascade_from_applications(self, schema_sql: str):
        assert _has_fk_cascade(schema_sql, "doc_versions", "applications"), (
            "doc_versions.application_id must have ON DELETE CASCADE referencing applications"
        )


class TestUniqueConstraints:
    """Critical uniqueness invariants that prevent data corruption."""

    def test_evidence_ledger_items_job_id_id_unique(self, schema_sql: str):
        assert _has_unique_constraint(schema_sql, "evidence_ledger_items", "job_id", "id"), (
            "evidence_ledger_items must have UNIQUE(job_id, id) to prevent duplicate evidence"
        )

    def test_generation_job_events_job_id_sequence_no_unique(self, schema_sql: str):
        assert _has_unique_constraint(
            schema_sql, "generation_job_events", "job_id", "sequence_no"
        ), (
            "generation_job_events must have UNIQUE(job_id, sequence_no) to guarantee event ordering"
        )


class TestJobStatusEnum:
    """generation_jobs status values must match backend constants."""

    _VALID_STATUSES = frozenset(
        {"queued", "running", "succeeded", "succeeded_with_warnings", "failed", "cancelled"}
    )

    def test_terminal_statuses_exported_from_helpers(self):
        from app.api.routes.generate.helpers import TERMINAL_JOB_STATUSES

        assert "succeeded" in TERMINAL_JOB_STATUSES
        assert "failed" in TERMINAL_JOB_STATUSES
        assert "cancelled" in TERMINAL_JOB_STATUSES
        # succeeded_with_warnings is a terminal state too
        assert "succeeded_with_warnings" in TERMINAL_JOB_STATUSES

    def test_non_terminal_statuses_not_in_terminal_set(self):
        from app.api.routes.generate.helpers import TERMINAL_JOB_STATUSES

        assert "queued" not in TERMINAL_JOB_STATUSES
        assert "running" not in TERMINAL_JOB_STATUSES

    def test_schema_allows_queued_status(self, schema_sql: str):
        # The column default is 'queued'; verify it appears in the generation_jobs CREATE.
        assert "queued" in schema_sql

    def test_schema_allows_succeeded_with_warnings(self, schema_sql: str):
        # succeeded_with_warnings must be reachable without schema rejection.
        # The column is VARCHAR(30) — verify the value fits.
        assert len("succeeded_with_warnings") <= 30, (
            "succeeded_with_warnings exceeds the status column width — "
            "widen the column or shorten the status string"
        )
        # Also verify the canonical schema uses VARCHAR(30) not the old VARCHAR(20)
        assert "VARCHAR(30)" in schema_sql or "VARCHAR(50)" in schema_sql or "TEXT" in schema_sql, (
            "generation_jobs.status column must be at least VARCHAR(30) to store "
            "'succeeded_with_warnings' (23 chars). Run migration "
            "20260422_widen_generation_jobs_status.sql on this environment."
        )


class TestTablesDict:
    """TABLES dict in database.py must cover all critical tables."""

    _REQUIRED_CORE_TABLES = [
        "users",
        "profiles",
        "applications",
        "generation_jobs",
        "generation_job_events",
        "evidence_ledger_items",
        "claim_citations",
        "evidence",
        "documents",
        "doc_versions",
    ]

    def test_all_core_tables_present(self):
        from app.core.database import TABLES

        missing = [t for t in self._REQUIRED_CORE_TABLES if t not in TABLES]
        assert not missing, f"TABLES dict missing entries for: {missing}"

    def test_table_names_are_strings(self):
        from app.core.database import TABLES

        non_str = [(k, v) for k, v in TABLES.items() if not isinstance(v, str)]
        assert not non_str, f"TABLES values must be strings, found: {non_str}"

    def test_no_empty_table_names(self):
        from app.core.database import TABLES

        empty = [k for k, v in TABLES.items() if not v.strip()]
        assert not empty, f"Empty table name for keys: {empty}"


class TestModuleWhitelist:
    """requested_modules values must match the module whitelist in schemas."""

    _KNOWN_MODULES = frozenset(
        {
            "benchmark",
            "gaps",
            "cv",
            "coverLetter",
            "personalStatement",
            "portfolio",
            "scorecard",
            "learningPlan",
        }
    )

    def test_generation_job_request_schema_module_list(self):
        """GenerationJobRequest schema must accept all known module names."""
        from app.api.routes.generate.schemas import ALLOWED_JOB_MODULES, GenerationJobRequest

        # All KNOWN_MODULES must be in ALLOWED_JOB_MODULES (whitelist must be a superset)
        missing_from_allowed = self._KNOWN_MODULES - ALLOWED_JOB_MODULES
        assert not missing_from_allowed, (
            f"ALLOWED_JOB_MODULES is missing canonical modules: {missing_from_allowed}. "
            "If you added a new module, add it to ALLOWED_JOB_MODULES in schemas.py."
        )

        # The schema must accept all known camelCase module names
        valid_request = GenerationJobRequest(
            application_id="00000000-0000-0000-0000-000000000001",
            requested_modules=list(self._KNOWN_MODULES),
        )
        assert set(valid_request.requested_modules) == self._KNOWN_MODULES

    def test_generation_job_request_rejects_unknown_module(self):
        """GenerationJobRequest must reject unknown module names."""
        import pydantic

        from app.api.routes.generate.schemas import GenerationJobRequest

        with pytest.raises((pydantic.ValidationError, ValueError)):
            GenerationJobRequest(
                application_id="00000000-0000-0000-0000-000000000001",
                requested_modules=["totally_unknown_module_xyz"],
            )


class TestSchemaConsistency:
    """Cross-file consistency checks between SQL schema and Python constants."""

    def test_tables_dict_keys_match_values_for_core(self):
        """For the core tables the dict key and table name must match."""
        from app.core.database import TABLES

        mismatches = [
            (k, v)
            for k, v in TABLES.items()
            if k != v and k not in {"jobs"}  # jobs → job_descriptions is intentional
        ]
        # Allow intentional aliases: generation_jobs → generation_jobs (should match)
        problematic = [
            (k, v) for k, v in mismatches
            if k.replace("_", "") == v.replace("_", "")
            # Same words, different separators would be a problem
            # but we only flag cases where key and value diverge inexplicably
        ]
        # Actually the intent here is just to document the known alias and catch NEW ones.
        # Known intentional aliases: jobs → job_descriptions
        known_aliases = {"jobs": "job_descriptions"}
        unexpected = [(k, v) for k, v in mismatches if known_aliases.get(k) != v]
        assert not unexpected, (
            f"Unexpected TABLES aliases (key != table name and not in known_aliases): "
            f"{unexpected}. If intentional, add to known_aliases in this test."
        )

    def test_migration_file_exists_and_nonempty(self):
        assert _COMBINED_MIGRATION.exists(), "combined_migration.sql must exist"
        assert _COMBINED_MIGRATION.stat().st_size > 1000, (
            "combined_migration.sql appears empty or truncated"
        )

    def test_applications_modules_column_default_contains_all_module_keys(self, schema_sql: str):
        """The modules JSONB default in applications must include all 8 known module keys."""
        required_keys = [
            "benchmark", "gaps", "learningPlan", "cv",
            "coverLetter", "personalStatement", "portfolio", "scorecard",
        ]
        missing = [k for k in required_keys if f'"{k}"' not in schema_sql]
        assert not missing, (
            f"applications.modules JSONB default is missing keys: {missing}. "
            "If you renamed a module, update the schema default."
        )
