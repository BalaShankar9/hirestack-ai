"""
StrengthMapper — identifies competitive advantages and leverage strategies.

Finds what the candidate does BETTER than the benchmark expects, or
unique differentiators that can compensate for gaps elsewhere:
  • Over-qualified skills (above required level)
  • Unique technology combinations
  • Industry/domain crossover advantages
  • Rare certifications or achievements
  • Project portfolio strengths

Pure deterministic analysis — no LLM call.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

# Patterns that indicate exceptional achievements
_ACHIEVEMENT_PATTERNS = re.compile(
    r"(?:award|patent|publish|peer.?review|keynote|speaker|"
    r"open.?source\s+(?:maintainer|creator|author)|"
    r"top\s*\d+%|first\s+(?:place|prize)|"
    r"grew\s+(?:revenue|team|user)|"
    r"reduced?\s+(?:cost|latency|downtime)|"
    r"increased?\s+(?:revenue|performance|uptime)|"
    r"\d+x\s+(?:improvement|faster|better)|"
    r"from\s+\d+\s+to\s+\d+|"
    r"saved?\s+\$?\d+[KkMm]?\+?)",
    re.IGNORECASE,
)

_LEVEL_INDEX = {"none": 0, "beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}


class StrengthMapper(SubAgent):
    """Identifies competitive advantages and leverage strategies."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="strength_mapper", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        user_profile = context.get("user_profile", {})
        benchmark = context.get("benchmark", {})

        strengths: list[dict] = []
        quick_wins: list[str] = []

        # ── 1. Over-qualified skills ────────────────────────────
        user_skills = {
            (s.get("name") or s.get("skill") or "").lower(): s
            for s in user_profile.get("skills", [])
            if s.get("name") or s.get("skill")
        }
        ideal_skills = benchmark.get("ideal_skills", [])

        for ideal in ideal_skills:
            name = (ideal.get("name") or ideal.get("skill") or "").strip()
            if not name:
                continue
            user_s = user_skills.get(name.lower())
            if not user_s:
                continue

            req_level = self._normalize_level(ideal.get("level") or ideal.get("required_level") or "intermediate")
            cur_level = self._normalize_level(user_s.get("level") or user_s.get("proficiency") or "intermediate")

            if _LEVEL_INDEX.get(cur_level, 0) > _LEVEL_INDEX.get(req_level, 0):
                strengths.append({
                    "area": name,
                    "description": f"Exceeds requirement: {cur_level} vs {req_level} required",
                    "competitive_advantage": f"Deep {name} expertise can compensate for gaps elsewhere and add immediate value.",
                    "how_to_leverage": f"Emphasize {name} mastery in CV/cover letter — position as go-to expert on the team.",
                })

        # ── 2. Extra skills not in benchmark ────────────────────
        ideal_skill_names = set(
            (s.get("name") or s.get("skill") or "").lower()
            for s in ideal_skills
        )
        bonus_skills = []
        for skill_key, skill_data in user_skills.items():
            if skill_key not in ideal_skill_names:
                level = self._normalize_level(skill_data.get("level") or skill_data.get("proficiency") or "intermediate")
                if _LEVEL_INDEX.get(level, 0) >= 3:  # advanced or expert
                    bonus_skills.append(skill_data.get("name") or skill_data.get("skill") or skill_key)

        if bonus_skills:
            strengths.append({
                "area": "Bonus Technical Skills",
                "description": f"Advanced+ skills not required but valuable: {', '.join(bonus_skills[:5])}",
                "competitive_advantage": "Brings additional capabilities the team may not expect — can expand role scope.",
                "how_to_leverage": "Mention briefly in CV summary or cover letter as value-adds beyond core requirements.",
            })

        # ── 3. Achievement-based strengths ──────────────────────
        exp_text_parts = []
        for exp in user_profile.get("experience", []):
            exp_text_parts.append(f"{exp.get('title', '')} {exp.get('description', '')}")
        for proj in user_profile.get("projects", []):
            exp_text_parts.append(f"{proj.get('title', '')} {proj.get('description', '')}")
        full_text = " ".join(exp_text_parts)

        achievements = _ACHIEVEMENT_PATTERNS.findall(full_text)
        if achievements:
            strengths.append({
                "area": "Quantified Achievements",
                "description": f"{len(achievements)} measurable achievement(s) detected in profile",
                "competitive_advantage": "Concrete metrics differentiate from candidates who only list responsibilities.",
                "how_to_leverage": "Lead with metrics in CV bullet points — quantified impact is the #1 differentiator for hiring managers.",
            })
            quick_wins.append("Ensure all CV bullet points start with action verbs and include quantified results")

        # ── 4. Project portfolio ────────────────────────────────
        projects = user_profile.get("projects", [])
        if len(projects) >= 3:
            strengths.append({
                "area": "Strong Project Portfolio",
                "description": f"{len(projects)} projects demonstrate hands-on building experience",
                "competitive_advantage": "Active builder profile signals initiative and practical ability beyond job duties.",
                "how_to_leverage": "Include top 2-3 projects in CV with links. Reference in cover letter as proof of capability.",
            })
            quick_wins.append("Add live links/GitHub repos to your top projects")

        # ── 5. Education strengths ──────────────────────────────
        education = user_profile.get("education", [])
        for edu in education:
            degree = (edu.get("degree") or "").lower()
            institution = edu.get("institution") or edu.get("school") or ""
            gpa = edu.get("gpa") or edu.get("grade") or ""
            honours = any(kw in degree for kw in ["first class", "summa", "magna", "cum laude", "distinction", "honours", "honors"])

            if honours or (gpa and self._gpa_is_strong(gpa)):
                strengths.append({
                    "area": "Academic Excellence",
                    "description": f"Strong academic record: {edu.get('degree', 'Degree')} from {institution}",
                    "competitive_advantage": "Demonstrates strong analytical ability and discipline — valued by employers.",
                    "how_to_leverage": "Include GPA/honours prominently if within last 5 years of graduation.",
                })
                break

        # ── 6. Certification strengths ──────────────────────────
        certs = user_profile.get("certifications", [])
        if len(certs) >= 3:
            cert_names = [c.get("name") or c.get("title") or (c if isinstance(c, str) else "") for c in certs[:5]]
            strengths.append({
                "area": "Strong Certification Profile",
                "description": f"{len(certs)} certifications: {', '.join(n for n in cert_names if n)}",
                "competitive_advantage": "Demonstrates commitment to continuous learning and validated expertise.",
                "how_to_leverage": "List relevant certs prominently — many ATS systems specifically scan for certifications.",
            })

        # ── Quick wins ──────────────────────────────────────────
        if not achievements:
            quick_wins.append("Add quantified metrics to your top 5 bullet points (%, $, time saved, users impacted)")
        if not projects:
            quick_wins.append("Add 2-3 personal/side projects to demonstrate initiative and hands-on skills")

        summary = user_profile.get("summary") or ""
        if len(summary) < 50:
            quick_wins.append("Write a compelling 2-3 sentence professional summary tailored to the target role")

        quick_wins.append("Tailor your CV summary to mirror keywords from the job description")
        quick_wins.append("Get a referral from someone at the company if possible — referrals have 5-10x higher conversion rates")

        confidence = min(0.8, 0.3 + 0.1 * len(strengths))

        return SubAgentResult(
            agent_name=self.name,
            data={
                "strengths": strengths[:8],
                "quick_wins": quick_wins[:8],
                "achievement_count": len(achievements),
                "bonus_skill_count": len(bonus_skills),
                "summary": self._build_summary(strengths, quick_wins),
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
        if "beginner" in level or "basic" in level:
            return "beginner"
        return "intermediate"

    def _gpa_is_strong(self, gpa: Any) -> bool:
        """Check if GPA indicates strong academic performance."""
        gpa_str = str(gpa).strip()
        try:
            val = float(re.search(r"(\d+\.?\d*)", gpa_str).group(1))
            # 4.0 scale
            if val <= 4.0 and val >= 3.5:
                return True
            # Percentage scale
            if val > 4.0 and val >= 70:
                return True
        except (AttributeError, ValueError):
            pass
        return False

    def _build_summary(self, strengths: list, quick_wins: list) -> str:
        if not strengths:
            return "No clear competitive advantages identified yet. Focus on quick wins to strengthen profile."
        areas = ", ".join(s["area"] for s in strengths[:4])
        return f"{len(strengths)} competitive advantage(s) found: {areas}. {len(quick_wins)} quick win(s) recommended."
