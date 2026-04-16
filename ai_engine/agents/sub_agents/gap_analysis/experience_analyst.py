"""
ExperienceAnalyst — deep experience gap assessment.

Compares candidate's work experience against benchmark requirements:
  • Total years of experience
  • Domain/industry alignment
  • Leadership and management experience
  • Project complexity and scale
  • Role progression trajectory

Pure deterministic analysis — no LLM call.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

# Seniority level mapping for trajectory analysis
_SENIORITY_ORDER = {
    "intern": 0, "trainee": 0, "apprentice": 0,
    "junior": 1, "associate": 1, "entry": 1,
    "mid": 2, "developer": 2, "engineer": 2, "analyst": 2,
    "senior": 3, "sr": 3, "lead": 3,
    "staff": 4, "principal": 4, "architect": 4,
    "manager": 5, "director": 5, "head": 5, "vp": 6,
    "cto": 7, "cio": 7, "ceo": 7,
}

_LEADERSHIP_SIGNALS = re.compile(
    r"(?:led\s+(?:a\s+)?team|managed\s+\d+|mentored|coached|supervised|"
    r"hiring|onboard|cross.?functional|stakeholder\s+management|"
    r"team\s+lead|tech\s+lead|engineering\s+manager)", re.IGNORECASE,
)

_SCALE_SIGNALS = re.compile(
    r"(?:\d+[MBK]\+?\s*(?:users|requests|DAU|MAU|transactions)|"
    r"million|billion|enterprise|fortune\s*\d+|series\s*[A-D]|"
    r"global|multi.?region|distributed|high.?availability|"
    r"petabyte|terabyte|\d+\s*(?:servers|nodes|clusters))", re.IGNORECASE,
)


class ExperienceAnalyst(SubAgent):
    """Deterministic experience gap analysis."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="experience_analyst", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        user_profile = context.get("user_profile", {})
        benchmark = context.get("benchmark", {})

        experiences = user_profile.get("experience", [])
        ideal_profile = benchmark.get("ideal_profile", {})
        ideal_experience = benchmark.get("ideal_experience", [])

        # ── Total years ─────────────────────────────────────────
        total_years = self._compute_total_years(experiences)
        required_years = ideal_profile.get("years_experience", 0)
        if isinstance(required_years, str):
            try:
                required_years = float(re.search(r"(\d+\.?\d*)", required_years).group(1))
            except (AttributeError, ValueError):
                required_years = 3  # default

        years_gap = max(0, required_years - total_years)
        years_score = min(100, int((total_years / max(required_years, 1)) * 100))

        # ── Domain alignment ────────────────────────────────────
        required_domains = set()
        for exp in ideal_experience:
            domain = (exp.get("domain") or exp.get("area") or exp.get("industry") or "").lower()
            if domain:
                required_domains.add(domain)
        # Also extract from ideal_profile
        for domain_key in ["industry", "domain", "sector"]:
            d = (ideal_profile.get(domain_key) or "").lower()
            if d:
                required_domains.add(d)

        user_domains = set()
        domain_text_parts: list[str] = []
        for exp in experiences:
            for key in ["company", "industry", "description", "title"]:
                text = exp.get(key) or ""
                domain_text_parts.append(text)
                if key == "industry" and text:
                    user_domains.add(text.lower())
        domain_text = " ".join(domain_text_parts).lower()

        domain_matches = []
        domain_misses = []
        for rd in required_domains:
            if rd in domain_text:
                domain_matches.append(rd)
            else:
                domain_misses.append(rd)

        domain_score = int((len(domain_matches) / max(len(required_domains), 1)) * 100) if required_domains else 70

        # ── Leadership assessment ───────────────────────────────
        leadership_evidence: list[dict] = []
        for exp in experiences:
            desc = f"{exp.get('title', '')} {exp.get('description', '')}"
            if _LEADERSHIP_SIGNALS.search(desc):
                leadership_evidence.append({
                    "role": exp.get("title", "Unknown"),
                    "company": exp.get("company", "Unknown"),
                    "signal": _LEADERSHIP_SIGNALS.search(desc).group(0),
                })

        required_leadership = ideal_profile.get("leadership_required", False)
        if not isinstance(required_leadership, bool):
            required_leadership = str(required_leadership).lower() in ("true", "yes", "1")

        leadership_score = 100
        if required_leadership:
            leadership_score = min(100, len(leadership_evidence) * 35)  # Each evidence counts ~35%

        # ── Project scale & complexity ──────────────────────────
        scale_evidence: list[str] = []
        for exp in experiences:
            desc = f"{exp.get('title', '')} {exp.get('description', '')}"
            matches = _SCALE_SIGNALS.findall(desc)
            scale_evidence.extend(matches)

        for proj in user_profile.get("projects", []):
            desc = f"{proj.get('title', '')} {proj.get('description', '')}"
            matches = _SCALE_SIGNALS.findall(desc)
            scale_evidence.extend(matches)

        # ── Career trajectory ───────────────────────────────────
        trajectory = self._analyze_trajectory(experiences)

        # ── Build experience gaps ───────────────────────────────
        experience_gaps: list[dict] = []

        if years_gap > 0:
            severity = "critical" if years_gap >= 3 else ("major" if years_gap >= 1.5 else "moderate")
            experience_gaps.append({
                "area": "Total Years of Experience",
                "required": f"{required_years:.0f}+ years",
                "current": f"{total_years:.1f} years",
                "gap_severity": severity,
                "recommendation": self._years_recommendation(total_years, required_years),
                "alternatives": self._years_alternatives(total_years, required_years),
            })

        if domain_misses:
            severity = "major" if len(domain_misses) > len(domain_matches) else "moderate"
            experience_gaps.append({
                "area": "Domain/Industry Experience",
                "required": ", ".join(required_domains),
                "current": ", ".join(user_domains) if user_domains else "Not specified",
                "gap_severity": severity,
                "recommendation": f"Gain exposure to {', '.join(domain_misses[:3])} through projects, open-source, or freelance work.",
                "alternatives": [
                    "Contribute to open-source projects in the target domain",
                    "Build personal projects that demonstrate domain knowledge",
                    "Take industry-specific courses or certifications",
                ],
            })

        if required_leadership and not leadership_evidence:
            experience_gaps.append({
                "area": "Leadership Experience",
                "required": "Team leadership or management experience",
                "current": "No leadership evidence found",
                "gap_severity": "major",
                "recommendation": "Seek out leadership opportunities: lead a project, mentor junior devs, or organize a tech initiative.",
                "alternatives": [
                    "Volunteer to lead a sprint or project at current role",
                    "Mentor junior team members",
                    "Lead open-source project or community initiative",
                ],
            })

        # ── Overall score ───────────────────────────────────────
        weights = {"years": 0.35, "domain": 0.25, "leadership": 0.20, "trajectory": 0.20}
        experience_score = int(
            years_score * weights["years"]
            + domain_score * weights["domain"]
            + leadership_score * weights["leadership"]
            + trajectory["score"] * weights["trajectory"]
        )

        confidence = 0.7 if experiences else 0.3

        return SubAgentResult(
            agent_name=self.name,
            data={
                "experience_score": experience_score,
                "experience_gaps": experience_gaps[:6],
                "years_analysis": {
                    "total_years": round(total_years, 1),
                    "required_years": required_years,
                    "gap_years": round(years_gap, 1),
                    "score": years_score,
                },
                "domain_analysis": {
                    "matched_domains": domain_matches,
                    "missing_domains": domain_misses,
                    "score": domain_score,
                },
                "leadership_analysis": {
                    "required": required_leadership,
                    "evidence": leadership_evidence[:5],
                    "score": leadership_score,
                },
                "scale_evidence": scale_evidence[:10],
                "trajectory": trajectory,
                "summary": self._build_summary(experience_score, total_years, required_years, leadership_evidence, trajectory),
            },
            confidence=confidence,
        )

    def _compute_total_years(self, experiences: list[dict]) -> float:
        """Sum experience durations from profile."""
        total = 0.0
        for exp in experiences:
            dur = exp.get("duration", exp.get("years", ""))
            if isinstance(dur, (int, float)):
                total += float(dur)
                continue
            dur = str(dur).lower()
            year_match = re.search(r"(\d+\.?\d*)\s*year", dur)
            month_match = re.search(r"(\d+)\s*month", dur)
            if year_match:
                total += float(year_match.group(1))
            if month_match:
                total += float(month_match.group(1)) / 12
            # If no duration, try start/end dates
            if not year_match and not month_match:
                start = exp.get("start_date", "")
                end = exp.get("end_date", "")
                if start:
                    years = self._date_range_years(start, end)
                    if years > 0:
                        total += years
        return total

    def _date_range_years(self, start: str, end: str) -> float:
        """Estimate years between two date strings."""
        import re as _re
        year_re = _re.compile(r"(20\d{2}|19\d{2})")
        start_m = year_re.search(str(start))
        end_m = year_re.search(str(end)) if end and "present" not in str(end).lower() else None
        if start_m:
            start_year = int(start_m.group(1))
            end_year = int(end_m.group(1)) if end_m else 2026
            return max(0, end_year - start_year)
        return 0

    def _analyze_trajectory(self, experiences: list[dict]) -> dict:
        """Analyze career progression trajectory."""
        if not experiences:
            return {"pattern": "unknown", "score": 50, "detail": "No experience data available"}

        levels: list[int] = []
        for exp in experiences:
            title = (exp.get("title") or "").lower()
            best_level = 2  # default mid
            for keyword, level in _SENIORITY_ORDER.items():
                if keyword in title:
                    best_level = max(best_level, level)
            levels.append(best_level)

        if len(levels) < 2:
            return {
                "pattern": "single_role",
                "score": 60,
                "detail": "Single role — trajectory not assessable",
            }

        # Are levels generally increasing?
        increasing = sum(1 for i in range(1, len(levels)) if levels[i] >= levels[i - 1])
        ratio = increasing / (len(levels) - 1)

        if ratio >= 0.8 and levels[-1] > levels[0]:
            return {"pattern": "strong_progression", "score": 90, "detail": "Clear upward career progression"}
        if ratio >= 0.5:
            return {"pattern": "moderate_progression", "score": 70, "detail": "Moderate career progression with some lateral moves"}
        return {"pattern": "lateral_or_mixed", "score": 50, "detail": "Lateral moves or non-linear progression"}

    def _years_recommendation(self, current: float, required: float) -> str:
        gap = required - current
        if gap <= 1:
            return "Slightly below requirement — emphasize project complexity and breadth of experience to compensate."
        if gap <= 3:
            return "Moderate experience gap — highlight transferable skills, side projects, and accelerated learning to bridge the difference."
        return "Significant experience gap — consider targeting a stepping-stone role first, or demonstrate exceptional depth through projects and certifications."

    def _years_alternatives(self, current: float, required: float) -> list[str]:
        alts = ["Highlight relevant freelance, open-source, or side project experience"]
        if required - current > 2:
            alts.append("Consider applying for one level below to build experience")
        alts.append("Emphasize rate of learning and impact per year over raw years")
        alts.append("Get referrals to bypass automated experience filters")
        return alts

    def _build_summary(self, score: int, years: float, req_years: float, leadership: list, trajectory: dict) -> str:
        parts = [f"Experience match: {score}%."]
        if years >= req_years:
            parts.append(f"Meets experience requirement ({years:.0f}y vs {req_years:.0f}y needed).")
        else:
            parts.append(f"Experience gap: {years:.1f}y vs {req_years:.0f}y required.")
        if leadership:
            parts.append(f"{len(leadership)} leadership signal(s) detected.")
        parts.append(f"Trajectory: {trajectory['pattern'].replace('_', ' ')}.")
        return " ".join(parts)
