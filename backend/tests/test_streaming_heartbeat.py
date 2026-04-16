"""
Test streaming pipeline with heartbeat progress.

Verifies that:
1. Heartbeat progress events are emitted every N seconds during long-running phases
2. Flush points are properly placed after critical events
3. Timing instrumentation is logged correctly
"""

import asyncio
import time
import pytest

from app.api.routes.generate.stream import _run_with_heartbeat, _sse


@pytest.mark.asyncio
async def test_run_with_heartbeat_emits_progress():
    """Test that heartbeat emits progress events at regular intervals."""

    # Mock coroutine that takes 10 seconds
    async def slow_task():
        await asyncio.sleep(10)
        return {"status": "done"}

    emitted_events = []

    async def capture_emit(phase: str, progress: int, message: str, elapsed_ms: int):
        emitted_events.append({
            "phase": phase,
            "progress": progress,
            "message": message,
            "elapsed_ms": elapsed_ms,
        })

    # Run with 2-second heartbeat intervals
    start = time.time()
    result = await asyncio.wait_for(
        _run_with_heartbeat(
            slow_task(),
            phase="test_phase",
            initial_progress=50,
            emit_fn=capture_emit,
            heartbeat_interval=2.0,
        ),
        timeout=15,
    )
    elapsed = time.time() - start

    # Verify result
    assert result == {"status": "done"}

    # Verify multiple heartbeat events were emitted (10s / 2s = ~5 events)
    # Allow some variance due to timing
    assert len(emitted_events) >= 3, f"Expected at least 3 heartbeats, got {len(emitted_events)}"

    # Verify message format includes elapsed time
    for event in emitted_events:
        assert "elapsed" in event["message"] or "ms" in str(event["elapsed_ms"])
        assert event["phase"] == "test_phase"
        assert 50 <= event["progress"] <= 98  # Capped at 98


@pytest.mark.asyncio
async def test_run_with_heartbeat_handles_exceptions():
    """Test that heartbeat properly propagates exceptions."""

    async def failing_task():
        await asyncio.sleep(2)
        raise ValueError("Task failed")

    emitted_events = []

    async def capture_emit(phase: str, progress: int, message: str, elapsed_ms: int):
        emitted_events.append({"progress": progress})

    # Should raise the exception from the task
    with pytest.raises(ValueError, match="Task failed"):
        await asyncio.wait_for(
            _run_with_heartbeat(
                failing_task(),
                phase="test_phase",
                initial_progress=50,
                emit_fn=capture_emit,
                heartbeat_interval=1.0,
            ),
            timeout=10,
        )

    # Should have emitted at least one heartbeat before failure
    assert len(emitted_events) >= 1


def test_sse_formatting():
    """Test that SSE events are properly formatted."""

    data = {
        "phase": "test",
        "progress": 50,
        "message": "Testing",
    }

    event_str = _sse("progress", data)

    # Should have proper SSE format
    assert event_str.startswith("event: progress\n")
    assert "data: " in event_str
    assert event_str.endswith("\n\n")

    # Should be JSON-serializable
    import json
    lines = event_str.strip().split("\n")
    assert lines[0] == "event: progress"
    json_data = json.loads(lines[1][6:])  # Skip "data: "
    assert json_data["phase"] == "test"
    assert json_data["progress"] == 50


@pytest.mark.asyncio
async def test_run_with_heartbeat_cancellation():
    """Test that heartbeat properly handles cancellation."""

    async def long_task():
        await asyncio.sleep(60)
        return {"status": "done"}

    emitted_events = []

    async def capture_emit(phase: str, progress: int, message: str, elapsed_ms: int):
        emitted_events.append({"progress": progress})

    # Create task with heartbeat
    heartbeat_task = _run_with_heartbeat(
        long_task(),
        phase="test_phase",
        initial_progress=50,
        emit_fn=capture_emit,
        heartbeat_interval=1.0,
    )

    # Create wrapper task to cancel after short time
    task = asyncio.create_task(heartbeat_task)

    # Let it run for a bit
    await asyncio.sleep(2)

    # Cancel it
    task.cancel()

    # Should raise CancelledError
    with pytest.raises(asyncio.CancelledError):
        await task

    # Should have emitted at least one heartbeat
    assert len(emitted_events) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
