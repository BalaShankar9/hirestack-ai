"""S17-P2 — Culture-Fit Interview Coach tests."""
from __future__ import annotations

import pytest

from ai_engine.agents.culture_fit import (
    AnswerCoach,
    ValuesMapper,
    build_culture_fit_tools,
    coach_culture_fit,
    detect_culture_fit_intent,
    extract_culture_signals,
)
from ai_engine.agents.culture_fit.schemas import (
    CultureSignal,
    ValuesQuestion,
)


# ─── stub LLM ──────────────────────────────────────────────────────

class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, **kwargs):
        return self._payload


class _RaisingClient:
    async def complete_json(self, **kwargs):
        raise RuntimeError("no llm")


_FIXTURE_TEXT = (
    "We're building for the long-term. Our team prizes ownership and "
    "bias for action — every engineer is end-to-end on what they "
    "ship. We obsess over customers and treat their feedback as the "
    "primary signal. We hold a high quality bar; ship fast, but never "
    "at the cost of craft. Diversity, inclusion, and belonging are "
    "non-negotiable values for how we hire and operate."
)


# ─── intent ────────────────────────────────────────────────────────

def test_intent_positive():
    assert detect_culture_fit_intent("Help me prep for a culture-fit interview")
    assert detect_culture_fit_intent("Tell me about their company values")


def test_intent_negative():
    assert detect_culture_fit_intent("How do I deploy to Azure?") is None
    assert detect_culture_fit_intent("") is None


# ─── signal extractor ─────────────────────────────────────────────

def test_extract_signals_finds_multiple_dimensions():
    sigs = extract_culture_signals(_FIXTURE_TEXT)
    dims = {s.dimension for s in sigs}
    # Must include the obvious ones
    for required in ("ownership", "customer_obsession", "craft_quality",
                     "long_term_thinking", "diversity_inclusion"):
        assert required in dims, f"missing {required}; got {dims}"
    # All weights bounded
    assert all(0.0 < s.weight <= 3.0 for s in sigs)


def test_extract_signals_empty_text_returns_empty():
    assert extract_culture_signals("") == []


# ─── values mapper ────────────────────────────────────────────────

def test_values_mapper_aggregates_and_orders():
    sigs = [
        CultureSignal(dimension="ownership", evidence="x", weight=2.0),
        CultureSignal(dimension="ownership", evidence="y", weight=1.0),
        CultureSignal(dimension="craft_quality", evidence="z", weight=1.5),
    ]
    vm = ValuesMapper().map(sigs, company="Acme", top_n=2)
    assert vm.scores["ownership"] == 3.0
    assert vm.scores["craft_quality"] == 1.5
    assert vm.top_dimensions[0] == "ownership"
    assert len(vm.top_dimensions) == 2


def test_misalignment_risks_flag_missing_company_values():
    vm = ValuesMapper().map(
        [CultureSignal(dimension="frugality", evidence="frugal", weight=2.0)],
        company="Acme",
    )
    risks = ValuesMapper().misalignment_risks(vm, candidate_values=["learning"])
    assert risks
    assert "frugality" in risks[0]


def test_misalignment_risks_silent_when_aligned():
    vm = ValuesMapper().map(
        [CultureSignal(dimension="ownership", evidence="own", weight=2.0)],
        company="Acme",
    )
    risks = ValuesMapper().misalignment_risks(
        vm, candidate_values=["ownership", "execution speed"],
    )
    assert risks == []


# ─── answer coach ─────────────────────────────────────────────────

def test_questions_for_returns_one_per_known_dim():
    qs = AnswerCoach().questions_for(["ownership", "innovation", "unknown_dim"])
    assert len(qs) == 2
    assert qs[0].dimension == "ownership"


@pytest.mark.asyncio
async def test_prepare_answers_uses_llm_payload():
    payload = {
        "star_situation": "LLM-SIT",
        "star_task": "LLM-TASK",
        "star_action": "LLM-ACTION",
        "star_result": "LLM-RESULT",
        "talking_points": ["tp1"],
        "pitfalls": ["pf1"],
    }
    qs = AnswerCoach().questions_for(["ownership"])
    answers = await AnswerCoach(_StubClient(payload)).prepare_answers(qs)
    assert answers[0].star_action == "LLM-ACTION"
    assert answers[0].talking_points == ["tp1"]


@pytest.mark.asyncio
async def test_prepare_answers_falls_back_when_llm_raises():
    qs = AnswerCoach().questions_for(["ownership"])
    answers = await AnswerCoach(_RaisingClient()).prepare_answers(qs)
    assert answers[0].star_action
    assert answers[0].talking_points


@pytest.mark.asyncio
async def test_prepare_answers_falls_back_on_garbage_payload():
    qs = AnswerCoach().questions_for(["ownership"])
    answers = await AnswerCoach(_StubClient({"star_action": ""})).prepare_answers(qs)
    assert answers[0].star_action  # scaffold filled it in


# ─── e2e ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coach_culture_fit_e2e():
    report = await coach_culture_fit(
        company="Acme",
        company_text=_FIXTURE_TEXT,
        candidate_values=["ownership", "customer obsession"],
        questions_per_dimension=1,
        top_n=4,
    )
    assert report.value_map.top_dimensions
    assert report.questions
    assert len(report.prepared_answers) == len(report.questions)
    # Mismatch check: candidate didn't list craft_quality / long_term_thinking
    assert any("craft" in r or "long term" in r for r in report.misalignment_risks)


@pytest.mark.asyncio
async def test_coach_rejects_empty_company_text():
    with pytest.raises(ValueError):
        await coach_culture_fit(company="X", company_text="   ")


# ─── tool registry ────────────────────────────────────────────────

def test_build_culture_fit_tools_registers():
    reg = build_culture_fit_tools()
    tool = reg.get("coach_culture_fit_interview")
    assert tool is not None
    assert "company_text" in tool.parameters["required"]
