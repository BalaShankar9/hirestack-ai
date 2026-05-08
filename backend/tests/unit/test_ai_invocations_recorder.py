# backend/tests/unit/test_ai_invocations_recorder.py
"""Tests for ADR-0034 / m7-pr30 ``AIInvocationsRecorder``.

The supabase client is mocked via ``app.core.database.get_supabase`` so the
suite never reaches a real database.
"""
from __future__ import annotations

import asyncio
import hashlib
from unittest.mock import MagicMock, patch

import pytest


# ─── Helpers ────────────────────────────────────────────────────────────

def _fake_supabase() -> MagicMock:
    """Return a chainable mock that records ``insert(row).execute()`` calls."""
    sb = MagicMock(name="supabase")
    sb.table.return_value = sb  # .table(...) returns self
    sb.insert.return_value = sb  # .insert(...) returns self
    sb.execute.return_value = MagicMock(data=[], count=None)
    return sb


@pytest.fixture(autouse=True)
def _reset_recorder():
    from ai_engine.observability.ai_invocations import reset_recorder_for_tests
    reset_recorder_for_tests()
    yield
    reset_recorder_for_tests()


@pytest.fixture
def _flag_on(monkeypatch):
    """Force the recorder flag ON for the test."""
    from ai_engine.observability import ai_invocations as mod
    monkeypatch.setattr(mod, "_flag_enabled", lambda: True)
    return mod


def _last_inserted_row(sb: MagicMock) -> dict:
    args, _ = sb.insert.call_args
    assert args, "insert() was not called with a positional row"
    return args[0]


# ─── Tests ──────────────────────────────────────────────────────────────

def test_flag_off_short_circuits_no_db_call():
    """When ff_ai_invocations_recorder is OFF, no supabase call happens."""
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder, _flag_enabled
    sb = _fake_supabase()
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=sb), \
            patch("ai_engine.observability.ai_invocations._flag_enabled", lambda: False):
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="hello", prompt_tokens=10,
            completion_tokens=20, latency_ms=100, outcome="success",
        ))
    sb.insert.assert_not_called()


def test_success_row_written_with_expected_fields(_flag_on):
    sb = _fake_supabase()
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=sb):
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="hi", prompt_tokens=5,
            completion_tokens=15, latency_ms=42, outcome="success",
            task_type="reasoning", cascade_position=0,
        ))
    row = _last_inserted_row(sb)
    assert row["model"] == "gemini-2.5-flash"
    assert row["provider"] == "gemini"
    assert row["outcome"] == "success"
    assert row["task_type"] == "reasoning"
    assert row["prompt_tokens"] == 5
    assert row["completion_tokens"] == 15
    assert row["total_tokens"] == 20
    assert row["latency_ms"] == 42
    assert row["cascade_position"] == 0
    assert row["error_class"] is None if "error_class" in row else "error_class" not in row
    # prompt_hash is sha256 hex of the prompt text
    assert row["prompt_hash"] == hashlib.sha256(b"hi").hexdigest()
    assert len(row["prompt_hash"]) == 64


def test_failure_row_includes_error_class_and_truncated_message(_flag_on):
    sb = _fake_supabase()
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    rec = AIInvocationsRecorder()
    long_msg = "x" * 1000
    err = RuntimeError(long_msg)
    with patch.object(rec, "_get_supabase", return_value=sb):
        asyncio.run(rec.record(
            model="claude-3-5-sonnet-20241022", prompt_text="p", prompt_tokens=1,
            completion_tokens=0, latency_ms=99, outcome="failure",
            cascade_position=2, error=err,
        ))
    row = _last_inserted_row(sb)
    assert row["outcome"] == "failure"
    assert row["provider"] == "anthropic"
    assert row["cascade_position"] == 2
    assert row["error_class"].endswith("RuntimeError")
    assert len(row["error_message"]) == 500
    assert row["error_message"] == "x" * 500


def test_prompt_hash_is_deterministic_sha256(_flag_on):
    sb = _fake_supabase()
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder, _hash_prompt
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=sb):
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="same prompt", prompt_tokens=1,
            completion_tokens=1, latency_ms=1, outcome="success",
        ))
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="same prompt", prompt_tokens=1,
            completion_tokens=1, latency_ms=1, outcome="success",
        ))
    rows = [c.args[0] for c in sb.insert.call_args_list]
    assert rows[0]["prompt_hash"] == rows[1]["prompt_hash"]
    assert rows[0]["prompt_hash"] == _hash_prompt("same prompt")


def test_invalid_outcome_is_dropped_not_inserted(_flag_on):
    sb = _fake_supabase()
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=sb):
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="p", prompt_tokens=1,
            completion_tokens=0, latency_ms=1, outcome="not_a_real_outcome",
        ))
    sb.insert.assert_not_called()


def test_supabase_unavailable_does_not_raise(_flag_on):
    """If get_supabase returns None, record() must swallow."""
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=None):
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="p", prompt_tokens=1,
            completion_tokens=0, latency_ms=1, outcome="success",
        ))
    # No exception = pass.


def test_insert_failure_is_swallowed(_flag_on):
    """Even if .insert().execute() raises, record() must NOT propagate."""
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    sb = _fake_supabase()
    sb.execute.side_effect = RuntimeError("supabase down")
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=sb):
        # Must not raise
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="p", prompt_tokens=1,
            completion_tokens=0, latency_ms=1, outcome="success",
        ))


def test_provider_inference_matches_migration_check_constraint(_flag_on):
    """provider must always be one of {gemini, anthropic, unknown}."""
    sb = _fake_supabase()
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    rec = AIInvocationsRecorder()
    cases = [
        ("claude-3-5-sonnet-20241022", "anthropic"),
        ("gemini-2.5-flash", "gemini"),
        ("gemini-2.5-pro", "gemini"),
        ("text-bison-001", "gemini"),
        ("some-future-model", "unknown"),
        ("", "unknown"),
    ]
    with patch.object(rec, "_get_supabase", return_value=sb):
        for model, expected in cases:
            sb.insert.reset_mock()
            asyncio.run(rec.record(
                model=model, prompt_text="p", prompt_tokens=1,
                completion_tokens=0, latency_ms=1, outcome="success",
            ))
            row = _last_inserted_row(sb)
            assert row["provider"] == expected, f"{model} → {row['provider']} (want {expected})"


def test_get_recorder_returns_singleton():
    from ai_engine.observability.ai_invocations import get_recorder, reset_recorder_for_tests
    reset_recorder_for_tests()
    a = get_recorder()
    b = get_recorder()
    assert a is b
