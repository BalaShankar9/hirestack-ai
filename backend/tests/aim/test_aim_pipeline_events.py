"""B1 \u2014 contract tests for the AIM emitter wiring.

Verifies that ``analyze_assignment`` and ``generate_section`` emit the
streaming lifecycle events the SSE route depends on. Pure-Python; no
network, no DB.
"""
from __future__ import annotations

from typing import Any

import pytest
from unittest.mock import AsyncMock, patch


class CollectingEmitter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, event_type: str, **kwargs: Any) -> None:
        self.events.append({"event_type": event_type, **kwargs})

    def by_type(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["event_type"] == event_type]


def _agent_result(content=None, *, flags=None, metadata=None, latency_ms=10):
    from ai_engine.agents.base import AgentResult
    return AgentResult(
        content=content or {},
        quality_scores={},
        flags=list(flags or []),
        latency_ms=latency_ms,
        metadata=metadata or {},
    )


# ─── analyze_assignment ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_emits_parser_then_recon_on_happy_path():
    from ai_engine.chains import aim_pipeline

    parsed = {"directive": "analyse", "confidence": 0.95}
    recon = {"section_strategy": [{"section_title": "Intro"}]}

    with patch.object(aim_pipeline.AIMParserAgent, "run",
                      new=AsyncMock(return_value=_agent_result(parsed))), \
         patch.object(aim_pipeline.AIMReconAgent, "run",
                      new=AsyncMock(return_value=_agent_result(recon))):
        emitter = CollectingEmitter()
        result = await aim_pipeline.analyze_assignment(
            "brief text", "rubric text", emit=emitter,
        )

    assert not result.needs_clarification
    types = [(e["event_type"], e.get("agent"), e.get("status")) for e in emitter.events]
    assert ("agent_status", "parser", "running") in types
    assert ("agent_status", "parser", "completed") in types
    assert ("agent_status", "recon", "running") in types
    assert ("agent_status", "recon", "completed") in types
    # Parser completes before recon starts
    parser_done_idx = next(i for i, e in enumerate(emitter.events)
                           if e.get("agent") == "parser" and e.get("status") == "completed")
    recon_start_idx = next(i for i, e in enumerate(emitter.events)
                           if e.get("agent") == "recon" and e.get("status") == "running")
    assert parser_done_idx < recon_start_idx


@pytest.mark.asyncio
async def test_analyze_skips_recon_on_clarification_needed():
    from ai_engine.chains import aim_pipeline

    parsed = {"directive": "analyse", "confidence": 0.5,
              "clarification_questions": [{"question": "Word count?"}]}

    with patch.object(aim_pipeline.AIMParserAgent, "run",
                      new=AsyncMock(return_value=_agent_result(
                          parsed, flags=["needs_clarification"]))), \
         patch.object(aim_pipeline.AIMReconAgent, "run",
                      new=AsyncMock()) as recon_run:
        emitter = CollectingEmitter()
        result = await aim_pipeline.analyze_assignment(
            "brief", emit=emitter,
        )

    assert result.needs_clarification
    recon_run.assert_not_called()
    agents = {e.get("agent") for e in emitter.events}
    assert "parser" in agents
    assert "recon" not in agents


# ─── generate_section ──────────────────────────────────────────────────


def _section() -> dict[str, Any]:
    return {"id": "sec-1", "title": "Intro", "word_limit": 500}


def _writer_result(text: str = "draft body") -> Any:
    return _agent_result({"content": text, "blocks": [], "word_count": len(text.split())})


def _reviewer_result(score: float, *, passed: bool) -> Any:
    return _agent_result(
        {"verdict": "pass" if passed else "fail", "ranked_issues": []},
        metadata={"weighted_score": score, "passed_gate": passed},
    )


@pytest.mark.asyncio
async def test_generate_section_emits_writer_reviewer_pair_per_attempt_and_complete_on_pass():
    from ai_engine.chains import aim_pipeline

    with patch.object(aim_pipeline.AIMWriterAgent, "run",
                      new=AsyncMock(return_value=_writer_result())), \
         patch.object(aim_pipeline.AIMReviewerAgent, "run",
                      new=AsyncMock(return_value=_reviewer_result(90.0, passed=True))):
        emitter = CollectingEmitter()
        result = await aim_pipeline.generate_section(
            section=_section(), parsed={}, recon={}, section_id="sec-1",
            max_attempts=3, emit=emitter,
        )

    assert result.stop_reason == "passed"
    assert result.final_passed_gate is True

    # Exactly one writer+reviewer pair (since first attempt passed)
    writer_evts = [e for e in emitter.events if e.get("agent") == "writer"]
    reviewer_evts = [e for e in emitter.events if e.get("agent") == "reviewer"]
    assert len(writer_evts) == 2  # running + completed
    assert len(reviewer_evts) == 2  # running + completed
    # passed_gate surfaced in reviewer completed event data
    completed = next(e for e in reviewer_evts if e["status"] == "completed")
    assert completed["data"]["passed_gate"] is True
    assert completed["data"]["weighted_score"] == 90.0


@pytest.mark.asyncio
async def test_generate_section_emits_retry_event_when_attempt_below_gate():
    from ai_engine.chains import aim_pipeline

    # Two attempts: first fails, second passes
    review_scores = iter([
        _reviewer_result(60.0, passed=False),
        _reviewer_result(88.0, passed=True),
    ])

    async def reviewer_side_effect(_ctx):
        return next(review_scores)

    with patch.object(aim_pipeline.AIMWriterAgent, "run",
                      new=AsyncMock(return_value=_writer_result())), \
         patch.object(aim_pipeline.AIMReviewerAgent, "run",
                      new=AsyncMock(side_effect=reviewer_side_effect)):
        emitter = CollectingEmitter()
        result = await aim_pipeline.generate_section(
            section=_section(), parsed={}, recon={}, section_id="sec-1",
            max_attempts=3, emit=emitter,
        )

    assert result.stop_reason == "passed"
    assert len(result.history) == 2
    retries = emitter.by_type("retry")
    assert len(retries) == 1
    assert retries[0]["status"] == "retrying"
    assert retries[0]["data"]["attempt"] == 1


# ─── predict_grade ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_predict_grade_emits_running_then_completed_with_grade_data():
    from ai_engine.chains import aim_pipeline

    grade_payload = {"predicted_grade": "A-", "confidence": 0.82}
    with patch.object(aim_pipeline.AIMGradePredictorAgent, "run",
                      new=AsyncMock(return_value=_agent_result(grade_payload))):
        emitter = CollectingEmitter()
        result = await aim_pipeline.predict_grade(
            parsed={"directive": "analyse"},
            section_reviews=[{"section_id": "s1", "weighted_score": 80}],
            emit=emitter,
        )

    assert result == grade_payload
    statuses = [(e.get("agent"), e.get("status")) for e in emitter.events
                if e.get("agent") == "grade_predictor"]
    assert ("grade_predictor", "running") in statuses
    assert ("grade_predictor", "completed") in statuses
    completed = next(e for e in emitter.events
                     if e.get("agent") == "grade_predictor"
                     and e.get("status") == "completed")
    assert completed["data"]["predicted_grade"] == "A-"
    assert completed["data"]["sections_reviewed"] == 1


# ─── fix_section ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fix_section_emits_running_then_completed_with_fix_count():
    from ai_engine.chains import aim_pipeline

    fix_payload = {"fixes": [{"id": "f1"}, {"id": "f2"}, {"id": "f3"}]}
    with patch.object(aim_pipeline.AIMFixAgent, "run",
                      new=AsyncMock(return_value=_agent_result(fix_payload))):
        emitter = CollectingEmitter()
        result = await aim_pipeline.fix_section(
            section={"id": "sec-1", "title": "Intro", "word_limit": 500},
            parsed={"directive": "analyse"},
            draft_content="one two three four five",
            section_id="sec-1",
            emit=emitter,
        )

    assert result == fix_payload
    statuses = [(e.get("agent"), e.get("status")) for e in emitter.events
                if e.get("agent") == "fixer"]
    assert ("fixer", "running") in statuses
    assert ("fixer", "completed") in statuses
    completed = next(e for e in emitter.events
                     if e.get("agent") == "fixer" and e.get("status") == "completed")
    assert completed["data"]["fix_count"] == 3
    assert completed["data"]["before_words"] == 5
    assert completed["data"]["section_id"] == "sec-1"
