"""
P1-10: Verify critic scores are meaningful — not all 85s.

Tests that the CriticAgent:
- Produces differentiated scores when the AI returns different quality signals.
- Correctly decides revision flags based on pipeline-calibrated thresholds.
- Clamps out-of-range scores to [0, 100].
- Computes weighted quality scores per pipeline type.
- Detects diminishing returns across revision rounds and stops cycling.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_engine.agents.critic import CriticAgent, _PIPELINE_THRESHOLDS, _DIMENSION_WEIGHTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(quality_scores: dict, issues: list | None = None) -> MagicMock:
    """Return a mock AIClient whose complete_json resolves to the given scores."""
    client = MagicMock()
    client.complete_json = AsyncMock(return_value={
        "quality_scores": quality_scores,
        "feedback": {
            "critical_issues": issues or [],
            "suggestions": [],
        },
        "confidence": 0.85,
        "needs_revision": False,  # The agent overrides this deterministically.
    })
    return client


def _run(coro):
    # Py3.13+ removed implicit event-loop creation in the main thread, so we
    # create a fresh loop per call. This keeps the helper synchronous (the
    # test classes here aren't async-collected by pytest-asyncio) while
    # being safe across 3.10 → 3.14.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 1. Scores are propagated as-is (clamped to 0-100) and not collapsed to 85
# ---------------------------------------------------------------------------

class TestScoresAreDifferentiated:
    def test_high_quality_content_produces_high_scores(self):
        """Strong content → all dimensions high → no revision needed."""
        scores = {"impact": 92, "clarity": 88, "tone_match": 91, "completeness": 95}
        agent = CriticAgent(ai_client=_make_client(scores))
        result = _run(agent.run({"content": "Strong CV draft"}))
        assert result.quality_scores["impact"] == 92
        assert result.quality_scores["clarity"] == 88
        assert result.quality_scores["tone_match"] == 91
        assert result.quality_scores["completeness"] == 95
        assert result.needs_revision is False

    def test_low_quality_content_produces_low_scores_and_flags_revision(self):
        """Weak content → at least one dimension below threshold → revision needed."""
        scores = {"impact": 45, "clarity": 52, "tone_match": 38, "completeness": 67}
        agent = CriticAgent(ai_client=_make_client(scores))
        result = _run(agent.run({"content": "Weak CV draft"}))
        assert result.quality_scores["impact"] == 45
        assert result.quality_scores["tone_match"] == 38
        assert result.needs_revision is True

    def test_mixed_scores_with_one_failing_dimension_triggers_revision(self):
        """If one dimension is below the revision threshold, revision is still required."""
        scores = {"impact": 85, "clarity": 88, "tone_match": 85, "completeness": 60}
        agent = CriticAgent(ai_client=_make_client(scores))
        result = _run(agent.run({"content": "Mixed quality CV"}))
        # Default revision threshold is 70 — completeness=60 should trigger revision.
        assert result.needs_revision is True

    def test_all_dimensions_above_pass_threshold_no_revision(self):
        """Scores just above pass threshold → no revision."""
        scores = {"impact": 82, "clarity": 83, "tone_match": 81, "completeness": 84}
        agent = CriticAgent(ai_client=_make_client(scores))
        result = _run(agent.run({"content": "Above-threshold CV"}))
        assert result.needs_revision is False

    def test_scores_are_not_uniform_for_varied_inputs(self):
        """Two different AI responses must produce two different weighted scores."""
        high_client = _make_client({"impact": 90, "clarity": 88, "tone_match": 92, "completeness": 91})
        low_client = _make_client({"impact": 42, "clarity": 38, "tone_match": 50, "completeness": 55})

        high_agent = CriticAgent(ai_client=high_client)
        low_agent = CriticAgent(ai_client=low_client)

        high_result = _run(high_agent.run({"content": "Strong content"}))
        low_result = _run(low_agent.run({"content": "Weak content"}))

        assert high_result.content["weighted_quality_score"] > low_result.content["weighted_quality_score"]


# ---------------------------------------------------------------------------
# 2. Out-of-range score clamping
# ---------------------------------------------------------------------------

class TestScoreClamping:
    def test_score_above_100_is_clamped(self):
        """LLM returning 110 must be clamped to 100."""
        scores = {"impact": 110, "clarity": 95, "tone_match": 88, "completeness": 92}
        agent = CriticAgent(ai_client=_make_client(scores))
        result = _run(agent.run({"content": "Overflow scores"}))
        assert result.quality_scores["impact"] == 100

    def test_score_below_0_is_clamped(self):
        """LLM returning -5 must be clamped to 0."""
        scores = {"impact": -5, "clarity": 72, "tone_match": 68, "completeness": 74}
        agent = CriticAgent(ai_client=_make_client(scores))
        result = _run(agent.run({"content": "Underflow scores"}))
        assert result.quality_scores["impact"] == 0
        assert result.needs_revision is True

    def test_non_numeric_score_defaults_to_zero(self):
        """LLM returning a string for a score must be converted to 0."""
        scores = {"impact": "excellent", "clarity": 75, "tone_match": 72, "completeness": 78}
        agent = CriticAgent(ai_client=_make_client(scores))
        result = _run(agent.run({"content": "Bad score type"}))
        assert result.quality_scores["impact"] == 0


# ---------------------------------------------------------------------------
# 3. Pipeline-calibrated thresholds
# ---------------------------------------------------------------------------

class TestPipelineThresholds:
    def test_cv_generation_uses_higher_threshold(self):
        """CV pipeline has revision_threshold=72; a score of 71 should trigger revision."""
        rev_thresh, _ = _PIPELINE_THRESHOLDS["cv_generation"]
        assert rev_thresh == 72

        scores = {"impact": 71, "clarity": 85, "tone_match": 88, "completeness": 90}
        agent = CriticAgent(ai_client=_make_client(scores))
        context = {
            "content": "CV draft",
            "original_context": {"pipeline": "cv_generation"},
        }
        result = _run(agent.run(context))
        assert result.needs_revision is True

    def test_gap_analysis_uses_lower_threshold(self):
        """Gap analysis pipeline has revision_threshold=60; a score of 65 should not trigger."""
        rev_thresh, pass_thresh = _PIPELINE_THRESHOLDS["gap_analysis"]
        assert rev_thresh == 60

        scores = {"impact": 65, "clarity": 76, "tone_match": 70, "completeness": 77}
        agent = CriticAgent(ai_client=_make_client(scores))
        context = {
            "content": "Gap analysis output",
            "original_context": {"pipeline": "gap_analysis"},
        }
        result = _run(agent.run(context))
        # 65 >= rev_thresh(60), and all >= pass_thresh(75)? clarity=76, completeness=77, impact=65<75
        # impact(65) < pass_thresh(75) → needs_revision
        assert result.needs_revision is True

    def test_all_pass_gap_analysis_no_revision(self):
        """All scores above gap_analysis pass threshold → no revision."""
        scores = {"impact": 76, "clarity": 76, "tone_match": 76, "completeness": 76}
        agent = CriticAgent(ai_client=_make_client(scores))
        context = {
            "content": "Good gap analysis",
            "original_context": {"pipeline": "gap_analysis"},
        }
        result = _run(agent.run(context))
        assert result.needs_revision is False


# ---------------------------------------------------------------------------
# 4. Weighted quality score
# ---------------------------------------------------------------------------

class TestWeightedQualityScore:
    def test_weighted_score_uses_cv_weights(self):
        """CV generation uses impact-heavy weights (0.35, 0.25, 0.15, 0.25)."""
        weights = _DIMENSION_WEIGHTS["cv_generation"]
        scores = {"impact": 80, "clarity": 80, "tone_match": 80, "completeness": 80}
        expected = sum(80 * w for w in weights.values())

        agent = CriticAgent(ai_client=_make_client(scores))
        context = {
            "content": "CV draft",
            "original_context": {"pipeline": "cv_generation"},
        }
        result = _run(agent.run(context))
        assert abs(result.content["weighted_quality_score"] - expected) < 0.1

    def test_weighted_score_present_in_content(self):
        """weighted_quality_score must always appear in the result content."""
        scores = {"impact": 70, "clarity": 70, "tone_match": 70, "completeness": 70}
        agent = CriticAgent(ai_client=_make_client(scores))
        result = _run(agent.run({"content": "Content"}))
        assert "weighted_quality_score" in result.content
        assert isinstance(result.content["weighted_quality_score"], (int, float))


# ---------------------------------------------------------------------------
# 5. Diminishing returns — revision loop termination
# ---------------------------------------------------------------------------

class TestDiminishingReturns:
    def test_no_improvement_across_rounds_stops_revision(self):
        """If scores didn't improve by ≥3 points, needs_revision must be False
        even when scores are below pass threshold (to avoid endless loops)."""
        # Scores still borderline (below pass=80 default), but barely improved
        prev_scores = {"impact": 72, "clarity": 74, "tone_match": 71, "completeness": 73}
        curr_scores = {"impact": 73, "clarity": 75, "tone_match": 71, "completeness": 73}  # max delta = 1

        agent = CriticAgent(ai_client=_make_client(curr_scores))
        context = {
            "content": "Borderline CV draft",
            "previous_quality_scores": prev_scores,
        }
        result = _run(agent.run(context))
        # Even though scores are below pass threshold, max delta < 3 → stop
        assert result.needs_revision is False

    def test_meaningful_improvement_continues_revision(self):
        """If at least one dimension improved by ≥3 points, continue revising."""
        prev_scores = {"impact": 65, "clarity": 72, "tone_match": 68, "completeness": 71}
        curr_scores = {"impact": 70, "clarity": 72, "tone_match": 72, "completeness": 71}  # tone improved +4

        agent = CriticAgent(ai_client=_make_client(curr_scores))
        context = {
            "content": "Improving CV draft",
            "previous_quality_scores": prev_scores,
        }
        result = _run(agent.run(context))
        # tone_match improved +4 ≥ 3, so revision should still be flagged if below thresholds
        assert result.needs_revision is True

    def test_quality_deltas_are_tracked(self):
        """quality_deltas dict must be present when previous_quality_scores supplied."""
        prev = {"impact": 60, "clarity": 70, "tone_match": 65, "completeness": 68}
        curr = {"impact": 75, "clarity": 78, "tone_match": 70, "completeness": 73}

        agent = CriticAgent(ai_client=_make_client(curr))
        result = _run(agent.run({"content": "Revised CV", "previous_quality_scores": prev}))
        deltas = result.content.get("quality_deltas", {})
        assert deltas["impact"] == pytest.approx(15.0)
        assert deltas["clarity"] == pytest.approx(8.0)
