"""
ExperienceLevelClassifier — deterministic Phase 1 agent.

Maps job title + years of experience to a standard seniority level
and estimated salary band multiplier.  No LLM call.
"""
from __future__ import annotations


from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


# (min_years, max_years, multiplier relative to median)
_LEVELS: dict[str, tuple[int, int, float]] = {
    "intern":     (0, 0, 0.40),
    "junior":     (0, 2, 0.65),
    "mid":        (2, 5, 1.00),
    "senior":     (5, 10, 1.30),
    "staff":      (8, 15, 1.60),
    "principal":  (12, 25, 1.90),
    "director":   (10, 25, 2.00),
    "vp":         (15, 30, 2.50),
}

_TITLE_LEVEL_MAP: dict[str, str] = {
    "intern": "intern", "trainee": "intern", "apprentice": "intern",
    "junior": "junior", "entry": "junior", "associate": "junior", "graduate": "junior",
    "mid": "mid", "intermediate": "mid", "ii": "mid",
    "senior": "senior", "sr.": "senior", "sr ": "senior", "iii": "senior", "lead": "senior",
    "staff": "staff", "principal": "principal", "architect": "staff",
    "director": "director", "head of": "director",
    "vp": "vp", "vice president": "vp", "chief": "vp",
    "distinguished": "principal", "fellow": "principal",
}


class ExperienceLevelClassifier(SubAgent):
    """Classifies experience level from title and years."""

    def __init__(self, ai_client=None):
        super().__init__(name="experience_level_classifier", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        title: str = (context.get("title") or "").lower()
        years: int = context.get("years_experience", 0)

        # ── Title-based classification ─────────────────────────
        detected_level = None
        for keyword, level in _TITLE_LEVEL_MAP.items():
            if keyword in title:
                detected_level = level
                break

        # ── Years-based classification (fallback or confirmation)
        years_level = "mid"  # default
        if years <= 1:
            years_level = "junior"
        elif years <= 4:
            years_level = "mid"
        elif years <= 8:
            years_level = "senior"
        elif years <= 14:
            years_level = "staff"
        else:
            years_level = "principal"

        # Merge: title wins if present, otherwise years
        level = detected_level or years_level
        level_info = _LEVELS.get(level, _LEVELS["mid"])

        # Determine band label
        band_labels = {
            "intern": "Entry / Intern Band",
            "junior": "Junior Band (IC1-IC2)",
            "mid": "Mid-Level Band (IC3)",
            "senior": "Senior Band (IC4)",
            "staff": "Staff / Principal Band (IC5-IC6)",
            "principal": "Principal / Distinguished Band (IC6+)",
            "director": "Management Band (M1-M2)",
            "vp": "Executive Band (M3+)",
        }

        return SubAgentResult(
            agent_name=self.name,
            data={
                "classified_level": level,
                "years_experience": years,
                "title_detected_level": detected_level,
                "years_based_level": years_level,
                "salary_multiplier": level_info[2],
                "band_label": band_labels.get(level, "Mid-Level Band"),
                "typical_years_range": f"{level_info[0]}-{level_info[1]} years",
            },
            confidence=0.90 if detected_level else 0.75,
        )
