"""
TechnicalSkillAnalyst — deep skill-by-skill gap assessment.

Compares every skill in the benchmark against the candidate's profile.
For each skill: identifies current vs required level, gap severity,
and a concrete recommendation for closing the gap.

Pure deterministic analysis — no LLM call. Fast and reliable.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

# Ordered skill levels for comparison
_LEVELS = ["none", "beginner", "intermediate", "advanced", "expert"]
_LEVEL_INDEX = {lvl: i for i, lvl in enumerate(_LEVELS)}

# Keyword heuristics for level detection from profile text
_EXPERT_SIGNALS = re.compile(
    r"(?:architect|lead|design(?:ed)?\s+(?:system|platform)|mentor|principal|"
    r"authored?\s+(?:library|framework)|patent|published|core\s+contributor)",
    re.IGNORECASE,
)
_ADVANCED_SIGNALS = re.compile(
    r"(?:senior|optimize|scalab|distributed|micro.?service|CI/CD|devops|"
    r"performance\s+tun|observability|production\s+(?:deploy|support))",
    re.IGNORECASE,
)


class TechnicalSkillAnalyst(SubAgent):
    """Deterministic skill-by-skill gap analysis."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="technical_skill_analyst", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        user_profile = context.get("user_profile", {})
        benchmark = context.get("benchmark", {})
        jd_text = context.get("jd_text", "")

        # Gather user skills into a lookup: {skill_name_lower: skill_dict}
        user_skills_raw = user_profile.get("skills", [])
        user_skills: dict[str, dict] = {}
        for s in user_skills_raw:
            name = (s.get("name") or s.get("skill") or "").strip()
            if name:
                user_skills[name.lower()] = s

        # Gather benchmark/ideal skills
        ideal_skills = benchmark.get("ideal_skills", [])

        # Also extract must-have / nice-to-have from JD if available
        jd_must_have = set()
        jd_nice_to_have = set()
        for s in benchmark.get("must_have_skills", []):
            jd_must_have.add((s if isinstance(s, str) else s.get("name", "")).lower())
        for s in benchmark.get("nice_to_have_skills", []):
            jd_nice_to_have.add((s if isinstance(s, str) else s.get("name", "")).lower())

        # Experience text to search for level signals
        exp_text = " ".join(
            f"{e.get('title', '')} {e.get('description', '')} {e.get('company', '')}"
            for e in user_profile.get("experience", [])
        )
        proj_text = " ".join(
            f"{p.get('title', '')} {p.get('description', '')} {' '.join(p.get('technologies', []))}"
            for p in user_profile.get("projects", [])
        )
        full_text = f"{exp_text} {proj_text}"

        skill_gaps: list[dict] = []
        matched_skills: list[str] = []
        missing_skills: list[str] = []
        partial_skills: list[str] = []

        for ideal in ideal_skills:
            skill_name = (ideal.get("name") or ideal.get("skill") or "").strip()
            if not skill_name:
                continue

            required_level = self._normalize_level(ideal.get("level") or ideal.get("required_level") or "intermediate")
            importance = self._classify_importance(skill_name.lower(), jd_must_have, jd_nice_to_have, ideal)

            # Find in user profile
            user_skill = user_skills.get(skill_name.lower())
            if user_skill:
                current_level = self._infer_level(user_skill, skill_name, full_text)
            else:
                # Check fuzzy match (e.g., "React.js" vs "React")
                user_skill = self._fuzzy_find(skill_name, user_skills)
                if user_skill:
                    current_level = self._infer_level(user_skill, skill_name, full_text)
                else:
                    current_level = "none"

            gap_severity = self._compute_severity(current_level, required_level, importance)
            time_estimate = self._estimate_time(current_level, required_level)

            if current_level == "none":
                missing_skills.append(skill_name)
            elif _LEVEL_INDEX.get(current_level, 0) < _LEVEL_INDEX.get(required_level, 0):
                partial_skills.append(skill_name)
            else:
                matched_skills.append(skill_name)

            gap_entry = {
                "skill": skill_name,
                "required_level": required_level,
                "current_level": current_level,
                "gap_severity": gap_severity,
                "importance_for_role": importance,
                "recommendation": self._make_recommendation(skill_name, current_level, required_level, gap_severity),
                "estimated_time_to_close": time_estimate,
            }
            skill_gaps.append(gap_entry)

        # Sort: critical first, then by importance
        severity_order = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
        skill_gaps.sort(key=lambda g: (severity_order.get(g["gap_severity"], 9), g["importance_for_role"] != "critical"))

        total = len(skill_gaps)
        matched_count = len(matched_skills)
        score = int((matched_count / max(total, 1)) * 100) if total > 0 else 50

        # Adjust score for partial matches
        partial_bonus = len(partial_skills) * (50 / max(total, 1))
        score = min(100, int(score + partial_bonus * 0.5))

        confidence = min(0.95, 0.4 + 0.05 * len(ideal_skills)) if ideal_skills else 0.3

        return SubAgentResult(
            agent_name=self.name,
            data={
                "skill_gaps": skill_gaps[:12],
                "technical_score": score,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "partial_skills": partial_skills,
                "total_ideal_skills": total,
                "summary": self._build_summary(score, matched_skills, missing_skills, partial_skills),
            },
            confidence=confidence,
        )

    def _normalize_level(self, level: str) -> str:
        level = level.lower().strip()
        if level in _LEVEL_INDEX:
            return level
        if "expert" in level or "senior" in level:
            return "expert"
        if "advanced" in level:
            return "advanced"
        if "beginner" in level or "basic" in level or "entry" in level:
            return "beginner"
        return "intermediate"

    def _classify_importance(self, name_lower: str, must: set, nice: set, ideal: dict) -> str:
        if name_lower in must:
            return "critical"
        if name_lower in nice:
            return "preferred"
        imp = (ideal.get("importance") or ideal.get("importance_for_role") or "").lower()
        if "critical" in imp or "must" in imp or "required" in imp:
            return "critical"
        if "nice" in imp or "prefer" in imp or "bonus" in imp:
            return "preferred"
        return "important"

    def _infer_level(self, skill: dict, skill_name: str, full_text: str) -> str:
        """Infer skill level from profile data and experience context."""
        # If the profile explicitly states a level, use it
        explicit = (skill.get("level") or skill.get("proficiency") or "").lower()
        if explicit in _LEVEL_INDEX:
            return explicit

        # Years-based inference
        years = skill.get("years", skill.get("experience_years", 0))
        if isinstance(years, str):
            try:
                years = float(re.search(r"(\d+\.?\d*)", years).group(1))
            except (AttributeError, ValueError):
                years = 0

        # Context-based boost: check if skill name appears in expert/advanced contexts
        skill_pattern = re.compile(re.escape(skill_name), re.IGNORECASE)
        skill_context_hits = skill_pattern.findall(full_text)
        frequency = len(skill_context_hits)

        if years >= 5 or (frequency >= 5 and _EXPERT_SIGNALS.search(full_text)):
            return "expert"
        if years >= 3 or (frequency >= 3 and _ADVANCED_SIGNALS.search(full_text)):
            return "advanced"
        if years >= 1 or frequency >= 2:
            return "intermediate"
        if years > 0 or frequency >= 1:
            return "beginner"
        return "beginner"

    def _fuzzy_find(self, skill_name: str, user_skills: dict[str, dict]) -> Optional[dict]:
        """Fuzzy match skill name (e.g. React.js → React, PostgreSQL → Postgres)."""
        target = skill_name.lower().replace(".", "").replace("-", "").replace(" ", "")
        for key, val in user_skills.items():
            canon = key.replace(".", "").replace("-", "").replace(" ", "")
            if target in canon or canon in target:
                return val
            # Common aliases
            if target.rstrip("js") == canon.rstrip("js"):
                return val
        return None

    def _compute_severity(self, current: str, required: str, importance: str) -> str:
        cur_idx = _LEVEL_INDEX.get(current, 0)
        req_idx = _LEVEL_INDEX.get(required, 2)
        delta = req_idx - cur_idx

        if delta <= 0:
            return "minor"
        if importance == "critical" and delta >= 2:
            return "critical"
        if importance == "critical" and delta >= 1:
            return "major"
        if delta >= 3:
            return "critical"
        if delta >= 2:
            return "major"
        if delta >= 1:
            return "moderate"
        return "minor"

    def _estimate_time(self, current: str, required: str) -> str:
        cur_idx = _LEVEL_INDEX.get(current, 0)
        req_idx = _LEVEL_INDEX.get(required, 2)
        delta = req_idx - cur_idx

        if delta <= 0:
            return "Already at level"
        if delta == 1:
            return "2-4 weeks focused practice"
        if delta == 2:
            return "1-3 months dedicated study"
        if delta == 3:
            return "3-6 months intensive learning"
        return "6+ months (significant upskilling needed)"

    def _make_recommendation(self, skill: str, current: str, required: str, severity: str) -> str:
        if severity == "minor":
            return f"Already meets or exceeds requirement for {skill}."
        if current == "none":
            return f"Start learning {skill} immediately — focus on foundational concepts and hands-on projects."
        if severity == "critical":
            return f"Urgent: {skill} needs to go from {current} to {required}. Prioritize intensive courses + real-world projects."
        if severity == "major":
            return f"Important: Upgrade {skill} from {current} to {required} through advanced tutorials and practice."
        return f"Grow {skill} from {current} to {required} through targeted practice and project work."

    def _build_summary(self, score: int, matched: list, missing: list, partial: list) -> str:
        parts = []
        parts.append(f"Technical skill match: {score}%.")
        if matched:
            parts.append(f"{len(matched)} skills at or above required level.")
        if partial:
            parts.append(f"{len(partial)} skills need level upgrade.")
        if missing:
            parts.append(f"{len(missing)} required skills not present in profile.")
        return " ".join(parts)
