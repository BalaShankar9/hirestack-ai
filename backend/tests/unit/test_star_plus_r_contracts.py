"""C1 — STAR+R contract tests for interview-prep chains.

Verifies the one-line prompt change advertised in
docs/MASTER_INTEGRATION_PLAN.md Week 3 Fri:
"STAR+R column added to all interview-prep chains
(one-line prompt change) | Reflection field appears in outputs"

These are pure string-contract tests; no LLM is invoked.
"""
from __future__ import annotations

from ai_engine.chains.adaptive_document import SYSTEM_PROMPTS
from ai_engine.chains.interview_simulator import (
    EVALUATE_PROMPT,
    EVALUATE_SCHEMA,
    INTERVIEW_SYSTEM,
)


# ── adaptive_document.interview_prep_guide ──────────────────────────


def test_interview_prep_guide_prompt_uses_star_plus_r() -> None:
    prompt = SYSTEM_PROMPTS["interview_prep_guide"]
    assert "STAR+R" in prompt
    # All five letters expanded somewhere in the prompt.
    for component in ("Situation", "Task", "Action", "Result", "Reflection"):
        assert component in prompt, f"missing component: {component}"


def test_interview_prep_guide_explains_reflection_seniority_signal() -> None:
    prompt = SYSTEM_PROMPTS["interview_prep_guide"]
    # The prompt must motivate why Reflection matters so the model
    # actually generates it instead of treating it as optional.
    assert "seniority" in prompt.lower() or "self-awareness" in prompt.lower()


# ── interview_simulator.INTERVIEW_SYSTEM ────────────────────────────


def test_interview_simulator_system_lists_star_plus_r() -> None:
    assert "STAR+R" in INTERVIEW_SYSTEM
    for component in ("Situation", "Task", "Action", "Result", "Reflection"):
        assert component in INTERVIEW_SYSTEM


# ── interview_simulator.EVALUATE_PROMPT ─────────────────────────────


def test_evaluate_prompt_requires_reflection_score() -> None:
    assert "Reflection" in EVALUATE_PROMPT
    # The 0-20 (5 components × 20 = 100 max) replaces the prior 0-25.
    assert "0–20" in EVALUATE_PROMPT or "0-20" in EVALUATE_PROMPT
    assert "STAR+R" in EVALUATE_PROMPT


# ── interview_simulator.EVALUATE_SCHEMA ─────────────────────────────


def test_evaluate_schema_star_scores_includes_reflection() -> None:
    star_scores = EVALUATE_SCHEMA["properties"]["star_scores"]
    props = star_scores["properties"]
    for key in ("situation", "task", "action", "result", "reflection"):
        assert key in props, f"missing star_score: {key}"
        assert props[key]["type"] == "INTEGER"


def test_evaluate_schema_required_fields_unchanged() -> None:
    # Backward compat: required outputs do NOT include star_scores so
    # purely technical answers can omit it without invalidating the response.
    assert "star_scores" not in EVALUATE_SCHEMA["required"]
    assert "score" in EVALUATE_SCHEMA["required"]
    assert "overall_feedback" in EVALUATE_SCHEMA["required"]


def test_evaluate_schema_star_scores_no_extra_components() -> None:
    # Exactly the STAR+R five — guards against accidental extra fields.
    star_scores = EVALUATE_SCHEMA["properties"]["star_scores"]
    assert set(star_scores["properties"].keys()) == {
        "situation", "task", "action", "result", "reflection",
    }
