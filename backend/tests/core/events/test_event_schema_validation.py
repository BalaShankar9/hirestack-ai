"""Tests for the JSON-Schema event validator and OutboxWriter strict mode (m7-pr31, ADR-0035)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.events import (
    AIM_SOURCE_CREATED,
    EventEnvelope,
    EventValidationError,
    GENERATION_REQUESTED,
    MissingEventSchema,
    OUTBOX_TABLE,
    OutboxWriter,
    reset_registry_for_tests,
    validate_event,
)


# ---------------------------------------------------------------------------
# Fake Supabase client (mirrors test_outbox_writer.py)
# ---------------------------------------------------------------------------


class _UniqueViolation(Exception):
    code = "23505"

    def __str__(self) -> str:  # pragma: no cover
        return "duplicate key value violates unique constraint"


@dataclass
class _Response:
    data: Any


@dataclass
class _FakeQuery:
    table: "_FakeTable"
    op: str
    payload: dict[str, Any] | None = None

    def insert(self, row: dict[str, Any]) -> "_FakeQuery":
        self.op = "insert"
        self.payload = row
        return self

    def execute(self) -> _Response:
        assert self.op == "insert" and self.payload is not None
        row = dict(self.payload)
        self.table.rows.append(row)
        return _Response(data=[row])


@dataclass
class _FakeTable:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def insert(self, row: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(table=self, op="insert", payload=row)


class _FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        return self.tables.setdefault(name, _FakeTable())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_source_envelope(**overrides: Any) -> EventEnvelope:
    """Envelope whose payload conforms to aim.source.created.v1.schema.json."""
    base = dict(
        event_type=AIM_SOURCE_CREATED.name,
        event_version=AIM_SOURCE_CREATED.version,
        org_id=uuid.uuid4(),
        payload={
            "source_id": str(uuid.uuid4()),
            "kind": "article",
            "title": "ACME",
            "url": None,
        },
    )
    base.update(overrides)
    return EventEnvelope(**base)


def _invalid_source_envelope() -> EventEnvelope:
    """Envelope with an extra field (additionalProperties:false → fail)."""
    return EventEnvelope(
        event_type=AIM_SOURCE_CREATED.name,
        event_version=AIM_SOURCE_CREATED.version,
        org_id=uuid.uuid4(),
        payload={
            "source_id": str(uuid.uuid4()),
            "kind": "article",
            "internal_debug": "should be rejected",
        },
    )


def _missing_required_envelope() -> EventEnvelope:
    """Envelope missing the required ``kind`` field."""
    return EventEnvelope(
        event_type=AIM_SOURCE_CREATED.name,
        event_version=AIM_SOURCE_CREATED.version,
        org_id=uuid.uuid4(),
        payload={"source_id": str(uuid.uuid4())},
    )


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


# ---------------------------------------------------------------------------
# validate_event
# ---------------------------------------------------------------------------


def test_validate_event_accepts_valid_payload() -> None:
    env = _valid_source_envelope()
    assert validate_event(env) == []


def test_validate_event_rejects_extra_field() -> None:
    env = _invalid_source_envelope()
    errors = validate_event(env)
    assert errors, "expected validation errors for additional property"
    assert any("internal_debug" in e or "additional" in e.lower() for e in errors)


def test_validate_event_rejects_missing_required_field() -> None:
    env = _missing_required_envelope()
    errors = validate_event(env)
    assert errors
    assert any("kind" in e for e in errors)


def test_validate_event_raises_for_unknown_event_type(tmp_path, monkeypatch) -> None:
    # Point the registry at an empty schema dir.
    from app.core.events import schema_registry

    reset_registry_for_tests()
    schema_registry.get_registry().schema_dir = tmp_path  # type: ignore[attr-defined]

    env = _valid_source_envelope()
    with pytest.raises(MissingEventSchema):
        validate_event(env)


def test_validator_is_cached_per_type() -> None:
    from app.core.events import schema_registry

    reg = schema_registry.get_registry()
    v1 = reg.get_validator("aim.source.created", 1)
    v2 = reg.get_validator("aim.source.created", 1)
    assert v1 is v2


# ---------------------------------------------------------------------------
# OutboxWriter — shadow mode (default)
# ---------------------------------------------------------------------------


def test_writer_shadow_mode_inserts_invalid_envelope_and_logs(caplog) -> None:
    fake = _FakeSupabase()
    writer = OutboxWriter(fake, strict=False)
    env = _invalid_source_envelope()

    with caplog.at_level("WARNING"):
        row = writer.append(env)

    assert row["event_type"] == env.event_type
    assert len(fake.tables[OUTBOX_TABLE].rows) == 1
    assert any("event_validation_failed_shadow" in r.message for r in caplog.records)


def test_writer_shadow_mode_inserts_valid_envelope_silently(caplog) -> None:
    fake = _FakeSupabase()
    writer = OutboxWriter(fake, strict=False)
    env = _valid_source_envelope()

    with caplog.at_level("WARNING"):
        writer.append(env)

    assert len(fake.tables[OUTBOX_TABLE].rows) == 1
    # No shadow log line for a valid payload.
    assert not any("event_validation_failed_shadow" in r.message for r in caplog.records)


def test_writer_shadow_mode_inserts_when_schema_missing(tmp_path, caplog) -> None:
    from app.core.events import schema_registry

    reset_registry_for_tests()
    schema_registry.get_registry().schema_dir = tmp_path  # type: ignore[attr-defined]

    fake = _FakeSupabase()
    writer = OutboxWriter(fake, strict=False)
    env = _valid_source_envelope()

    with caplog.at_level("WARNING"):
        writer.append(env)

    assert len(fake.tables[OUTBOX_TABLE].rows) == 1
    assert any("event_schema_missing_shadow" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# OutboxWriter — strict mode
# ---------------------------------------------------------------------------


def test_writer_strict_mode_blocks_invalid_envelope() -> None:
    fake = _FakeSupabase()
    writer = OutboxWriter(fake, strict=True)
    env = _invalid_source_envelope()

    with pytest.raises(EventValidationError) as excinfo:
        writer.append(env)

    assert excinfo.value.event_type == env.event_type
    assert excinfo.value.errors
    # Critical: NOTHING was written.
    assert OUTBOX_TABLE not in fake.tables or fake.tables[OUTBOX_TABLE].rows == []


def test_writer_strict_mode_inserts_valid_envelope() -> None:
    fake = _FakeSupabase()
    writer = OutboxWriter(fake, strict=True)
    env = _valid_source_envelope()

    row = writer.append(env)

    assert row["event_type"] == env.event_type
    assert len(fake.tables[OUTBOX_TABLE].rows) == 1


def test_writer_strict_mode_blocks_missing_required_field() -> None:
    fake = _FakeSupabase()
    writer = OutboxWriter(fake, strict=True)
    env = _missing_required_envelope()

    with pytest.raises(EventValidationError):
        writer.append(env)

    assert OUTBOX_TABLE not in fake.tables or fake.tables[OUTBOX_TABLE].rows == []


def test_writer_strict_mode_raises_missing_event_schema(tmp_path) -> None:
    from app.core.events import schema_registry

    reset_registry_for_tests()
    schema_registry.get_registry().schema_dir = tmp_path  # type: ignore[attr-defined]

    fake = _FakeSupabase()
    writer = OutboxWriter(fake, strict=True)

    with pytest.raises(MissingEventSchema):
        writer.append(_valid_source_envelope())

    assert OUTBOX_TABLE not in fake.tables or fake.tables[OUTBOX_TABLE].rows == []


# ---------------------------------------------------------------------------
# Strict-flag default plumbing (no explicit override)
# ---------------------------------------------------------------------------


def test_writer_strict_flag_off_by_default(monkeypatch, caplog) -> None:
    """With no override and the live flag OFF, behaviour is shadow mode."""
    fake = _FakeSupabase()
    writer = OutboxWriter(fake)  # strict=None → reads flag
    env = _invalid_source_envelope()

    with caplog.at_level("WARNING"):
        writer.append(env)  # must not raise

    assert len(fake.tables[OUTBOX_TABLE].rows) == 1


def test_writer_strict_flag_on_via_settings(monkeypatch) -> None:
    """When the live flag is ON, default-mode writer rejects bad envelopes."""
    from app.core import config as config_module

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "ff_strict_event_validation", True, raising=False)

    fake = _FakeSupabase()
    writer = OutboxWriter(fake)  # strict=None → reads flag → True
    env = _invalid_source_envelope()

    with pytest.raises(EventValidationError):
        writer.append(env)

    assert OUTBOX_TABLE not in fake.tables or fake.tables[OUTBOX_TABLE].rows == []


# ---------------------------------------------------------------------------
# All 5 registered event types have a loadable schema
# ---------------------------------------------------------------------------


def test_all_registered_event_types_have_loadable_schemas() -> None:
    from app.core.events import REGISTERED_EVENT_TYPES, schema_registry

    reg = schema_registry.get_registry()
    for name, et in REGISTERED_EVENT_TYPES.items():
        validator = reg.get_validator(name, et.version)
        assert validator is not None
