"""Temporal workflow + checkpoint resume contract pin (m12-pr18).

Companion to backend/tests/temporal/test_per_stage_resume.py — that file
covers the per-stage activity body (`_execute_with_checkpoint`). This
file pins the **workflow-side** resume contract and the **checkpoint-store
best-effort** contract, neither of which is currently asserted.

Why two files
-------------
A Temporal workflow can resume in two semantically different ways:

  1. **Per-stage activity resume** (test_per_stage_resume.py): a worker
     crash mid-pipeline → next attempt's activity body reads the
     checkpoint table and skips completed stages.

  2. **Workflow-level resume** (this file): the Temporal server retries
     a failed activity per its `retry_policy`, or restarts the workflow
     after a worker death. Determinism + retry-policy contracts here
     decide whether resume is correct, infinite, or silently lossy.

The resume invariants this file pins
1. EVERY activity called from `GenerationWorkflow.run` has an explicit
   `retry_policy` (no implicit unbounded retry → no runaway costs on a
   stuck activity).
2. EVERY activity has an explicit `start_to_close_timeout` (no
   indefinite hang on a degraded downstream).
3. `CRITIC_MAX_ATTEMPTS = 3` (in-workflow critic loop bound — separate
   from Temporal's per-activity retry).
4. `CriticGaveUp` is `non_retryable=True` (a logical critic failure must
   NOT loop forever; Temporal's workflow-failure path takes over).
5. Workflow body imports nothing time/random/io non-deterministic — only
   `temporalio.workflow` primitives and dataclasses passed through
   `workflow.unsafe.imports_passed_through()`.
6. Checkpoint summary truncation: `_truncate_summary` swaps oversized
   payloads for a sentinel marker — never silent partial loss.
7. Checkpoint reads on store outage return `None` (the activity treats
   None as "must execute" → safe-default behaviour on outage).
8. Checkpoint writes on store outage are swallowed (best-effort) — a
   checkpoint outage must NEVER block a generation job.
9. `mark_failed` does NOT clear `completed_at` — preserved for forensics
   even if status flips to 'failed'.
10. CHECKPOINT_SUMMARY_MAX_BYTES is 4 KiB exactly (Temporal activity
    history bound contract).

If any of these break, resume becomes unsafe: workflows could retry
forever, lose data silently, or burn cost re-running completed stages.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.temporal import checkpoints as checkpoints_mod
from app.temporal.checkpoints import (
    CHECKPOINT_SUMMARY_MAX_BYTES,
    CHECKPOINTS_TABLE,
    Checkpoint,
    CheckpointStore,
    _truncate_summary,
)
from app.temporal.workflows import (
    CRITIC_MAX_ATTEMPTS,
    CriticGaveUp,
    GenerationWorkflow,
)


# ── (1)+(2) Every activity has retry_policy AND start_to_close_timeout ──


def _workflow_activity_calls() -> list[ast.Call]:
    """Return the AST nodes for every `workflow.execute_activity*(...)` call
    inside the GenerationWorkflow class."""
    src = inspect.getsource(
        __import__("app.temporal.workflows", fromlist=["__init__"])
    )
    tree = ast.parse(src)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr.startswith("execute_activity"):
            # Reach: workflow.execute_activity / workflow.execute_local_activity
            if isinstance(func.value, ast.Name) and func.value.id == "workflow":
                calls.append(node)
    return calls


def test_every_workflow_activity_has_explicit_retry_policy() -> None:
    """Resume invariant: implicit retry policy → unbounded attempts →
    runaway cost. Force every activity to declare its own."""
    calls = _workflow_activity_calls()
    assert calls, "no execute_activity calls found — AST scan broken?"
    for call in calls:
        kwargs = {kw.arg for kw in call.keywords}
        assert "retry_policy" in kwargs, (
            f"workflow.execute_activity at line {call.lineno} is missing "
            "an explicit retry_policy — Temporal default is unbounded retry"
        )


def test_every_workflow_activity_has_explicit_start_to_close_timeout() -> None:
    """Resume invariant: an activity without start_to_close_timeout can
    hang indefinitely on a degraded downstream, blocking the workflow
    forever and preventing resume from making progress."""
    calls = _workflow_activity_calls()
    for call in calls:
        kwargs = {kw.arg for kw in call.keywords}
        assert "start_to_close_timeout" in kwargs, (
            f"workflow.execute_activity at line {call.lineno} is missing "
            "an explicit start_to_close_timeout"
        )


# ── (3) Critic loop bound is 3 ───────────────────────────────────────────


def test_critic_max_attempts_is_three() -> None:
    """Documented contract; downstream cost models multiply by this number."""
    assert CRITIC_MAX_ATTEMPTS == 3


# ── (4) CriticGaveUp is non_retryable ────────────────────────────────────


def test_critic_gave_up_is_non_retryable() -> None:
    """If the critic loop exhausts its in-workflow retries, the resulting
    failure must NOT trigger a Temporal-level retry — that would loop
    forever on a logical failure (model can't satisfy the critic).
    Marking non_retryable=True hands control to the workflow-failure
    path (caller sees WorkflowFailureError, not infinite retry)."""
    err = CriticGaveUp("step=plan reason=missing_evidence")
    assert err.non_retryable is True
    # Type label survives the failure-conversion round-trip.
    assert err.type == "CriticGaveUp"


# ── (5) Workflow body is deterministic (no time/random/io imports) ───────


def test_workflow_module_imports_nothing_nondeterministic() -> None:
    """A Temporal workflow must be deterministic on replay. Importing
    `random`, `time`, `datetime`, `os`, `requests`, etc. at module top
    is a smell that the workflow body might reach for them."""
    src = inspect.getsource(
        __import__("app.temporal.workflows", fromlist=["__init__"])
    )
    tree = ast.parse(src)
    # Collect top-level imports (NOT those inside `with workflow.unsafe.
    # imports_passed_through():` — those are explicitly allowed).
    forbidden = {"random", "time", "os", "requests", "httpx", "asyncio"}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden, (
                    f"workflow module imports `{alias.name}` at line "
                    f"{node.lineno} — non-deterministic on replay"
                )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root not in forbidden, (
                f"workflow module imports from `{node.module}` at line "
                f"{node.lineno} — non-deterministic on replay"
            )


def test_generation_workflow_class_is_temporal_decorated() -> None:
    """`@workflow.defn` is what tells Temporal this class is a workflow.
    A missing decorator silently turns the class into dead code — the
    workflow registers but does not run on replay."""
    # temporalio sets a private attr; check the public name handle instead.
    # The decorator gives the class a workflow definition under the name
    # we passed (`name="GenerationWorkflow"`).
    assert hasattr(GenerationWorkflow, "__temporal_workflow_definition")
    defn = GenerationWorkflow.__temporal_workflow_definition  # type: ignore[attr-defined]
    assert defn.name == "GenerationWorkflow"


# ── (6) Checkpoint summary truncation ────────────────────────────────────


def test_checkpoint_summary_truncation_swaps_for_sentinel_when_oversized() -> None:
    huge = {"blob": "x" * (CHECKPOINT_SUMMARY_MAX_BYTES + 100)}
    out = _truncate_summary(huge)
    assert out is not None
    assert out.get("__truncated__") is True
    assert "original_bytes" in out
    assert out["original_bytes"] > CHECKPOINT_SUMMARY_MAX_BYTES
    # Must NOT preserve the original blob — partial preservation is
    # silent data loss, the marker is the contract.
    assert "blob" not in out


def test_checkpoint_summary_truncation_passes_small_payload_unchanged() -> None:
    small = {"runtime_driven": True, "stage": "recon"}
    out = _truncate_summary(small)
    assert out is small  # identity — no copy, no rewrite


def test_checkpoint_summary_truncation_handles_unencodable_payload() -> None:
    """A payload that fails json.dumps must not raise — return the
    sentinel with reason='encode_failed'. (default=str catches most
    objects; this guards against the few that still raise.)"""

    class Unencodable:
        def __str__(self) -> str:
            raise RuntimeError("cannot stringify")

    out = _truncate_summary({"thing": Unencodable()})
    assert out == {"__truncated__": True, "reason": "encode_failed"}


def test_checkpoint_summary_max_bytes_is_4kib() -> None:
    """Documented contract — Temporal activity history payload bound."""
    assert CHECKPOINT_SUMMARY_MAX_BYTES == 4 * 1024


# ── (7)+(8) Checkpoint reads/writes are best-effort on store outage ─────


def test_checkpoint_read_returns_none_on_store_exception() -> None:
    """Resume invariant: Supabase outage → read returns None → activity
    treats stage as 'must execute'. Safer than False-positive 'complete'
    (which would silently skip work)."""
    broken = MagicMock()
    broken.table.side_effect = RuntimeError("supabase down")
    store = CheckpointStore(supabase=broken)
    assert store.read("job-1", "recon") is None


def test_checkpoint_writes_swallow_store_exceptions() -> None:
    """A checkpoint outage must NEVER raise back into the activity body.
    All three write methods (mark_running, mark_complete, mark_failed)
    swallow exceptions and log."""
    broken = MagicMock()
    broken.table.side_effect = RuntimeError("supabase down")
    store = CheckpointStore(supabase=broken)
    # None of these may raise.
    store.mark_running("job-1", "recon")
    store.mark_complete("job-1", "recon", summary={"ok": True})
    store.mark_failed("job-1", "recon", "RuntimeError")


def test_checkpoint_is_complete_returns_false_on_store_outage() -> None:
    """Read failure → None → not complete. The opposite default would
    silently skip uncompleted work on resume."""
    broken = MagicMock()
    broken.table.side_effect = RuntimeError("supabase down")
    store = CheckpointStore(supabase=broken)
    assert store.is_complete("job-1", "recon") is False


# ── (9) mark_failed preserves completed_at ──────────────────────────────


def test_mark_failed_payload_does_not_clear_completed_at() -> None:
    """Source-pin: a previously-complete stage that mysteriously fails
    must keep its completion timestamp (forensic value). Verified by
    inspecting the payload mark_failed builds — it must NOT include the
    key `completed_at` (so the existing column value is left alone by
    the upsert)."""
    captured: dict[str, Any] = {}

    fake = MagicMock()
    upsert_chain = MagicMock()
    fake.table.return_value.upsert.side_effect = lambda payload, **kw: (
        captured.update({"payload": payload, "kw": kw}) or upsert_chain
    )
    upsert_chain.execute.return_value = None

    store = CheckpointStore(supabase=fake)
    store.mark_failed("job-1", "recon", "RuntimeError")

    payload = captured["payload"]
    assert payload["status"] == "failed"
    assert payload["error_class"] == "RuntimeError"
    assert "completed_at" not in payload, (
        "mark_failed payload set completed_at — would overwrite forensic "
        "completion timestamp on a previously-complete stage"
    )


def test_mark_failed_truncates_long_error_class_to_200_chars() -> None:
    """error_class column is bounded — guard against runaway exception
    type names (e.g. dynamically-generated classes) blowing the column."""
    captured: dict[str, Any] = {}
    fake = MagicMock()
    upsert_chain = MagicMock()
    fake.table.return_value.upsert.side_effect = lambda payload, **kw: (
        captured.update({"payload": payload}) or upsert_chain
    )
    upsert_chain.execute.return_value = None

    store = CheckpointStore(supabase=fake)
    store.mark_failed("job-1", "recon", "X" * 5_000)
    assert len(captured["payload"]["error_class"]) == 200


# ── (10) Resume idempotency: cached complete checkpoint reads back ───────


def test_complete_checkpoint_read_yields_status_complete() -> None:
    """Resume contract: once a stage is marked complete, every
    subsequent read returns status='complete' so downstream
    `is_complete` short-circuits the activity body."""
    fake = MagicMock()
    fake.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
        data={
            "job_id": "job-1",
            "stage": "recon",
            "status": "complete",
            "attempt_count": 1,
            "output_summary": {"runtime_driven": True},
        }
    )
    store = CheckpointStore(supabase=fake)
    cp = store.read("job-1", "recon")
    assert isinstance(cp, Checkpoint)
    assert cp.status == "complete"
    assert cp.attempt_count == 1
    assert cp.output_summary == {"runtime_driven": True}
    assert store.is_complete("job-1", "recon") is True


def test_checkpoints_table_name_is_pipeline_checkpoints() -> None:
    """Migration / runbook / RLS policy all reference this table name.
    A rename here without coordinated migration = silent loss of the
    resume table. Pin the literal."""
    assert CHECKPOINTS_TABLE == "pipeline_checkpoints"


def test_checkpoints_module_uses_named_logger_for_outage_diagnostics() -> None:
    """On-call runs `kubectl logs ... | grep checkpoint_` to triage
    resume outages. The logger name is part of the runbook contract."""
    assert checkpoints_mod.logger.name == "hirestack.temporal.checkpoints"


# ── Source-located file path sanity (catches accidental file moves) ─────


def test_checkpoints_module_lives_at_expected_path() -> None:
    """If this module moves, the per-stage activity import will break
    AND the runbook reference must be updated. Pin the expected path."""
    p = Path(checkpoints_mod.__file__)
    assert p.name == "checkpoints.py"
    assert p.parent.name == "temporal"
