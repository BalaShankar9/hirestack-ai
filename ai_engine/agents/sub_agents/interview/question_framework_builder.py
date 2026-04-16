"""
QuestionFrameworkBuilder — deterministic Phase 1 agent.

Builds a question framework (category distribution, difficulty curve,
assessment dimensions) based on interview_type and question_count.
No LLM call — pure heuristic.
"""
from __future__ import annotations

import math

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


# Category distribution templates by interview type
_CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    "technical": {
        "technical": 0.50, "system_design": 0.15,
        "problem_solving": 0.15, "behavioral": 0.10, "cultural_fit": 0.10,
    },
    "behavioral": {
        "behavioral": 0.40, "situational": 0.20,
        "cultural_fit": 0.15, "leadership": 0.15, "technical": 0.10,
    },
    "mixed": {
        "technical": 0.30, "behavioral": 0.25,
        "problem_solving": 0.15, "situational": 0.10,
        "cultural_fit": 0.10, "leadership": 0.10,
    },
    "case_study": {
        "case_analysis": 0.40, "problem_solving": 0.25,
        "technical": 0.15, "communication": 0.10, "behavioral": 0.10,
    },
    "executive": {
        "leadership": 0.30, "strategy": 0.25,
        "behavioral": 0.20, "cultural_fit": 0.15, "technical": 0.10,
    },
}

# Difficulty spread: (easy%, medium%, hard%, expert%)
_DIFFICULTY_CURVES: dict[str, tuple[float, ...]] = {
    "easy":     (0.50, 0.30, 0.15, 0.05),
    "moderate": (0.20, 0.40, 0.30, 0.10),
    "hard":     (0.10, 0.25, 0.40, 0.25),
}

# Assessment-dimension bank
_DIMENSIONS: dict[str, list[str]] = {
    "technical":       ["technical_depth", "technical_breadth", "code_quality", "system_thinking"],
    "behavioral":      ["communication", "teamwork", "conflict_resolution", "adaptability"],
    "problem_solving": ["analytical_thinking", "creativity", "structured_approach"],
    "leadership":      ["decision_making", "mentoring", "strategic_vision"],
    "cultural_fit":    ["values_alignment", "motivation", "growth_mindset"],
    "situational":     ["judgement", "pressure_handling", "prioritisation"],
    "system_design":   ["scalability_thinking", "trade_off_analysis"],
    "case_analysis":   ["data_interpretation", "hypothesis_forming"],
    "strategy":        ["market_awareness", "long_term_planning"],
    "communication":   ["clarity", "persuasion", "active_listening"],
}


class QuestionFrameworkBuilder(SubAgent):
    """Builds a question framework: categories, difficulties, assessment dimensions."""

    def __init__(self, ai_client=None):
        super().__init__(name="question_framework_builder", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        interview_type: str = context.get("interview_type", "mixed")
        question_count: int = context.get("question_count", 10)

        # ── Category distribution ─────────────────────────────────
        weights = _CATEGORY_WEIGHTS.get(interview_type, _CATEGORY_WEIGHTS["mixed"])

        # Allocate counts proportionally (floor + distribute remainders)
        raw = {cat: w * question_count for cat, w in weights.items()}
        floored = {cat: int(math.floor(v)) for cat, v in raw.items()}
        remainder = question_count - sum(floored.values())
        sorted_cats = sorted(raw, key=lambda c: raw[c] - floored[c], reverse=True)
        for i in range(remainder):
            floored[sorted_cats[i]] += 1
        category_distribution = {c: n for c, n in floored.items() if n > 0}

        # ── Difficulty curve ──────────────────────────────────────
        # Infer difficulty tier from interview type
        tier = "hard" if interview_type in ("executive", "case_study") else "moderate"
        curve = _DIFFICULTY_CURVES[tier]
        levels = ["easy", "medium", "hard", "expert"]
        raw_diff = [c * question_count for c in curve]
        floored_diff = [int(math.floor(v)) for v in raw_diff]
        diff_rem = question_count - sum(floored_diff)
        frac_idx = sorted(range(len(raw_diff)), key=lambda i: raw_diff[i] - floored_diff[i], reverse=True)
        for i in range(diff_rem):
            floored_diff[frac_idx[i]] += 1
        difficulty_distribution = {levels[i]: floored_diff[i] for i in range(len(levels)) if floored_diff[i] > 0}

        # ── Assessment dimensions ─────────────────────────────────
        dimensions: list[str] = []
        for cat in category_distribution:
            for d in _DIMENSIONS.get(cat, []):
                if d not in dimensions:
                    dimensions.append(d)
        dimensions = dimensions[:10]  # Cap

        return SubAgentResult(
            agent_name=self.name,
            data={
                "interview_type": interview_type,
                "question_count": question_count,
                "category_distribution": category_distribution,
                "difficulty_distribution": difficulty_distribution,
                "assessment_dimensions": dimensions,
            },
            confidence=0.95,
        )
