"""Codemod: rewrite legacy `from ai_engine.X import Y` imports to use the
stable `ai_engine.api` surface (PR m4-pr11).

Only rewrites imports of symbols that `ai_engine.api` actually exports.
Anything not in the published surface is left alone — those will either
join the API in a later PR or get refactored away.

Usage:
    python tools/codemods/ai_engine_imports.py [path ...]

Defaults to scanning `backend/` if no paths are given. Pass `--check`
to fail (exit 1) when changes would be made instead of writing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Parse `ai_engine/api.py` for `__all__` instead of importing the module —
# importing ai_engine.client at codemod-time would pull in the whole backend
# config stack (the very coupling this PR exists to remove).
def _published_surface() -> set[str]:
    repo_root = Path(__file__).resolve().parents[2]
    api_path = repo_root / "ai_engine" / "api.py"
    text = api_path.read_text()
    m = re.search(r"__all__\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not m:
        return set()
    return {
        s.strip().strip('"').strip("'")
        for s in m.group(1).split(",")
        if s.strip().strip('"').strip("'")
    }


# `from ai_engine.<deep.path> import (a, b, c)` — captures module + names blob.
_FROM_RE = re.compile(
    r"^(?P<indent>[ \t]*)from[ \t]+ai_engine\.(?P<mod>[\w\.]+)[ \t]+import[ \t]+(?P<names>[^\n#]+)",
    re.MULTILINE,
)


def _split_names(blob: str) -> list[tuple[str, str]]:
    """Return [(symbol, alias_or_empty)] from an import names blob."""
    blob = blob.strip().strip("()").replace("\n", " ")
    out: list[tuple[str, str]] = []
    for chunk in blob.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if " as " in chunk:
            sym, alias = (p.strip() for p in chunk.split(" as ", 1))
        else:
            sym, alias = chunk, ""
        out.append((sym, alias))
    return out


def rewrite(source: str, surface: set[str]) -> tuple[str, int]:
    changes = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal changes
        names = _split_names(m["names"])
        moveable = [(s, a) for s, a in names if s in surface]
        leave = [(s, a) for s, a in names if s not in surface]
        if not moveable:
            return m.group(0)
        changes += 1
        new_lines: list[str] = []
        if leave:
            rebuilt = ", ".join(a and f"{s} as {a}" or s for s, a in leave)
            new_lines.append(f"{m['indent']}from ai_engine.{m['mod']} import {rebuilt}")
        rebuilt = ", ".join(a and f"{s} as {a}" or s for s, a in moveable)
        new_lines.append(f"{m['indent']}from ai_engine.api import {rebuilt}")
        return "\n".join(new_lines)

    return _FROM_RE.sub(_sub, source), changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["backend"])
    parser.add_argument("--check", action="store_true", help="exit 1 if changes needed")
    args = parser.parse_args(argv)

    surface = _published_surface()
    total_changed_files = 0
    total_rewrites = 0
    for root in args.paths:
        root_path = Path(root)
        if root_path.is_file():
            files = [root_path]
        else:
            files = list(root_path.rglob("*.py"))
        for py in files:
            try:
                text = py.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            new, changed = rewrite(text, surface)
            if not changed:
                continue
            total_changed_files += 1
            total_rewrites += changed
            if args.check:
                print(f"would rewrite: {py} ({changed} import statements)")
            else:
                py.write_text(new)
                print(f"rewrote: {py} ({changed} import statements)")

    print(f"\n{total_changed_files} files, {total_rewrites} import statements")
    if args.check and total_changed_files:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
