"""
AIM Grade Predictor \u2014 realistic rubric-weighted grade range.

Ceiling rule: distinction-band predictions require every reviewer sub-score
across every section to be \u2265 85, otherwise the predicted band is capped
one band below distinction.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ai_engine.agents.aim.schemas import GRADE_PREDICTOR_SCHEMA
from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.client import AIClient

_PROMPT = (Path(__file__).parent / "prompts" / "grade_predictor_system.md").read_text(encoding="utf-8")

# Buckets per academic_level
_DISTINCTION_BANDS = {
    "ug":   {"first", "1st"},
    "pg":   {"distinction"},
    "mba":  {"distinction"},
    "phd":  {"distinction", "high pass"},
    "other":{"a", "a+", "distinction", "first"},
}


def _is_distinction(band: str, level: str) -> bool:
    return (band or "").strip().lower() in _DISTINCTION_BANDS.get(level, set())


def _all_sections_high(section_reviews: list[dict]) -> bool:
    if not section_reviews:
        return False
    for rev in section_reviews:
        sub = rev.get("sub_scores") or {}
        if not sub:
            return False
        if any(float(v) < 85 for v in sub.values()):
            return False
    return True


class AIMGradePredictorAgent(BaseAgent):
    def __init__(self, ai_client: AIClient | None = None) -> None:
        super().__init__(
            name="aim_grade_predictor",
            system_prompt=_PROMPT,
            output_schema=GRADE_PREDICTOR_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict[str, Any]) -> AgentResult:
        start = time.monotonic_ns()
        parsed = context.get("parsed") or {}
        section_reviews: list[dict] = context.get("section_reviews") or []
        if not section_reviews:
            raise ValueError("aim_grade_predictor: section_reviews required")

        rubric = parsed.get("rubric_breakdown") or []
        academic_level = parsed.get("academic_level") or "ug"
        prompt = (
            f"ACADEMIC LEVEL: {academic_level}\n"
            f"RUBRIC: {rubric}\n\n"
            f"SECTION REVIEWS (per-section sub_scores + ranked_issues):\n{section_reviews}\n\n"
            "Predict the realistic grade range. Be honest. Apply the ceiling rule."
        )
        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            schema=self.output_schema,
            task_type="aim_grade_predictor",
            temperature=0.2,
        )

        # enforce ceiling rule deterministically
        if _is_distinction(result.get("band", ""), academic_level) and not _all_sections_high(section_reviews):
            result["_ceiling_applied"] = True
            # cap predicted_grade_high one band below
            high = int(result.get("predicted_grade_high") or 0)
            low = int(result.get("predicted_grade_low") or 0)
            cap = 69 if academic_level in ("ug", "pg", "mba", "phd") else 89
            if high > cap:
                result["predicted_grade_high"] = cap
            if low > cap - 5:
                result["predicted_grade_low"] = cap - 5
            # Drop band one tier
            result["band"] = "Merit" if academic_level in ("pg", "mba") else "2:1" if academic_level == "ug" else result["band"]

        confidence = float(result.get("confidence", 0.0))
        return self._timed_result(
            start,
            content=result,
            quality_scores={"grade_predictor_confidence": confidence * 100,
                            "predicted_grade_high": float(result.get("predicted_grade_high", 0))},
            metadata={
                "agent": self.name,
                "confidence": confidence,
                "ceiling_applied": bool(result.get("_ceiling_applied")),
            },
        )
