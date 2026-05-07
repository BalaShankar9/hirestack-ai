#!/usr/bin/env python3
"""packages/events codegen scaffold (PR m6-pr26).

Inspects ``packages/events/schema/v1/`` and prints a per-language
generation plan. Real codegen lands in PR m6-pr26b once we wire the
first cross-language consumer.

Usage:
    python packages/events/scripts/codegen.py --lang python
    python packages/events/scripts/codegen.py --lang typescript
    python packages/events/scripts/codegen.py --lang kotlin
    python packages/events/scripts/codegen.py --check    # exit 0 iff all schemas parse

The ``--check`` mode is the only mode that runs in CI today; it makes
this file executable as a smoke test even though no language target is
wired yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema" / "v1"

LANG_TARGETS = {
    "python":     ("backend/app/core/events/generated/", "datamodel-code-generator"),
    "typescript": ("frontend/src/types/events/",         "json-schema-to-typescript"),
    "kotlin":     ("mobile/lib/events/",                 "quicktype"),
}


def _list_schemas() -> list[Path]:
    return sorted(SCHEMA_DIR.glob("*.schema.json"))


def _check() -> int:
    schemas = _list_schemas()
    if not schemas:
        print(f"no schemas found in {SCHEMA_DIR}", file=sys.stderr)
        return 1
    failures = 0
    for path in schemas:
        try:
            data = json.loads(path.read_text())
            assert "$id" in data and "title" in data
        except (json.JSONDecodeError, AssertionError) as exc:
            print(f"FAIL {path.name}: {exc}", file=sys.stderr)
            failures += 1
    if failures:
        print(f"{failures} schema(s) failed validation", file=sys.stderr)
        return 1
    print(f"OK {len(schemas)} schema(s) validated")
    return 0


def _plan(lang: str) -> int:
    if lang not in LANG_TARGETS:
        print(f"unknown lang {lang!r}; choose from {sorted(LANG_TARGETS)}", file=sys.stderr)
        return 2
    out_dir, tool = LANG_TARGETS[lang]
    schemas = _list_schemas()
    print(f"# {lang} codegen plan")
    print(f"# tool: {tool}")
    print(f"# output: {out_dir}")
    for path in schemas:
        print(f"  {tool} {path.relative_to(SCHEMA_DIR.parents[1])}  ->  {out_dir}")
    print(f"# {len(schemas)} schema(s) total")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="validate schemas, exit 0 on success")
    group.add_argument("--lang", choices=sorted(LANG_TARGETS), help="print codegen plan for a language")
    args = parser.parse_args(argv)
    if args.check:
        return _check()
    return _plan(args.lang)


if __name__ == "__main__":
    raise SystemExit(main())
