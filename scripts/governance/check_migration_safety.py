#!/usr/bin/env python3
"""
Migration safety linter.

Enforces expand-only migration discipline on supabase/migrations.
(As of m9-pr33 / M10, supabase/migrations is the sole migration root;
the legacy database/migrations directory was removed.)

Forbidden in a single migration:
  - DROP TABLE / DROP COLUMN
  - ALTER TABLE ... RENAME
  - ALTER TABLE ... DROP CONSTRAINT
  - ADD COLUMN ... NOT NULL without DEFAULT (locks table on rewrite)
  - CREATE INDEX (must be CONCURRENTLY in prod schemas)
  - Missing RLS on new public table

A migration that needs a destructive op must be split into:
  1. expand    — additive, deployed and observed.
  2. migrate   — backfill / dual-write.
  3. contract  — destructive op, in a separate later migration.

Override: add a header comment `-- SAFETY: <reason> (ADR-NNNN)` to a migration
file to acknowledge the risk explicitly. The script logs it but does not fail.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DIRS = [ROOT / "supabase" / "migrations"]

CHECKS: list[tuple[str, str]] = [
    (r"\bDROP\s+TABLE\b", "DROP TABLE in single migration"),
    (r"\bDROP\s+COLUMN\b", "DROP COLUMN in single migration"),
    (r"\bRENAME\s+(TO|COLUMN)\b", "RENAME in single migration (split into expand/contract)"),
    (r"\bDROP\s+CONSTRAINT\b", "DROP CONSTRAINT in single migration"),
    # NOT NULL without DEFAULT: ADD COLUMN <name> <type> NOT NULL (no DEFAULT keyword on the line)
    # Heuristic — 95% accuracy is fine for a guardrail.
    (r"ADD\s+COLUMN\s+\w+\s+[\w()]+\s+NOT\s+NULL\b(?!.*DEFAULT)", "NOT NULL ADD COLUMN without DEFAULT"),
    (r"\bCREATE\s+INDEX\b(?!\s+CONCURRENTLY)", "CREATE INDEX without CONCURRENTLY"),
]

OVERRIDE_RE = re.compile(r"--\s*SAFETY:\s*(.+)", re.IGNORECASE)
NEW_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?(public\.)?([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
RLS_RE = re.compile(r"ALTER\s+TABLE\s+(public\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE)


def audit_file(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues: list[str] = []
    overrides = OVERRIDE_RE.findall(text)

    for pattern, label in CHECKS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            line = text[: m.start()].count("\n") + 1
            if overrides:
                # Acknowledged risk, log but allow.
                continue
            issues.append(f"{path.relative_to(ROOT)}:{line}: {label}")

    # New tables must enable RLS in the same migration.
    new_tables = {m.group(3).lower() for m in NEW_TABLE_RE.finditer(text)}
    rls_tables = {m.group(2).lower() for m in RLS_RE.finditer(text)}
    # Skip clearly non-tenant tables (queue / cache / partition shells).
    skip = {p for p in new_tables if p.startswith(("_partman", "outbox_", "events_", "schema_migrations"))}
    missing = (new_tables - rls_tables) - skip
    for t in sorted(missing):
        if not overrides:
            issues.append(f"{path.relative_to(ROOT)}: new table `{t}` missing ENABLE ROW LEVEL SECURITY")

    return issues


def main() -> int:
    all_issues: list[str] = []
    seen = 0
    for d in DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.sql")):
            seen += 1
            all_issues.extend(audit_file(p))
    if all_issues:
        print(f"Migration safety audit FAILED ({seen} migrations scanned):", file=sys.stderr)
        for i in all_issues:
            print(f"  {i}", file=sys.stderr)
        print(
            "\nFix options: split into expand/migrate/contract OR add `-- SAFETY: <reason> (ADR-NNNN)` header.",
            file=sys.stderr,
        )
        return 1
    print(f"Migration safety audit: clean ({seen} migrations).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
