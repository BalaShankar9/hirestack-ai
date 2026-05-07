"""Tests for the PR-8 outbox writer + envelope.

Uses a fake Supabase client so the suite stays unit-scoped. Real DB
behaviour (the partitioned table + UNIQUE constraint) is covered by the
migration itself and will be exercised end-to-end in PR-9.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

from app.core.events import (
    AIM_SOURCE_CREATED,
    EventEnvelope,
    GENERATION_REQUESTED,
    OUTBOX_TABLE,
    OutboxWriter,
    REGISTERED_EVENT_TYPES,
    current_version,
)


# ---------------------------------------------------------------------------
# Fake Supabase client
# ---------------------------------------------------------------------------


class _UniqueViolation(Exception):
    code = "23505"

    def __str__(self) -> str:  # pragma: no cover — fmt only
        return "duplicate key value violates unique constraint"


@dataclass
class _Response:
    data: Any


@dataclass
class _FakeQuery:
    table: "_FakeTable"
    op: str
    payload: dict[str, Any] | None = None
    filters: list[tuple[str, str]] = field(default_factory=list)
    limit_n: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        self.op = "select"
        return self

    def insert(self, row: dict[str, Any]) -> "_FakeQuery":
        self.op = "insert"
        self.payload = row
        return self

    def eq(self, col: str, val: str) -> "_FakeQuery":
        self.filters.append((col, val))
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self.limit_n = n
        return self

    def execute(self) -> _Response:
        if self.op == "insert":
            assert self.payload is not None
            row = dict(self.payload)
            key = (row.get("org_id"), row.get("idempotency_key"))
            if row.get("idempotency_key") is not None and key in self.table.dedupe_index:
                raise _UniqueViolation()
            self.table.rows.append(row)
            if row.get("idempotency_key") is not None:
                self.table.dedupe_index[key] = row
            return _Response(data=[row])

        if self.op == "select":
            matched = [
                r
                for r in self.table.rows
                if all(str(r.get(c)) == str(v) for c, v in self.filters)
            ]
            if self.limit_n is not None:
                matched = matched[: self.limit_n]
            return _Response(data=matched)

        raise AssertionError(f"unexpected op {self.op}")


@dataclass
class _FakeTable:
    rows: list[dict[str, Any]] = field(default_factory=list)
    dedupe_index: dict[tuple[Any, Any], dict[str, Any]] = field(default_factory=dict)

    def insert(self, row: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(table=self, op="insert", payload=row)

    def select(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return _FakeQuery(table=self, op="select")


class _FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        return self.tables.setdefault(name, _FakeTable())


# ---------------------------------------------------------------------------
# Envelope tests
# ---------------------------------------------------------------------------


def _ok_envelope(**overrides: Any) -> EventEnvelope:
    base = dict(
        event_type=AIM_SOURCE_CREATED.name,
        event_version=AIM_SOURCE_CREATED.version,
        org_id=uuid.uuid4(),
        payload={"source_id": str(uuid.uuid4()), "name": "ACME"},
    )
    base.update(overrides)
    return EventEnvelope(**base)


def test_envelope_round_trip_dict_shape() -> None:
    env = _ok_envelope(idempotency_key="abc-123")
    row = env.to_outbox_row()

    assert row["event_type"] == AIM_SOURCE_CREATED.name
    assert row["event_version"] == AIM_SOURCE_CREATED.version
    assert row["idempotency_key"] == "abc-123"
    assert isinstance(row["payload"], dict)
    # Times stay ISO-8601 UTC.
    assert row["occurred_at"].endswith("+00:00")


def test_envelope_rejects_unknown_event_type() -> None:
    with pytest.raises(ValueError, match="unknown event_type"):
        EventEnvelope(
            event_type="aim.totally.fake",
            event_version=1,
            org_id=uuid.uuid4(),
        )


def test_envelope_rejects_wrong_version() -> None:
    with pytest.raises(ValueError, match="event_version"):
        EventEnvelope(
            event_type=GENERATION_REQUESTED.name,
            event_version=current_version(GENERATION_REQUESTED.name) + 7,
            org_id=uuid.uuid4(),
        )


def test_envelope_requires_tz_aware_occurred_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EventEnvelope(
            event_type=AIM_SOURCE_CREATED.name,
            event_version=AIM_SOURCE_CREATED.version,
            org_id=uuid.uuid4(),
            occurred_at=datetime(2026, 5, 7),  # naive
        )


def test_envelope_normalises_to_utc() -> None:
    from datetime import timedelta

    ist = timezone(timedelta(hours=5, minutes=30))
    env = _ok_envelope(occurred_at=datetime(2026, 5, 7, 18, 30, tzinfo=ist))
    assert env.occurred_at.tzinfo == timezone.utc
    assert env.occurred_at.hour == 13  # 18:30 IST = 13:00 UTC


def test_registered_event_types_match_plan() -> None:
    expected = {
        "aim.assignment.created",
        "aim.source.created",
        "generation.requested",
        "generation.completed",
        "mission.draft.created",
    }
    assert set(REGISTERED_EVENT_TYPES.keys()) == expected
    for et in REGISTERED_EVENT_TYPES.values():
        assert et.version == 1


# ---------------------------------------------------------------------------
# OutboxWriter tests
# ---------------------------------------------------------------------------


def test_writer_appends_envelope() -> None:
    fake = _FakeSupabase()
    writer = OutboxWriter(fake)
    env = _ok_envelope(idempotency_key="k1")

    row = writer.append(env)

    assert row["event_id"] == str(env.event_id)
    assert row["event_type"] == env.event_type
    assert fake.tables[OUTBOX_TABLE].rows == [row]


def test_writer_dedupes_on_unique_violation() -> None:
    fake = _FakeSupabase()
    writer = OutboxWriter(fake)
    org = uuid.uuid4()
    first = _ok_envelope(org_id=org, idempotency_key="same")
    second = _ok_envelope(org_id=org, idempotency_key="same")

    row1 = writer.append(first)
    row2 = writer.append(second)

    assert row1 == row2
    # Only one row landed despite two appends.
    assert len(fake.tables[OUTBOX_TABLE].rows) == 1


def test_writer_re_raises_on_non_dedupe_failure() -> None:
    class _BoomTable(_FakeTable):
        def insert(self, row: dict[str, Any]) -> _FakeQuery:  # type: ignore[override]
            raise RuntimeError("connection reset")

    class _BoomSupabase(_FakeSupabase):
        def table(self, name: str) -> _FakeTable:  # type: ignore[override]
            return self.tables.setdefault(name, _BoomTable())

    writer = OutboxWriter(_BoomSupabase())
    with pytest.raises(RuntimeError, match="connection reset"):
        writer.append(_ok_envelope(idempotency_key="k"))


def test_writer_does_not_dedupe_when_no_idempotency_key() -> None:
    fake = _FakeSupabase()
    writer = OutboxWriter(fake)
    org = uuid.uuid4()
    env_a = _ok_envelope(org_id=org, idempotency_key=None)
    env_b = _ok_envelope(org_id=org, idempotency_key=None)

    writer.append(env_a)
    writer.append(env_b)

    # Two distinct rows because no idempotency key was supplied.
    assert len(fake.tables[OUTBOX_TABLE].rows) == 2
