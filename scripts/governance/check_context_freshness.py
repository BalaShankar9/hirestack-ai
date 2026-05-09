#!/usr/bin/env python3
"""Advisory freshness checker for /context/ files.

Reads YAML front-matter `last_synced` and `watch_paths` from each markdown
file in /context/. For each file, runs `git log --since=<last_synced> --
<watch_paths>` and prints a warning if any commits exist on the watched
paths since the last sync date.

This script is ADVISORY ONLY. It exits 0 in all cases. Treat warnings as
a reminder to bump `last_synced` (and update content if needed) in your
next PR.

Usage:
    python scripts/governance/check_context_freshness.py
    make check-context

CI integration: this runs informationally on every PR. It is NOT a
required gate. Promotion to required is tracked as KNOWN_ISSUES W14.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_DIR = REPO_ROOT / "context"

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
LAST_SYNCED_RE = re.compile(r"^last_synced:\s*(\S+)\s*$", re.MULTILINE)
WATCH_BLOCK_RE = re.compile(
    r"^watch_paths:\s*\n((?:[ \t]+-\s+\S.*\n)+)", re.MULTILINE
)
WATCH_ITEM_RE = re.compile(r"^[ \t]+-\s+(\S.*?)\s*$", re.MULTILINE)


def parse_front_matter(text: str) -> tuple[str | None, list[str]]:
    """Return (last_synced, watch_paths) from a markdown file."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return None, []
    block = match.group(1)
    last_synced = None
    ls_match = LAST_SYNCED_RE.search(block)
    if ls_match:
        last_synced = ls_match.group(1).strip().strip("'\"")
    watch_paths: list[str] = []
    wb_match = WATCH_BLOCK_RE.search(block)
    if wb_match:
        for item in WATCH_ITEM_RE.finditer(wb_match.group(1)):
            watch_paths.append(item.group(1).strip().strip("'\""))
    return last_synced, watch_paths


def git_changed_since(since_date: str, paths: list[str]) -> list[str]:
    """Return list of commit SHAs that touched any of `paths` since
    `since_date` (YYYY-MM-DD).
    """
    if not paths:
        return []
    cmd = [
        "git",
        "log",
        f"--since={since_date}",
        "--pretty=format:%h",
        "--",
        *paths,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def check_file(path: Path) -> int:
    """Print warnings for one context file. Returns count of warnings."""
    text = path.read_text(encoding="utf-8")
    last_synced, watch_paths = parse_front_matter(text)
    rel = path.relative_to(REPO_ROOT)
    if last_synced is None:
        print(f"  [info] {rel}: no last_synced (skipping)")
        return 0
    if not watch_paths:
        print(f"  [info] {rel}: no watch_paths (skipping)")
        return 0
    shas = git_changed_since(last_synced, watch_paths)
    if not shas:
        return 0
    print(
        f"  [warn] {rel}: {len(shas)} commit(s) to watched paths since"
        f" {last_synced}"
    )
    print(f"         watch_paths: {watch_paths}")
    print(f"         recent commits: {shas[:5]}{'...' if len(shas) > 5 else ''}")
    print("         consider bumping last_synced and updating content")
    return 1


def main() -> int:
    if not CONTEXT_DIR.exists():
        print(f"context dir not found: {CONTEXT_DIR}", file=sys.stderr)
        return 0  # advisory: never fail CI

    md_files = sorted(p for p in CONTEXT_DIR.glob("*.md") if p.name != "README.md")
    if not md_files:
        print("no context files found")
        return 0

    print(f"checking {len(md_files)} context files for staleness...")
    warnings = 0
    for path in md_files:
        warnings += check_file(path)

    print()
    if warnings:
        print(f"advisory: {warnings} context file(s) may be stale")
        print("(this script exits 0; promote to required = KNOWN_ISSUES W14)")
    else:
        print("all context files are fresh against their watch_paths")

    return 0  # always 0 — advisory only


if __name__ == "__main__":
    sys.exit(main())
