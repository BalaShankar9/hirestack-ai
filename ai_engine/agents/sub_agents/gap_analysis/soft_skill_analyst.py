"""
SoftSkillCultureAnalyst — soft skills and culture fit assessment.

Analyzes the candidate's soft skills against role requirements:
  • Communication style and evidence
  • Collaboration and teamwork signals
  • Problem-solving approach
  • Adaptability and learning agility
  • Culture fit indicators from JD vs profile
  • Remote/hybrid readiness

Pure deterministic analysis — no LLM call.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

# Soft skill categories with detection patterns
_SOFT_SKILL_PATTERNS: dict[str, re.Pattern] = {
    "communication": re.compile(
        r"(?:present(?:ed|ation)|communicat|wrote|author|document|stakeholder|client.?facing|"
        r"public\s+speak|workshop|training(?:\s+session)?|blog|article|tech\s+talk)",
        re.IGNORECASE,
    ),
    "collaboration": re.compile(
        r"(?:collaborat|cross.?functional|partner|team(?:work|ed)|pair\s+program|"
        r"agile|scrum|standup|retro|sprint(?:\s+planning)?|joint\s+effort)",
        re.IGNORECASE,
    ),
    "leadership": re.compile(
        r"(?:led\b|lead(?:ing|s)?|mentor|coach|manage(?:d|ment)?|supervis|"
        r"initiative|drove|champion|owner(?:ship)?|accountability)",
        re.IGNORECASE,
    ),
    "problem_solving": re.compile(
        r"(?:debug|troubleshoot|root\s+cause|investigat|resolv|analyz|"
        r"architect|design(?:ed)?\s+(?:a|the|new)|optimiz|refactor|"
        r"incident|postmortem|outage)",
        re.IGNORECASE,
    ),
    "adaptability": re.compile(
        r"(?:adapt|pivot|transition|migrat|learn(?:ed|ing)\s+(?:new|quickly)|"
        r"ramp(?:ed)?\s+up|self.?taught|polyglot|diverse|multiple\s+(?:languages|stacks))",
        re.IGNORECASE,
    ),
    "ownership": re.compile(
        r"(?:end.?to.?end|full.?stack|owner(?:ship)?|autonomous|independently|"
        r"self.?directed|initiative|proactiv|built\s+from\s+scratch|zero\s+to\s+one)",
        re.IGNORECASE,
    ),
}

# Culture dimension patterns for JD matching
_CULTURE_PATTERNS: dict[str, re.Pattern] = {
    "innovation_driven": re.compile(r"(?:innovat|experiment|cutting.?edge|state.?of.?the.?art|research|R&D|hack(?:athon)?)", re.IGNORECASE),
    "fast_paced": re.compile(r"(?:fast.?paced|startup|agile|rapid|move\s+fast|iterate|ship\s+quickly)", re.IGNORECASE),
    "collaborative": re.compile(r"(?:collaborat|team.?orient|inclusive|diverse|open\s+(?:source|culture)|flat\s+hierarchy)", re.IGNORECASE),
    "mission_driven": re.compile(r"(?:mission|impact|purpose|social\s+good|sustainability|meaningful|make\s+a\s+difference)", re.IGNORECASE),
    "quality_focused": re.compile(r"(?:quality|reliab|test.?driven|code\s+review|best\s+practic|standard|compliance)", re.IGNORECASE),
    "remote_friendly": re.compile(r"(?:remote|distributed|async|flexible\s+(?:work|hours)|work.?from.?(?:home|anywhere)|hybrid)", re.IGNORECASE),
}


class SoftSkillCultureAnalyst(SubAgent):
    """Deterministic soft skill and culture fit analysis."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="soft_skill_culture_analyst", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        user_profile = context.get("user_profile", {})
        benchmark = context.get("benchmark", {})
        jd_text = context.get("jd_text", "")

        # Build full candidate text corpus for pattern matching
        text_parts: list[str] = []
        for exp in user_profile.get("experience", []):
            text_parts.append(f"{exp.get('title', '')} {exp.get('description', '')}")
        for proj in user_profile.get("projects", []):
            text_parts.append(f"{proj.get('title', '')} {proj.get('description', '')}")
        text_parts.append(user_profile.get("summary", ""))
        candidate_text = " ".join(text_parts)

        # ── Soft skills scoring ─────────────────────────────────
        required_soft_skills = benchmark.get("soft_skills", [])
        soft_skill_assessment: list[dict] = []

        # Score each detection category
        category_scores: dict[str, dict] = {}
        for category, pattern in _SOFT_SKILL_PATTERNS.items():
            hits = pattern.findall(candidate_text)
            frequency = len(hits)
            strength = "strong" if frequency >= 4 else ("moderate" if frequency >= 2 else ("weak" if frequency >= 1 else "none"))
            category_scores[category] = {
                "frequency": frequency,
                "strength": strength,
                "evidence_samples": hits[:3],
            }

        # Match against benchmark soft skills
        for ss in required_soft_skills:
            skill_name = (ss.get("name") or ss.get("skill") or (ss if isinstance(ss, str) else "")).strip()
            if not skill_name:
                continue

            # Try to match against our categories
            matched_category = None
            for cat in _SOFT_SKILL_PATTERNS:
                if cat.replace("_", " ") in skill_name.lower() or skill_name.lower() in cat.replace("_", " "):
                    matched_category = cat
                    break

            # Fallback: check if skill_name appears in candidate text
            if not matched_category:
                appeared = bool(re.search(re.escape(skill_name), candidate_text, re.IGNORECASE))
            else:
                appeared = category_scores[matched_category]["frequency"] > 0

            importance = (ss.get("importance") or "important").lower() if isinstance(ss, dict) else "important"
            level = category_scores[matched_category]["strength"] if matched_category else ("moderate" if appeared else "none")

            gap_severity = "minor"
            if level == "none" and "critical" in importance:
                gap_severity = "critical"
            elif level == "none":
                gap_severity = "major"
            elif level == "weak" and "critical" in importance:
                gap_severity = "moderate"

            soft_skill_assessment.append({
                "skill": skill_name,
                "detected_level": level,
                "importance": importance,
                "gap_severity": gap_severity,
                "recommendation": self._soft_skill_rec(skill_name, level, gap_severity),
            })

        # Overall soft skill score
        if soft_skill_assessment:
            has_skill = sum(1 for s in soft_skill_assessment if s["detected_level"] != "none")
            soft_score = int((has_skill / len(soft_skill_assessment)) * 100)
        else:
            # No explicit requirements — derive from detected signals
            detected_count = sum(1 for c in category_scores.values() if c["frequency"] > 0)
            soft_score = min(100, detected_count * 17)  # 6 categories → max ~102

        # ── Culture fit analysis ────────────────────────────────
        jd_culture: dict[str, bool] = {}
        candidate_culture: dict[str, bool] = {}
        for dimension, pattern in _CULTURE_PATTERNS.items():
            jd_culture[dimension] = bool(pattern.search(jd_text))
            candidate_culture[dimension] = bool(pattern.search(candidate_text))

        culture_alignment: list[dict] = []
        culture_mismatches: list[dict] = []
        for dim in _CULTURE_PATTERNS:
            if jd_culture[dim]:
                label = dim.replace("_", " ").title()
                if candidate_culture[dim]:
                    culture_alignment.append({"dimension": label, "status": "aligned"})
                else:
                    culture_mismatches.append({
                        "dimension": label,
                        "status": "gap",
                        "recommendation": f"The role emphasizes '{label}' — highlight any relevant experience or willingness to embrace this culture.",
                    })

        culture_total = sum(1 for v in jd_culture.values() if v)
        culture_matches = len(culture_alignment)
        culture_score = int((culture_matches / max(culture_total, 1)) * 100) if culture_total else 70

        # ── Overall ─────────────────────────────────────────────
        overall_score = int(soft_score * 0.6 + culture_score * 0.4)
        confidence = 0.5  # text-based heuristics, moderate confidence

        return SubAgentResult(
            agent_name=self.name,
            data={
                "soft_skill_score": soft_score,
                "culture_score": culture_score,
                "overall_score": overall_score,
                "soft_skills_assessment": soft_skill_assessment[:12],
                "category_signals": category_scores,
                "culture_alignment": culture_alignment,
                "culture_mismatches": culture_mismatches,
                "summary": self._build_summary(soft_score, culture_score, soft_skill_assessment, culture_mismatches),
            },
            confidence=confidence,
        )

    def _soft_skill_rec(self, skill: str, level: str, severity: str) -> str:
        if severity == "minor":
            return f"Good evidence of {skill} — continue demonstrating in applications."
        if level == "none":
            return f"No evidence of {skill} found. Add examples from past roles that demonstrate this ability."
        if level == "weak":
            return f"Limited evidence of {skill}. Strengthen by adding specific examples with measurable outcomes (STAR format)."
        return f"Moderate {skill} evidence. Quantify impact to make it more compelling."

    def _build_summary(self, soft_score: int, culture_score: int, assessment: list, mismatches: list) -> str:
        parts = [f"Soft skills match: {soft_score}%. Culture fit: {culture_score}%."]
        detected = sum(1 for s in assessment if s["detected_level"] != "none")
        if assessment:
            parts.append(f"{detected}/{len(assessment)} required soft skills detected in profile.")
        if mismatches:
            dims = ", ".join(m["dimension"] for m in mismatches[:3])
            parts.append(f"Culture gaps in: {dims}.")
        return " ".join(parts)
