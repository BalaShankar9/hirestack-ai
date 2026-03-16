import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_engine.agents.trace import AgentTracer


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.table = MagicMock(return_value=db)
    db.insert = MagicMock(return_value=db)
    db.execute = AsyncMock(return_value=MagicMock(data=[{"id": "trace-1"}]))
    return db


@pytest.mark.asyncio
async def test_tracer_records_stage():
    tracer = AgentTracer(pipeline_id="pipe-1", pipeline_name="cv_gen", user_id="user-1")
    tracer.record_stage("researcher", latency_ms=1500, status="completed", output_summary={"keywords": 5})
    assert len(tracer.stages) == 1
    assert tracer.stages[0]["agent"] == "researcher"
    assert tracer.stages[0]["latency_ms"] == 1500


@pytest.mark.asyncio
async def test_tracer_builds_trace_record():
    tracer = AgentTracer(pipeline_id="pipe-1", pipeline_name="cv_gen", user_id="user-1")
    tracer.record_stage("researcher", latency_ms=1000, status="completed")
    tracer.record_stage("drafter", latency_ms=5000, status="completed")
    record = tracer.build_record(
        quality_scores={"impact": 87},
        fact_check_flags=[],
        iterations_used=0,
    )
    assert record["pipeline_id"] == "pipe-1"
    assert record["total_latency_ms"] == 6000
    assert record["status"] == "completed"
    assert len(record["stages"]) == 2
