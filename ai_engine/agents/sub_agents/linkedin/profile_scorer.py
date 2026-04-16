"""
ProfileScorer — deterministic Phase 1 agent.

Scores the current profile's completeness and identifies structural gaps:
  - headline quality (job-title-only vs keyword-rich)
  - summary presence and length
  - skills count and categorisation
  - experience detail level (achievements, metrics)
  - certifications, education presence

No LLM call — pure heuristic.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult

_MAX_SCORE = 100


class ProfileScorer(SubAgent):
    """Scores a LinkedIn-ready profile for completeness."""

    def __init__(self, ai_client=None):
        super().__init__(name="profile_scorer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        profile: dict = context.get("profile_data", {})

        score = 0
        tips: list[str] = []

        # ── Headline (15 pts) ─────────────────────────────
        title = (profile.get("title") or "").strip()
        summary = (profile.get("summary") or "").strip()
        if title:
            score += 5
            if len(title) > 30 and "|" in title or "—" in title or "•" in title:
                score += 10  # keyword-rich headline
            else:
                tips.append("Upgrade headline: include value proposition + key skill, not just job title")
        else:
            tips.append("Add a headline with your role + specialty + value proposition")

        # ── Summary / About (20 pts) ─────────────────────
        if summary:
            words = len(summary.split())
            if words >= 150:
                score += 20
            elif words >= 50:
                score += 12
                tips.append("Expand your About section to 150-300 words with a compelling hook")
            else:
                score += 5
                tips.append("Your summary is too brief — aim for at least 150 words")
        else:
            tips.append("Add an About section — it's prime keyword real estate")

        # ── Skills (20 pts) ──────────────────────────────
        skills: list[dict] = profile.get("skills") or []
        n_skills = len(skills)
        if n_skills >= 15:
            score += 20
        elif n_skills >= 8:
            score += 14
            tips.append(f"Add {15 - n_skills} more skills — 15+ helps discoverability")
        elif n_skills >= 3:
            score += 8
            tips.append("Add more skills — target at least 15 for full profile strength")
        elif n_skills > 0:
            score += 3
            tips.append("You have very few skills listed — add 15+ relevant skills")
        else:
            tips.append("No skills listed — this hurts search visibility significantly")

        # ── Experience (25 pts) ──────────────────────────
        experience: list[dict] = profile.get("experience") or []
        if experience:
            has_achievements = any(e.get("achievements") for e in experience if isinstance(e, dict))
            if has_achievements:
                score += 25
            else:
                score += 10
                tips.append("Add achievement bullets to your experience entries — quantify impact")
        else:
            tips.append("Add at least your current role to the experience section")

        # ── Education (10 pts) ───────────────────────────
        education: list[dict] = profile.get("education") or []
        if education:
            score += 10
        else:
            tips.append("Add education — even bootcamps / online degrees count")

        # ── Certifications (10 pts bonus) ────────────────
        certs: list[dict] = profile.get("certifications") or []
        if certs:
            score += min(10, len(certs) * 3)
        else:
            tips.append("Add certifications — they boost credibility and search ranking")

        score = min(score, _MAX_SCORE)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "overall_score": score,
                "headline_present": bool(title),
                "summary_word_count": len(summary.split()) if summary else 0,
                "skills_count": n_skills,
                "experience_count": len(experience),
                "has_achievements": any(
                    e.get("achievements") for e in experience if isinstance(e, dict)
                ),
                "certifications_count": len(certs),
                "completeness_tips": tips[:8],
            },
            confidence=0.90,
        )
