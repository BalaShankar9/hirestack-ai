"""Anchor tests for the shared `finalize_job_status_payload` helper.

These tests exist to prevent regression to the prior
"two completion blocks, one in each runner, with hand-rolled
status/message dicts" pattern that allowed the frontend's
`succeeded_with_warnings` story to drift from the backend.

If anyone re-introduces a hand-rolled validation→status translation
in jobs.py the contract tests below will fail loudly.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api.routes.generate.helpers import (
    TERMINAL_JOB_STATUSES,
    finalize_job_status_payload,
)


# ── Pure helper behaviour ──────────────────────────────────────────────


def test_returns_succeeded_when_validation_missing():
    payload = finalize_job_status_payload({}, total_steps=7)
    assert payload["status"] == "succeeded"
    assert payload["message"] == "Generation complete."
    assert payload["progress"] == 100
    assert payload["phase"] == "complete"
    assert payload["current_agent"] == "nova"
    assert payload["completed_steps"] == 7
    assert payload["total_steps"] == 7
    assert payload["active_sources_count"] == 0
    assert "finished_at" in payload


def test_returns_succeeded_when_validation_passed_true():
    payload = finalize_job_status_payload(
        {"validation": {"passed": True, "error_count": 0, "warning_count": 0}},
        total_steps=7,
    )
    assert payload["status"] == "succeeded"
    assert payload["message"] == "Generation complete."


def test_returns_succeeded_with_warnings_when_validation_failed():
    payload = finalize_job_status_payload(
        {"validation": {"passed": False, "error_count": 2, "warning_count": 5}},
        total_steps=7,
    )
    assert payload["status"] == "succeeded_with_warnings"
    assert "validation warnings" in payload["message"]
    assert "2 errors" in payload["message"]
    assert "5 warnings" in payload["message"]


def test_handles_none_result_gracefully():
    payload = finalize_job_status_payload(None, total_steps=7)
    assert payload["status"] == "succeeded"


def test_extra_fields_are_merged_but_cannot_override_critical_keys():
    payload = finalize_job_status_payload(
        {"validation": {"passed": False, "error_count": 1, "warning_count": 0}},
        total_steps=7,
        extra_fields={
            "generation_plan": {"steps": ["a", "b"]},
            "result": {"foo": "bar"},
            # These four MUST be ignored — the helper owns them.
            "status": "succeeded",
            "message": "Hijacked!",
            "finished_at": "1970-01-01T00:00:00+00:00",
            "progress": 0,
        },
    )
    assert payload["status"] == "succeeded_with_warnings"
    assert payload["message"] != "Hijacked!"
    assert payload["progress"] == 100
    assert payload["finished_at"] != "1970-01-01T00:00:00+00:00"
    # Caller-supplied non-critical extras DO land.
    assert payload["generation_plan"] == {"steps": ["a", "b"]}
    assert payload["result"] == {"foo": "bar"}


def test_terminal_statuses_set_is_canonical():
    assert TERMINAL_JOB_STATUSES == frozenset(
        {"succeeded", "succeeded_with_warnings", "failed", "cancelled"}
    )
    # And it is immutable.
    with pytest.raises(AttributeError):
        TERMINAL_JOB_STATUSES.add("running")  # type: ignore[attr-defined]


# ── Anti-drift contract: jobs.py must use the helper, not hand-roll ──


def test_jobs_py_does_not_hand_roll_succeeded_with_warnings():
    """jobs.py used to contain TWO copies of the validation→status
    translation. After unification only the helper itself owns the
    string literal `succeeded_with_warnings` as a *value being computed*.

    Any new occurrence of the pattern
        ``status = "succeeded" if ... else "succeeded_with_warnings"``
    in jobs.py is a regression and must fail this test.
    """
    jobs_py = Path(__file__).resolve().parents[2] / "app" / "api" / "routes" / "generate" / "jobs.py"
    text = jobs_py.read_text(encoding="utf-8")
    # Look for the hand-rolled ternary that the helper now owns.
    pattern = re.compile(
        r'=\s*["\']succeeded["\']\s+if\s+\w+\s+else\s+["\']succeeded_with_warnings["\']'
    )
    matches = pattern.findall(text)
    assert matches == [], (
        "Found hand-rolled status ternary in jobs.py — use "
        "finalize_job_status_payload() from helpers.py instead. "
        f"Matches: {matches}"
    )


def test_jobs_py_completion_paths_call_the_helper():
    """Both completion blocks in jobs.py must reference the helper.
    If the helper import disappears from jobs.py the unification has
    been undone."""
    jobs_py = Path(__file__).resolve().parents[2] / "app" / "api" / "routes" / "generate" / "jobs.py"
    text = jobs_py.read_text(encoding="utf-8")
    occurrences = text.count("finalize_job_status_payload")
    # We expect the helper to be referenced at least twice (one per
    # completion path). Imports + call sites = 4 references today.
    assert occurrences >= 2, (
        "jobs.py must call finalize_job_status_payload() from at least "
        f"two completion paths; found {occurrences} reference(s)."
    )
