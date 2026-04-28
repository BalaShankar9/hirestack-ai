"""S2-F4: pin hot-path indexes so a later migration can't drop them.

These (table, column) pairs appear on the documented hot read paths
in `docs/audits/S2-data-migrations.md`. If any one is dropped or
misnamed, this test fails and the operator has to either restore
the index or update both the audit and the test together.

Match is loose by design: any CREATE INDEX whose column-spec
contains the column substring satisfies the pin. This tolerates
composite indexes (e.g. `(user_id, created_at DESC)`) without
demanding an exact name.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SUPABASE_DIR = REPO_ROOT / "supabase" / "migrations"

# Hot read paths. Add to this list when the audit identifies new ones.
HOT_PATHS: list[tuple[str, str]] = [
    ("job_descriptions", "user_id"),
    ("applications", "user_id"),
    ("document_library", "application_id"),
    ("evidence", "user_id"),
    ("evidence", "application_id"),
    ("generation_jobs", "status"),
    ("generation_jobs", "user_id"),
    ("generation_job_events", "job_id"),
    ("processed_webhook_events", "processed_at"),
    ("audit_logs", "org_id"),
    ("audit_logs", "user_id"),
    ("api_usage", "created_at"),
    ("api_usage", "user_id"),
]


def _scan_indexes() -> dict[str, list[str]]:
    idx_re = re.compile(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?"
        r"(?:IF\s+NOT\s+EXISTS\s+)?\S+\s+ON\s+(?:public\.)?"
        r"([a-zA-Z_][a-zA-Z_0-9]*)\s*(?:USING\s+\S+\s*)?\(([^)]+)\)",
        re.IGNORECASE,
    )
    out: dict[str, list[str]] = {}
    for path in sorted(SUPABASE_DIR.glob("*.sql")):
        for m in idx_re.finditer(path.read_text()):
            table = m.group(1).lower()
            cols = re.sub(r"\s+", " ", m.group(2)).strip().lower()
            out.setdefault(table, []).append(cols)
    return out


def test_hot_path_indexes_present() -> None:
    indexes = _scan_indexes()
    missing: list[str] = []
    for table, column in HOT_PATHS:
        candidates = indexes.get(table, [])
        if not any(column in spec for spec in candidates):
            missing.append(f"{table}({column})")
    assert not missing, (
        "Hot-path index missing from supabase/migrations/. "
        "Either restore the index or update HOT_PATHS in this file "
        "AND docs/audits/S2-data-migrations.md together. "
        f"Missing: {missing}"
    )
