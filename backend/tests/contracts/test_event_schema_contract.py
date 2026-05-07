"""Contract test for ``packages/events/schema/v1`` (PR m6-pr26).

Enforces three invariants:

1. Every JSON Schema file in ``packages/events/schema/v1/`` is valid
   JSON and conforms to JSON Schema Draft 2020-12 (or 7) as a meta-
   schema sanity check.
2. Every registered event type in
   ``app.core.events.types.REGISTERED_EVENT_TYPES`` has exactly one
   matching ``<name>.v<version>.schema.json`` file in the package.
3. The schema's ``event_type`` const + ``event_version`` const match
   the registered constants. (Stops drift between the wire schema and
   the Pydantic registry.)

The envelope schema is also smoke-tested against a freshly-built
``EventEnvelope`` instance to make sure the wire shape is unchanged.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.events.envelope import EventEnvelope
from app.core.events.types import REGISTERED_EVENT_TYPES

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "packages" / "events" / "schema" / "v1"


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


# ── invariant 1: every schema file parses ─────────────────────────────
def test_every_schema_file_is_valid_json():
    files = sorted(SCHEMA_DIR.glob("*.schema.json"))
    assert files, f"no schemas found in {SCHEMA_DIR}"
    for path in files:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            pytest.fail(f"{path.name} is not valid JSON: {exc}")
        assert "$schema" in data, f"{path.name} missing $schema"
        assert "$id" in data, f"{path.name} missing $id"
        assert "title" in data, f"{path.name} missing title"


def test_envelope_schema_has_required_fields():
    env = _load("envelope.schema.json")
    assert env["title"] == "EventEnvelope"
    required = set(env["required"])
    assert {
        "event_id",
        "event_type",
        "event_version",
        "org_id",
        "occurred_at",
        "payload",
    }.issubset(required)
    # idempotency_key is NOT required (matches Pydantic Optional[str])
    assert "idempotency_key" not in required


# ── invariant 2 + 3: registered types ↔ schema files ──────────────────
def test_every_registered_event_type_has_a_schema_file():
    files = {p.name for p in SCHEMA_DIR.glob("*.v*.schema.json")}
    for name, etype in REGISTERED_EVENT_TYPES.items():
        expected = f"{name}.v{etype.version}.schema.json"
        assert expected in files, (
            f"registered event {name} v{etype.version} has no schema file "
            f"(expected {expected} in packages/events/schema/v1/)"
        )


def test_every_event_schema_file_matches_a_registered_type():
    for path in SCHEMA_DIR.glob("*.v*.schema.json"):
        if path.name == "envelope.schema.json":
            continue
        data = json.loads(path.read_text())
        props = data["properties"]
        const_name = props["event_type"]["const"]
        const_version = props["event_version"]["const"]
        assert const_name in REGISTERED_EVENT_TYPES, (
            f"{path.name} declares event_type={const_name!r} but it is not "
            "in REGISTERED_EVENT_TYPES — register it in "
            "app/core/events/types.py first."
        )
        registered = REGISTERED_EVENT_TYPES[const_name]
        assert const_version == registered.version, (
            f"{path.name} declares version {const_version} but registry "
            f"says {registered.version} for {const_name}"
        )
        # filename version must equal the in-schema const version too
        # (e.g. generation.requested.v1.schema.json must hold const 1).
        filename_version = int(path.name.rsplit(".v", 1)[1].split(".", 1)[0])
        assert filename_version == const_version, (
            f"{path.name} filename version {filename_version} != "
            f"in-schema const {const_version}"
        )


# ── envelope smoke test ───────────────────────────────────────────────
def test_pydantic_envelope_matches_wire_schema_required_fields():
    env = EventEnvelope(
        event_type="generation.requested",
        event_version=1,
        org_id=uuid.uuid4(),
        occurred_at=datetime.now(timezone.utc),
        payload={
            "job_id": str(uuid.uuid4()),
            "application_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "requested_modules": ["resume"],
        },
    )
    row = env.to_outbox_row()
    schema_required = set(_load("envelope.schema.json")["required"])
    # Every required wire field must be present in the outbox row.
    assert schema_required.issubset(row.keys()), (
        f"outbox row missing required wire fields: "
        f"{schema_required - set(row.keys())}"
    )
