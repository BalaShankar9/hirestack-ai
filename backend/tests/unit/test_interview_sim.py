"""S16-P1 tests — Video Interview Simulator (audio-first)."""
from __future__ import annotations

import pytest

from ai_engine.agents.interview_sim import (
    InterviewSimulator,
    QuestionPlanner,
    build_interview_sim_tools,
    detect_interview_intent,
    score_answer,
)
from ai_engine.agents.orchestration import INTERVIEW_SESSION_PHASE_ORDER
from ai_engine.agents.interview_sim.schemas import (
    InterviewQuestion,
    QuestionKind,
)


# ─── stub LLM client ─────────────────────────────────────────────────

class _StubClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def complete_json(self, **kwargs):
        self.calls += 1
        return self._payload


class _RaisingClient:
    async def complete_json(self, **kwargs):
        raise RuntimeError("LLM down")


_VALID_QUESTIONS_PAYLOAD = {
    "questions": [
        {"text": "Tell me about a project you owned.",
         "kind": "behavioral", "signal_target": "ownership",
         "rubric": ["scope", "decisions", "outcome"]},
        {"text": "How do you handle ambiguous requirements?",
         "kind": "situational", "signal_target": "execution",
         "rubric": ["clarification", "iteration"]},
        {"text": "Why this role at this company?",
         "kind": "motivational", "signal_target": "fit",
         "rubric": ["specific", "honest"]},
        {"text": "Where do you want to be in three years?",
         "kind": "motivational", "signal_target": "trajectory",
         "rubric": ["specific", "growth"]},
        {"text": "What would your first 30 days look like?",
         "kind": "curveball", "signal_target": "initiative",
         "rubric": ["learning", "wins"]},
    ]
}


# ─── intent detection ────────────────────────────────────────────────

def test_intent_basic():
    out = detect_interview_intent("Help me practice interview for a Senior PM")
    assert out is not None
    assert "senior pm" in out["role"].lower() or "pm" in out["role"].lower()


def test_intent_negative():
    assert detect_interview_intent("What is the weather?") is None
    assert detect_interview_intent("") is None
    assert detect_interview_intent("interview the witness") is None  # no verb match


# ─── question planner ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_planner_uses_llm_payload():
    planner = QuestionPlanner(ai_client=_StubClient(_VALID_QUESTIONS_PAYLOAD))
    qs = await planner.plan(role="Software Engineer", question_count=5)
    assert len(qs) == 5
    assert all(isinstance(q, InterviewQuestion) for q in qs)
    assert all(q.id for q in qs)
    assert qs[0].text.startswith("Tell me about")


@pytest.mark.asyncio
async def test_planner_falls_back_to_static_bank():
    planner = QuestionPlanner(ai_client=_RaisingClient())
    qs = await planner.plan(role="Anything", question_count=8)
    assert len(qs) == 8
    assert all(q.text for q in qs)


@pytest.mark.asyncio
async def test_planner_clamps_question_count():
    planner = QuestionPlanner(ai_client=_RaisingClient())
    qs_low = await planner.plan(role="x", question_count=1)
    qs_high = await planner.plan(role="x", question_count=99)
    assert len(qs_low) == 5  # clamped to floor
    assert len(qs_high) == 10  # bank has 10, cap is 15


# ─── scorer ─────────────────────────────────────────────────────────

def _q(rubric=None) -> InterviewQuestion:
    return InterviewQuestion(
        id="q1", text="Tell me about a project you owned.",
        kind=QuestionKind.behavioral, signal_target="ownership",
        rubric=rubric or ["scope", "decisions", "outcome"],
    )


def test_score_empty_answer_is_zero():
    score, fb = score_answer(_q(), "")
    assert score.overall == 0.0
    assert any("empty" in f.lower() for f in fb)


def test_score_strong_star_answer():
    answer = (
        "When I was at my previous company, my role was to lead the rollout of a new "
        "checkout system. I designed the architecture, drove cross-team alignment, "
        "and shipped the rollout in 8 weeks. The result: we increased conversion by "
        "23% and reduced cart-abandonment by 15%."
    )
    score, _ = score_answer(_q(), answer)
    assert score.star_score >= 0.75
    assert score.specificity >= 0.5
    assert score.overall >= 0.6


def test_score_weak_answer_returns_feedback():
    answer = "I worked on stuff."
    score, fb = score_answer(_q(), answer)
    assert score.overall < 0.4
    assert len(fb) >= 2


# ─── orchestrator end-to-end ────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_full_session_flow():
    sim = InterviewSimulator(ai_client=_StubClient(_VALID_QUESTIONS_PAYLOAD))
    session = await sim.start_session(role="PM", question_count=5)
    assert len(session.questions) == 5
    assert session.planning_latency_ms >= 0
    assert tuple(session.phase_latencies.keys()) == INTERVIEW_SESSION_PHASE_ORDER[:1]
    assert session.phase_statuses == {"question_planning": "completed"}
    assert sim.next_question(session) is session.questions[0]

    # Submit answer to first question.
    first = session.questions[0]
    turn = sim.submit_answer(
        session, question_id=first.id,
        answer=("When I was at Acme, my role was to lead a redesign. I drove "
                "the spec, shipped it in 6 weeks, and increased NPS by 18%."),
    )
    assert turn.score is not None
    assert session.cursor == 1

    # Submit a weak answer to question 2.
    sim.submit_answer(session, question_id=session.questions[1].id, answer="I dunno.")

    report = sim.finalize(session)
    assert report.session_id == session.session_id
    assert 0.0 <= report.overall_score <= 1.0
    assert len(report.turns) == 2
    assert report.strengths
    assert report.gaps
    assert session.finalized is True


class _StubTTS:
    async def synthesize(self, text):
        return b"m" * 256 if text else None


@pytest.mark.asyncio
async def test_start_session_records_tts_phase_when_audio_requested():
    sim = InterviewSimulator(
        ai_client=_StubClient(_VALID_QUESTIONS_PAYLOAD),
        tts=_StubTTS(),
    )

    session = await sim.start_session(role="PM", question_count=5, with_audio=True)

    assert tuple(session.phase_latencies.keys()) == INTERVIEW_SESSION_PHASE_ORDER
    assert session.phase_statuses["tts_synthesize"] == "completed"
    assert all(q.audio_b64 for q in session.questions)


@pytest.mark.asyncio
async def test_orchestrator_rejects_blank_role():
    sim = InterviewSimulator(ai_client=_StubClient(_VALID_QUESTIONS_PAYLOAD))
    with pytest.raises(ValueError):
        await sim.start_session(role="   ")


@pytest.mark.asyncio
async def test_orchestrator_unknown_question_id_raises():
    sim = InterviewSimulator(ai_client=_StubClient(_VALID_QUESTIONS_PAYLOAD))
    session = await sim.start_session(role="x", question_count=5)
    with pytest.raises(ValueError):
        sim.submit_answer(session, question_id="bogus", answer="hi")


# ─── tool registry ───────────────────────────────────────────────────

def test_build_interview_sim_tools_registers_start():
    reg = build_interview_sim_tools()
    tool = reg.get("start_interview_sim")
    assert tool is not None
    assert "role" in tool.parameters["required"]


# ─── TTS adapter (no-key safety) ────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_no_key_returns_none(monkeypatch):
    from ai_engine.agents.interview_sim.tts_adapter import TTSAdapter
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    tts = TTSAdapter()
    assert tts.has_provider() is False
    assert await tts.synthesize("hello") is None
