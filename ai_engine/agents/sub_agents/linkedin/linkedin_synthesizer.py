"""
LinkedInSynthesizer — Phase 2 LLM agent.

Receives structured context from the four Phase 1 agents and generates
headline suggestions, summary rewrite, skills-to-add, experience
improvements, and priority actions.
"""
from __future__ import annotations

from typing import Any

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult

SYNTHESIS_SYSTEM = """You are a world-class LinkedIn optimization expert.
Generate specific, actionable LinkedIn profile improvements.
Return ONLY valid JSON."""

SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "headline_suggestions": {"type": "ARRAY", "items": {"type": "STRING"}},
        "summary_rewrite": {"type": "STRING"},
        "skills_to_add": {"type": "ARRAY", "items": {"type": "STRING"}},
        "experience_improvements": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "role": {"type": "STRING"},
                    "current_style": {"type": "STRING"},
                    "linkedin_suggestion": {"type": "STRING"},
                },
            },
        },
        "priority_actions": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "headline_suggestions",
        "summary_rewrite",
        "skills_to_add",
        "experience_improvements",
        "priority_actions",
    ],
}


class LinkedInSynthesizer(SubAgent):
    """LLM-backed synthesizer for LinkedIn profile optimisation output."""

    def __init__(self, ai_client=None):
        super().__init__(name="linkedin_synthesizer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        phase1: dict[str, dict] = context.get("phase1_results", {})
        profile: dict = context.get("profile_data", {})

        scorer = phase1.get("profile_scorer", {})
        gaps = phase1.get("skill_gap_finder", {})
        critic = phase1.get("experience_critic", {})
        keywords = phase1.get("keyword_extractor", {})

        prompt = self._build_prompt(profile, scorer, gaps, critic, keywords)

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=SYNTHESIS_SYSTEM,
            temperature=0.55,
            max_tokens=4000,
            schema=SYNTHESIS_SCHEMA,
            task_type="reasoning",
        )

        return SubAgentResult(
            agent_name=self.name,
            data=result,
            confidence=0.85,
        )

    @staticmethod
    def _build_prompt(
        profile: dict,
        scorer: dict,
        gaps: dict,
        critic: dict,
        keywords: dict,
    ) -> str:
        name = profile.get("name", "Unknown")
        title = profile.get("title", "Professional")
        summary = (profile.get("summary") or "")[:400]

        skills_list = ", ".join(
            s.get("name", "")
            for s in (profile.get("skills") or [])[:15]
            if isinstance(s, dict)
        ) or "None listed"

        lines: list[str] = [
            f"Optimize the LinkedIn profile for {name}, currently '{title}'.",
            f"\nCURRENT SUMMARY ({scorer.get('summary_word_count', 0)} words):\n{summary[:300]}",
            f"\nCURRENT SKILLS: {skills_list}",
            f"PROFILE SCORE: {scorer.get('overall_score', 0)}/100",
        ]

        tips = scorer.get("completeness_tips", [])
        if tips:
            lines.append(f"GAPS: {'; '.join(tips[:5])}")

        missing_skills = gaps.get("missing_high_demand_skills", [])
        if missing_skills:
            lines.append(f"\nMISSING HIGH-DEMAND SKILLS ({gaps.get('role_category', 'general')}): {', '.join(missing_skills[:8])}")

        critiques = critic.get("experience_critiques", [])
        if critiques:
            lines.append("\nEXPERIENCE CRITIQUE:")
            for c in critiques[:4]:
                lines.append(f"  {c.get('role', '?')} — score {c.get('score', 0)}/100, issues: {'; '.join(c.get('issues', []))}")

        missing_kw = keywords.get("missing_keywords", [])
        if missing_kw:
            lines.append(f"\nMISSING KEYWORDS: {', '.join(missing_kw[:10])}")

        lines.extend([
            "\nGenerate:",
            "  - 3 headline_suggestions (under 120 chars each, keyword-rich)",
            "  - summary_rewrite (300-500 words, first-person, hook + story + CTA)",
            "  - 8-12 skills_to_add",
            "  - experience_improvements for each role listed",
            "  - Top 3 priority_actions",
            "\nReturn ONLY valid MINIFIED JSON.",
        ])

        return "\n".join(lines)
