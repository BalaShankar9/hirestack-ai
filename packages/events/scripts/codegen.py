#!/usr/bin/env python3
"""packages/events codegen — real generator (m9-pr35, M10).

Generates typed event clients in three languages from the JSON Schemas
in ``packages/events/schema/v1/``:

  * Python     → ``backend/app/core/events/generated/`` (pydantic v2 models,
                 via ``datamodel-code-generator``).
  * TypeScript → ``frontend/src/types/events/``         (interfaces,
                 via ``json-schema-to-typescript`` invoked through ``npx``).
  * Kotlin     → ``mobile/lib/events/``                 (data classes,
                 via ``quicktype`` invoked through ``npx``).

Determinism: every generator is invoked with flags that strip timestamps
and other non-reproducible noise. The CI drift gate runs ``--write`` for
every language and then ``git diff --exit-code`` on the output dirs.

Usage::

    # Validate schemas only (cheap pre-flight).
    python packages/events/scripts/codegen.py --check

    # Plan-only (read-only — prints what would happen).
    python packages/events/scripts/codegen.py --plan --lang python

    # Real generation (writes to the on-disk output dir).
    python packages/events/scripts/codegen.py --write --lang python
    python packages/events/scripts/codegen.py --write --lang typescript
    python packages/events/scripts/codegen.py --write --lang kotlin
    python packages/events/scripts/codegen.py --write --all
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema" / "v1"

LANG_TARGETS: dict[str, tuple[str, str]] = {
    "python":     ("backend/app/core/events/generated", "datamodel-code-generator"),
    "typescript": ("frontend/src/types/events",         "json-schema-to-typescript"),
    "kotlin":     ("mobile/lib/events",                 "quicktype"),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _list_schemas() -> list[Path]:
    return sorted(SCHEMA_DIR.glob("*.schema.json"))


def _slug_to_module(slug: str) -> str:
    """``aim.assignment.created.v1`` → ``aim_assignment_created_v1``."""
    return re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")


def _slug_to_kotlin_class(slug: str) -> str:
    """``aim.assignment.created.v1`` → ``AimAssignmentCreatedV1``."""
    return "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", slug) if part)


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


def _wipe_generated_dir(out_dir: Path) -> None:
    """Remove all generated files but keep the directory (so .gitkeep stays)."""
    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        return
    for child in out_dir.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


# ---------------------------------------------------------------------------
# Per-language writers
# ---------------------------------------------------------------------------


def _write_python(schemas: list[Path]) -> int:
    out_dir = ROOT / LANG_TARGETS["python"][0]
    _wipe_generated_dir(out_dir)
    if shutil.which("datamodel-codegen") is None:
        print("datamodel-codegen not on PATH; install datamodel-code-generator", file=sys.stderr)
        return 3
    for schema in schemas:
        slug = schema.name.removesuffix(".schema.json")
        module = _slug_to_module(slug)
        out_file = out_dir / f"{module}.py"
        cmd = [
            "datamodel-codegen",
            "--input", str(schema),
            "--input-file-type", "jsonschema",
            "--output-model-type", "pydantic_v2.BaseModel",
            "--output", str(out_file),
            "--disable-timestamp",
            "--use-schema-description",
            "--target-python-version", "3.11",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FAIL {schema.name}: {result.stderr}", file=sys.stderr)
            return result.returncode
    # Generate a barrel __init__.py for convenient imports.
    init_path = out_dir / "__init__.py"
    init_lines = [
        '"""Generated event models. DO NOT EDIT — regenerate via `make codegen-events`."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    re_exports: list[str] = []
    for schema in schemas:
        slug = schema.name.removesuffix(".schema.json")
        module = _slug_to_module(slug)
        title = json.loads(schema.read_text())["title"]
        init_lines.append(f"from .{module} import {title}")
        re_exports.append(title)
    init_lines.extend(["", f"__all__ = {sorted(re_exports)!r}", ""])
    init_path.write_text("\n".join(init_lines))
    print(f"OK python: wrote {len(schemas)} models + __init__.py to {out_dir.relative_to(ROOT)}")
    return 0


def _write_typescript(schemas: list[Path]) -> int:
    out_dir = ROOT / LANG_TARGETS["typescript"][0]
    _wipe_generated_dir(out_dir)
    if shutil.which("npx") is None:
        print("npx not on PATH; install Node.js", file=sys.stderr)
        return 3
    barrel_lines = [
        "// Generated event types. DO NOT EDIT — regenerate via `make codegen-events`.",
        "",
    ]
    for schema in schemas:
        slug = schema.name.removesuffix(".schema.json")
        module = _slug_to_module(slug).replace("_", "-")
        out_file = out_dir / f"{module}.ts"
        cmd = [
            "npx", "--yes", "json-schema-to-typescript@15",
            str(schema),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FAIL {schema.name}: {result.stderr}", file=sys.stderr)
            return result.returncode
        out_file.write_text(result.stdout)
        barrel_lines.append(f'export * from "./{module}";')
    (out_dir / "index.ts").write_text("\n".join(barrel_lines) + "\n")
    print(f"OK typescript: wrote {len(schemas)} interfaces + index.ts to {out_dir.relative_to(ROOT)}")
    return 0


def _strip_integer_consts(node: object) -> object:
    """Recursively rewrite ``{"const": <int>}`` → ``{"type": "integer", "minimum": n, "maximum": n}``.

    Workaround for an upstream quicktype bug (`s.codePointAt is not a function`)
    triggered by integer ``const`` keywords. The semantics are preserved (the
    field is still pinned to a single integer value) and Python/TypeScript
    codegen are unaffected because they read the original schemas.
    """
    if isinstance(node, dict):
        if "const" in node and isinstance(node["const"], int) and not isinstance(node["const"], bool):
            value = node["const"]
            new = {k: v for k, v in node.items() if k != "const"}
            new.setdefault("type", "integer")
            new["minimum"] = value
            new["maximum"] = value
            return {k: _strip_integer_consts(v) for k, v in new.items()}
        return {k: _strip_integer_consts(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_integer_consts(item) for item in node]
    return node


def _write_kotlin(schemas: list[Path]) -> int:
    import tempfile

    out_dir = ROOT / LANG_TARGETS["kotlin"][0]
    _wipe_generated_dir(out_dir)
    if shutil.which("npx") is None:
        print("npx not on PATH; install Node.js", file=sys.stderr)
        return 3
    for schema in schemas:
        slug = schema.name.removesuffix(".schema.json")
        # Class name comes from the schema's `title` field — guarantees parity
        # with Python (datamodel-codegen also uses title) and with the contract
        # tests in backend/tests/contracts/test_generated_event_clients.py.
        class_name = json.loads(schema.read_text())["title"]
        out_file = out_dir / f"{class_name}.kt"
        # Workaround: rewrite integer-const before handing to quicktype.
        rewritten = _strip_integer_consts(json.loads(schema.read_text()))
        with tempfile.NamedTemporaryFile("w", suffix=".schema.json", delete=False) as tmp:
            json.dump(rewritten, tmp, indent=2, sort_keys=True)
            tmp_path = tmp.name
        try:
            cmd = [
                "npx", "--yes", "quicktype@23",
                "--src", tmp_path,
                "--src-lang", "schema",
                "--lang", "kotlin",
                "--package", "com.hirestack.events.generated",
                "--framework", "klaxon",
                "--top-level", class_name,
                "--out", str(out_file),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        if result.returncode != 0:
            print(f"FAIL {schema.name}: {result.stderr}", file=sys.stderr)
            return result.returncode
    print(f"OK kotlin: wrote {len(schemas)} data classes to {out_dir.relative_to(ROOT)}")
    return 0


WRITERS = {
    "python": _write_python,
    "typescript": _write_typescript,
    "kotlin": _write_kotlin,
}


def _write(lang: str) -> int:
    schemas = _list_schemas()
    if not schemas:
        print(f"no schemas found in {SCHEMA_DIR}", file=sys.stderr)
        return 1
    return WRITERS[lang](schemas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="validate schemas, exit 0 on success")
    group.add_argument("--plan",  action="store_true", help="print codegen plan (requires --lang)")
    group.add_argument("--write", action="store_true", help="generate code (requires --lang or --all)")
    parser.add_argument("--lang", choices=sorted(LANG_TARGETS), help="target language")
    parser.add_argument("--all",  action="store_true", help="apply --write to every language")
    args = parser.parse_args(argv)

    if args.check:
        return _check()

    if args.plan:
        if not args.lang:
            print("--plan requires --lang", file=sys.stderr)
            return 2
        return _plan(args.lang)

    # --write
    if args.all:
        for lang in sorted(LANG_TARGETS):
            rc = _write(lang)
            if rc != 0:
                return rc
        return 0
    if not args.lang:
        print("--write requires --lang or --all", file=sys.stderr)
        return 2
    return _write(args.lang)


if __name__ == "__main__":
    raise SystemExit(main())
