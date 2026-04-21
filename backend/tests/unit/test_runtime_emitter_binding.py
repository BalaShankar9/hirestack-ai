"""Phase B.1.2 — verify the runtime job path
(`_run_generation_job_inner_runtime`) binds the Phase A.2 ContextVar
emitter so enriched events fired inside chains land in
generation_job_events instead of /dev/null."""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import pytest


@pytest.mark.asyncio
async def test_runtime_path_binds_event_emitter_and_persists_enriched_events() -> None:
    """When _run_generation_job_inner_runtime executes, any emit_tool_call
    fired by chains/tools inside the runtime.execute() task tree must be
    persisted via _persist_generation_job_event (which writes to
    generation_job_events that the dock listens to).
    """
    from app.api.routes.generate import jobs as jobs_module
    from ai_engine.agent_events import emit_tool_call

    persisted: List[Dict[str, Any]] = []

    async def _capture_persist(
        sb: Any, tables: Dict[str, str], *,
        job_id: str, user_id: str, application_id: str,
        sequence_no: int, event_name: str, payload: Dict[str, Any],
    ) -> None:
        persisted.append({
            "job_id": job_id,
            "event_name": event_name,
            "payload": payload,
            "sequence_no": sequence_no,
        })

    # Stub the body so it fires an enriched event exactly as a real chain
    # would inside the runtime.execute() task tree.  If the outer wrapper
    # bound the emitter, we'll see this event in `persisted`.  Otherwise
    # the event vanishes into /dev/null and the assertion fails.
    async def _fake_body(*_args: Any, **_kwargs: Any) -> None:
        emit_tool_call("ai.draft_quill", {"task_type": "draft", "model": "gemini"})

    fetched = (
        MagicMock(),  # sb (also passed to _persist_generation_job_event below)
        {"id": "job-1"},
        {"confirmed_facts": {}},
        "app-1",
        ["cv"],
    )

    with patch.object(jobs_module, "_fetch_job_and_application", AsyncMock(return_value=fetched)), \
         patch.object(jobs_module, "_DatabaseSink", MagicMock()), \
         patch.object(jobs_module, "_PipelineRuntime", MagicMock()), \
         patch.object(jobs_module, "_run_generation_job_inner_runtime_body", _fake_body), \
         patch.object(jobs_module, "_persist_generation_job_event", _capture_persist):
        await jobs_module._run_generation_job_inner_runtime("job-1", "user-1")
        # emit_tool_call fires via loop.create_task — give the loop a tick
        # to drain queued telemetry tasks before asserting.
        for _ in range(5):
            await asyncio.sleep(0)

    # The bridged emitter must have captured the enriched tool_call event.
    tool_calls = [e for e in persisted if e["event_name"] == "tool_call"]
    assert len(tool_calls) == 1, f"expected 1 tool_call, got {[e['event_name'] for e in persisted]}"
    assert tool_calls[0]["payload"]["tool"] == "ai.draft_quill"


@pytest.mark.asyncio
async def test_runtime_emitter_token_is_reset_even_on_failure() -> None:
    """If runtime.execute() raises, the ContextVar token must still be
    reset so subsequent jobs in the same process don't inherit a stale
    bound emitter."""
    from app.api.routes.generate import jobs as jobs_module
    from ai_engine.agent_events import get_current_chain_agent

    fetched = (
        MagicMock(), {"id": "job-2"}, {"confirmed_facts": {}}, "app-2", ["cv"],
    )

    async def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("simulated runtime failure")

    with patch.object(jobs_module, "_fetch_job_and_application", AsyncMock(return_value=fetched)), \
         patch.object(jobs_module, "_DatabaseSink", MagicMock()), \
         patch.object(jobs_module, "_PipelineRuntime", MagicMock()), \
         patch.object(jobs_module, "_run_generation_job_inner_runtime_body", AsyncMock(side_effect=_boom)), \
         patch.object(jobs_module, "_persist_generation_job_event", AsyncMock()):
        with pytest.raises(RuntimeError):
            await jobs_module._run_generation_job_inner_runtime("job-2", "user-2")

    # After the exception, no chain-agent context should leak into this scope.
    assert get_current_chain_agent() is None
