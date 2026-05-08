"""Contract test for generated cross-language event clients (m9-pr35, M10).

M10 exit gate text: "Generated event clients in use by at least one
consumer per language." This test ratifies the consumers:

* Python     — ``from app.core.events.generated import EventEnvelope``
               (also covered in test_event_schema_contract.py via field-set
               drift check).
* TypeScript — ``frontend/src/lib/sdk/index.ts`` re-exports
               ``EventEnvelope`` from ``../../types/events``.
* Kotlin     — every generated ``mobile/lib/events/*.kt`` file declares the
               expected ``data class <Title>`` that mirrors a registered
               event type.

If any of these consumers drifts (e.g. the SDK barrel stops re-exporting,
or a generated Kotlin file disappears), this test fails and the codegen
workflow won't re-create the binding silently.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "packages" / "events" / "schema" / "v1"
PYTHON_OUT = REPO_ROOT / "backend" / "app" / "core" / "events" / "generated"
TS_OUT = REPO_ROOT / "frontend" / "src" / "types" / "events"
KOTLIN_OUT = REPO_ROOT / "mobile" / "lib" / "events"
SDK_BARREL = REPO_ROOT / "frontend" / "src" / "lib" / "sdk" / "index.ts"


def _schema_titles() -> dict[str, str]:
    """Map basename → schema ``title`` (the class name)."""
    out: dict[str, str] = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        out[path.stem.removesuffix(".schema")] = json.loads(path.read_text())["title"]
    return out


# ── python consumer ───────────────────────────────────────────────────
def test_python_generated_module_imports():
    # If this import fails the generated artifact is missing or invalid.
    from app.core.events import generated  # noqa: F401

    titles = set(_schema_titles().values())
    exported = set(getattr(generated, "__all__", []))
    assert titles == exported, (
        f"generated python __all__ drift: schema-only={titles - exported} "
        f"export-only={exported - titles}"
    )


# ── typescript consumer ───────────────────────────────────────────────
def test_typescript_sdk_barrel_reexports_envelope():
    assert SDK_BARREL.exists(), f"missing {SDK_BARREL}"
    text = SDK_BARREL.read_text()
    assert 'from "../../types/events"' in text, (
        "frontend SDK barrel must re-export from ../../types/events to "
        "satisfy the M10 exit gate (TypeScript consumer)."
    )
    assert "EventEnvelope" in text, "barrel must re-export EventEnvelope type"


def test_typescript_index_barrel_present():
    index = TS_OUT / "index.ts"
    assert index.exists(), f"missing generated TS barrel: {index}"
    text = index.read_text()
    for stem in _schema_titles():
        ts_module = stem.replace("_", "-").replace(".", "-")
        assert f'from "./{ts_module}"' in text, (
            f"TS barrel missing export for {ts_module}"
        )


# ── kotlin consumer ───────────────────────────────────────────────────
def test_kotlin_files_declare_expected_data_classes():
    titles = _schema_titles()
    assert KOTLIN_OUT.exists(), f"missing {KOTLIN_OUT}"
    for stem, title in titles.items():
        kt_file = KOTLIN_OUT / f"{title}.kt"
        assert kt_file.exists(), f"missing generated Kotlin file: {kt_file}"
        text = kt_file.read_text()
        assert "package com.hirestack.events.generated" in text, (
            f"{kt_file.name} missing expected package declaration"
        )
        # quicktype emits either `data class <Title>` or `class <Title>`.
        pattern = rf"\b(data\s+class|class)\s+{re.escape(title)}\b"
        assert re.search(pattern, text), (
            f"{kt_file.name} does not declare expected class {title}; "
            f"the Kotlin consumer wiring is broken."
        )


@pytest.mark.parametrize("schema_file", sorted(SCHEMA_DIR.glob("*.schema.json")))
def test_every_schema_has_artifact_in_each_language(schema_file: Path):
    stem = schema_file.stem.removesuffix(".schema")
    title = json.loads(schema_file.read_text())["title"]

    py = PYTHON_OUT / f"{stem.replace('.', '_')}.py"
    assert py.exists(), f"missing python artifact: {py}"

    ts = TS_OUT / f"{stem.replace('_', '-').replace('.', '-')}.ts"
    assert ts.exists(), f"missing typescript artifact: {ts}"

    kt = KOTLIN_OUT / f"{title}.kt"
    assert kt.exists(), f"missing kotlin artifact: {kt}"
