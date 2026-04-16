"""
PrepTipGenerator — deterministic Phase 1 agent.

Generates interview preparation tips based on interview type, role level,
and company context.  No LLM call — rule-based template selection.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


_BASE_TIPS: list[str] = [
    "Research the company's recent news, product launches, and press coverage.",
    "Prepare 3-5 thoughtful questions for the interviewer.",
    "Practice the STAR method (Situation, Task, Action, Result) for behavioral answers.",
    "Prepare a concise 90-second self-introduction.",
    "Test your video/audio setup if the interview is remote.",
]

_TYPE_TIPS: dict[str, list[str]] = {
    "technical": [
        "Review core data structures and algorithms relevant to the role.",
        "Practice coding problems in a shared editor (not your IDE).",
        "Be ready to discuss time/space complexity trade-offs.",
        "Prepare to walk through a system design for a familiar product.",
    ],
    "behavioral": [
        "Prepare specific stories for: conflict resolution, failure, leadership, teamwork.",
        "Quantify your impact in each story — numbers make answers memorable.",
        "Practice transitioning smoothly between stories.",
        "Show self-awareness when discussing mistakes.",
    ],
    "mixed": [
        "Expect to switch between coding and behavioral — practice transitions.",
        "Keep technical explanations accessible for non-technical interviewers.",
        "Balance depth (technical) with breadth (leadership, communication).",
    ],
    "case_study": [
        "Practice structuring ambiguous problems before solving them.",
        "Use frameworks (MECE, Porter's Five Forces) but adapt them to the situation.",
        "Think aloud — the interviewer cares about your reasoning process.",
    ],
    "executive": [
        "Prepare vision statements for where the team/org should go.",
        "Have metrics showing your leadership impact.",
        "Be ready to discuss strategy under budget and time constraints.",
    ],
}

_SENIORITY_TIPS: dict[str, list[str]] = {
    "junior": [
        "Emphasise learning speed and curiosity over existing expertise.",
        "Prepare examples of side projects, coursework, or open-source contributions.",
    ],
    "mid": [
        "Show ownership — interviewers want to see independent problem-solving.",
        "Prepare examples of cross-team collaboration.",
    ],
    "senior": [
        "Demonstrate technical leadership — mentoring, architecture decisions.",
        "Show you can break down ambiguous problems into actionable plans.",
    ],
    "staff": [
        "Lead with impact — how your decisions affected the entire organisation.",
        "Discuss trade-offs you've navigated at the organisational level.",
    ],
}


class PrepTipGenerator(SubAgent):
    """Generates interview preparation tips based on context."""

    def __init__(self, ai_client=None):
        super().__init__(name="prep_tip_generator", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        interview_type: str = context.get("interview_type", "mixed")
        company: str = context.get("company", "")
        seniority: str = context.get("_seniority", "mid")

        tips: list[str] = list(_BASE_TIPS)

        # Type-specific tips
        type_tips = _TYPE_TIPS.get(interview_type, _TYPE_TIPS["mixed"])
        tips.extend(type_tips)

        # Seniority-specific tips
        level_tips = _SENIORITY_TIPS.get(seniority, _SENIORITY_TIPS["mid"])
        tips.extend(level_tips)

        # Company-specific tip
        if company and company.lower() not in ("the company", ""):
            tips.insert(0, f"Research {company}'s mission, culture, and recent developments.")

        # Deduplicate and cap
        seen: set[str] = set()
        unique_tips: list[str] = []
        for t in tips:
            if t not in seen:
                seen.add(t)
                unique_tips.append(t)
        unique_tips = unique_tips[:12]

        return SubAgentResult(
            agent_name=self.name,
            data={
                "preparation_tips": unique_tips,
                "tip_count": len(unique_tips),
                "interview_type": interview_type,
                "seniority": seniority,
            },
            confidence=0.90,
        )
