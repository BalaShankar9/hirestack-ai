#!/usr/bin/env python3
"""
TODO expiration enforcement.

Every TODO/FIXME/XXX in source code MUST carry a deadline:

    TODO(2026-08-01): drop ai_engine.api carve-outs after m4-pr12+
    FIXME(2026-06-15): proper retry policy for outbox claim

Format: TODO(YYYY-MM-DD): description

Fails CI when:
  - TODO has no date
  - TODO date has passed (relative to today)
  - Date is malformed

Skip files: tests, vendored deps, generated code (configured below).
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TODAY = dt.date.today()

# Patterns we audit
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX)\b(\(([^)]*)\))?", re.IGNORECASE)
DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

INCLUDE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".kt", ".sql", ".yml", ".yaml", ".toml"}
EXCLUDE_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "dist",
    "build",
    ".next",
    ".next-dev-3001",
    ".next-dev-3002",
    ".netlify",
    ".turbo",
    ".vercel",
    ".cache",
    "coverage",
    "output",
    "reference",
    ".mypy_cache",
    ".pytest_cache",
    "_archive",
    ".worktrees",
}
EXCLUDE_PATHS = {
    # Files that document or implement the TODO-format rule itself contain
    # literal "TODO" tokens that are not real TODOs.
    "scripts/governance/check_todo_expiry.py",
    "scripts/governance/check_architecture.py",
    "scripts/governance/check_feature_flags.py",
    "scripts/governance/check_migration_safety.py",
    ".github/workflows/architecture.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "docs/architecture/IMPLEMENTATION_MILESTONES.md",
    "docs/architecture/OPERATIONAL_PROCESSES.md",
    "docs/adrs/README.md",
}


def is_excluded(path: pathlib.Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if path.suffix not in INCLUDE_SUFFIXES:
        return True
    rel = str(path.relative_to(ROOT))
    if rel in EXCLUDE_PATHS:
        return True
    return False


def audit() -> int:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or is_excluded(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = TODO_RE.search(line)
            if not m:
                continue
            tag = m.group(1).upper()
            arg = (m.group(3) or "").strip()
            rel = path.relative_to(ROOT)
            if not arg:
                failures.append(
                    f"{rel}:{lineno}: {tag} without deadline. Use {tag}(YYYY-MM-DD): description"
                )
                continue
            dm = DATE_RE.search(arg)
            if not dm:
                failures.append(
                    f"{rel}:{lineno}: {tag}({arg}) malformed; required: {tag}(YYYY-MM-DD): ..."
                )
                continue
            try:
                deadline = dt.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            except ValueError:
                failures.append(f"{rel}:{lineno}: {tag} invalid date {dm.group(0)}")
                continue
            if deadline < TODAY:
                age = (TODAY - deadline).days
                failures.append(
                    f"{rel}:{lineno}: {tag} expired {age} days ago ({deadline.isoformat()}): {line.strip()[:120]}"
                )
    if failures:
        print("TODO/FIXME expiration audit failed:\n", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        print(
            f"\n{len(failures)} expired or malformed marker(s). "
            "Either resolve the work, or extend the deadline in the same PR.",
            file=sys.stderr,
        )
        return 1
    print("TODO/FIXME audit: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(audit())
