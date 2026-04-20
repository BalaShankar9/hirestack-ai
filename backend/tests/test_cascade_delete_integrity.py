"""Static cascade-integrity test.

Parses every migration in the repo and asserts that any table holding a
foreign key to `applications` or `users` has an explicit ON DELETE
strategy — either CASCADE (drop dependent rows) or SET NULL (preserve
the row for analytics, sever the link). A bare REFERENCES with no
ON DELETE clause leaves orphan rows behind on parent deletion.

This is the defensive net the audit demanded — without it a new table
author can land code that leaves dangling references after account or
application deletion, silently breaking GDPR Right-to-Erasure and
creating data hygiene drift.

This is a static structural test (no live DB required) so it runs in CI
on every push and catches drift the moment it is introduced.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

import pytest


MIGRATION_GLOBS = (
    "supabase/migrations/*.sql",
    "database/migrations/*.sql",
)

# Tables that DELIBERATELY use ON DELETE SET NULL on their application_id
# FK so the analytic / history row survives the parent deletion.
ALLOWED_SET_NULL_FOR_APPLICATIONS: set[str] = {
    "ats_scans",            # Preserves user's ATS-scan history
    "interview_sessions",   # Preserves practice-interview history
    "learning_plans",       # Preserves study plans created from a JD
    "doc_variants",         # Preserves A/B test variant history
    "salary_analyses",      # Preserves salary research history
    "career_suggestions",   # Preserves coaching history
    "document_library",     # Documents survive even if application removed
    "document_observations",  # Observations are user-scoped audit
    "events",               # Telemetry preserved for analytics
    "evidence",             # Evidence linked to application but user-owned
    "evidence_mappings",    # Mapping records preserved as audit trail
    "review_sessions",      # Review history is user-scoped
    "tasks",                # Tasks survive application removal
}

# KNOWN HISTORICAL DRIFT — frozen at the time of v4 hardening, then
# closed by migration 20260420200000_user_fk_on_delete_hygiene.sql.
# The set is empty because the corrective migration explicitly classified
# every previously-bare user FK as either CASCADE or SET NULL. Future
# new bare FKs will be caught by the test below.
KNOWN_BARE_USER_FKS: set[tuple[str, str]] = set()


def _read_all_sql() -> str:
    """Concatenate all migration SQL into a single string for FK parsing."""
    # Walk upwards until we find the workspace root (the dir that contains
    # both supabase/migrations and database/migrations). Resilient to test
    # being moved.
    here = Path(__file__).resolve()
    repo_root = None
    for ancestor in here.parents:
        if (ancestor / "supabase" / "migrations").is_dir():
            repo_root = ancestor
            break
    assert repo_root is not None, (
        "Could not locate workspace root containing supabase/migrations"
    )
    chunks: list[str] = []
    for pattern in MIGRATION_GLOBS:
        for path in sorted(glob.glob(str(repo_root / pattern))):
            with open(path) as fh:
                chunks.append(f"\n-- FILE: {path}\n")
                chunks.append(fh.read())
    return "\n".join(chunks)


# A FK declaration like:
#     application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
# or:
#     application_id UUID REFERENCES applications(id),
_FK_INLINE_RE = re.compile(
    r"(?P<col>\w+)\s+(?:UUID|BIGINT|INT|INTEGER|TEXT|VARCHAR\(\d+\))"
    r"(?:\s+(?:NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|DEFAULT\s+[^,]+))*"
    r"\s+REFERENCES\s+(?:public\.)?(?P<parent>\w+)\s*(?:\([^)]+\))?"
    r"(?P<rest>[^,]*)",
    re.IGNORECASE,
)
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:public\.)?(?P<tname>\w+)\s*\((?P<body>.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)


def _collect_fks(sql: str, parent_table: str) -> list[tuple[str, str, str]]:
    """Return (child_table, column, on_delete_strategy) for every FK
    pointing at `parent_table`. Strategy is one of:
        "cascade" | "set_null" | "set_default" | "restrict" | "no_action" | "none"
    "none" means the FK was declared with no ON DELETE clause at all,
    which is the only universally-bad outcome for cleanup."""
    out: list[tuple[str, str, str]] = []

    def _classify(rest: str) -> str:
        upper = rest.upper()
        if "ON DELETE CASCADE" in upper:
            return "cascade"
        if "ON DELETE SET NULL" in upper:
            return "set_null"
        if "ON DELETE SET DEFAULT" in upper:
            return "set_default"
        if "ON DELETE RESTRICT" in upper:
            return "restrict"
        if "ON DELETE NO ACTION" in upper:
            return "no_action"
        return "none"

    for m in _CREATE_TABLE_RE.finditer(sql):
        child = m.group("tname")
        body = m.group("body")
        for fk in _FK_INLINE_RE.finditer(body):
            if fk.group("parent").lower() != parent_table.lower():
                continue
            out.append((child, fk.group("col"), _classify(fk.group("rest"))))
    alter_re = re.compile(
        r"ALTER\s+TABLE\s+(?:public\.)?(?P<child>\w+)\s+"
        r"ADD\s+CONSTRAINT\s+\w+\s+"
        r"FOREIGN\s+KEY\s*\((?P<col>\w+)\)\s+"
        r"REFERENCES\s+(?:public\.)?(?P<parent>\w+)"
        r"(?P<rest>[^;]*)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in alter_re.finditer(sql):
        if m.group("parent").lower() != parent_table.lower():
            continue
        out.append((m.group("child"), m.group("col"), _classify(m.group("rest"))))

    # Dedupe by (child, col) — later ALTER TABLE definitions override
    # earlier CREATE TABLE inline FKs (mirrors live-DB last-write-wins).
    # Prefer any explicit strategy over "none".
    last_by_key: dict[tuple[str, str], str] = {}
    for child, col, strat in out:
        key = (child.lower(), col.lower())
        prev = last_by_key.get(key)
        if prev is None or prev == "none":
            last_by_key[key] = strat
        elif strat != "none":
            # Both explicit — last-seen wins (matches Postgres semantics)
            last_by_key[key] = strat
    return [(c, col, strat) for (c, col), strat in last_by_key.items()]


@pytest.fixture(scope="module")
def all_sql() -> str:
    return _read_all_sql()


def test_every_application_fk_has_explicit_on_delete(all_sql):
    """Every FK to applications must have an explicit ON DELETE strategy.
    A bare REFERENCES leaves orphans on parent deletion."""
    fks = _collect_fks(all_sql, "applications")
    assert fks, "Expected at least one FK to applications; parser may be broken."

    bare = [(c, col) for c, col, strat in fks if strat == "none"]
    assert not bare, (
        "These tables hold an application FK without ANY ON DELETE clause. "
        "Deleting an application would leave dangling references behind:\n  "
        + "\n  ".join(f"{c}.{col}" for c, col in bare)
        + "\nFix: add 'ON DELETE CASCADE' (drop dependents) or "
        "'ON DELETE SET NULL' (preserve analytics row) to the FK."
    )


def test_application_set_null_choices_are_documented(all_sql):
    """Every table that uses SET NULL on its application FK must be in
    the explicit allow-list. Prevents silent drift toward keeping
    orphaned-reference rows the team didn't intend to keep."""
    fks = _collect_fks(all_sql, "applications")
    set_null_children = {c for c, _col, strat in fks if strat == "set_null"}
    undocumented = set_null_children - ALLOWED_SET_NULL_FOR_APPLICATIONS
    assert not undocumented, (
        f"These tables use ON DELETE SET NULL on application_id without "
        f"being on the documented allow-list: {sorted(undocumented)}.\n"
        f"Either: (a) change them to CASCADE, or (b) add them to "
        f"ALLOWED_SET_NULL_FOR_APPLICATIONS in this test file with a "
        f"product justification comment."
    )


def test_every_user_fk_has_explicit_on_delete(all_sql):
    """Every NEW FK to users must have an explicit ON DELETE strategy.
    Existing drift is grandfathered in KNOWN_BARE_USER_FKS but no new
    bare FK may be added. Postgres default is NO ACTION which raises
    on parent delete — making user removal silently impossible."""
    fks = _collect_fks(all_sql, "users")
    assert fks, "Expected at least one FK to users; parser may be broken."

    bare = {(c, col) for c, col, strat in fks if strat == "none"}
    new_bare = bare - KNOWN_BARE_USER_FKS
    assert not new_bare, (
        "These NEW user FKs were added without an ON DELETE clause. "
        "Account deletion would fail with a FK-violation error:\n  "
        + "\n  ".join(f"{c}.{col}" for c, col in sorted(new_bare))
        + "\nFix: add 'ON DELETE CASCADE' (drop dependents) or "
        "'ON DELETE SET NULL' (preserve audit row) to the FK definition."
    )

    # Detect drift removal: if someone fixed a bare FK we want to know
    # so we can shrink the allow-list and tighten the gate.
    fixed = KNOWN_BARE_USER_FKS - bare
    if fixed:
        print(
            "\nINFO: bare user FKs that have been fixed since the "
            "allow-list was created (please remove from "
            f"KNOWN_BARE_USER_FKS): {sorted(fixed)}"
        )


def test_known_critical_tables_cascade_on_application_delete(all_sql):
    """Anchor the cascade test against a list of concrete tables we know
    must drop their rows when an application is deleted (not preserved
    as analytics). If anyone refactors a migration and accidentally
    removes the cascade, this test names the offender."""
    REQUIRED_CASCADING_CHILDREN = {
        "generation_jobs",
        "generation_job_events",
        "agent_artifacts",
        "document_library",
    }

    fks = _collect_fks(all_sql, "applications")
    cascading_children = {c for c, _col, strat in fks if strat == "cascade"}

    missing = REQUIRED_CASCADING_CHILDREN - cascading_children
    assert not missing, (
        f"These critical child tables MUST cascade on application "
        f"delete but currently do not: {sorted(missing)}.\n"
        f"All cascading children parsed: {sorted(cascading_children)}"
    )


def test_cascade_audit_dump(all_sql):
    """Documents the current cascade landscape. Always passes; intent is
    to make the inventory visible in test output for review."""
    fks_app = _collect_fks(all_sql, "applications")
    fks_user = _collect_fks(all_sql, "users")
    print("\n=== application_id FKs ===")
    for child, col, strat in sorted(fks_app):
        print(f"  {child}.{col}: {strat}")
    print(f"\n=== user_id FKs — {len(fks_user)} total ===")
    for child, col, strat in sorted(fks_user)[:30]:
        print(f"  {child}.{col}: {strat}")
