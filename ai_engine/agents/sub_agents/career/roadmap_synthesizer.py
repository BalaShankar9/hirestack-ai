"""
RoadmapSynthesizer — Phase 2 LLM agent for the Career Consultant swarm.

Receives pre-computed Phase 1 outputs (prioritised skills, milestones,
quick wins, project ideas) and synthesises a polished, human-quality
career roadmap.  The LLM focuses purely on narrative quality, learning
resource suggestions, motivation tips, and connecting the dots — all
heavy-lifting analysis was already done deterministically.

Produces output matching CareerConsultantChain's ROADMAP_SCHEMA so the
coordinator can return a drop-in replacement for the legacy single-shot.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

_SYNTHESIS_SYSTEM = (
    "You are a world-class career coach. You receive pre-computed analysis "
    "(skill priorities, milestones, quick wins, project ideas) and your job "
    "is to weave them into a polished, motivating, and realistic 12-week "
    "career roadmap.  Be specific with resource suggestions, keep strings "
    "single-line, and return MINIFIED JSON only."
)

_SYNTHESIS_PROMPT = """\
Synthesise a career improvement roadmap from the pre-computed analysis below.

TARGET ROLE: {job_title} at {company}
USER PROFILE (summary): {profile_summary}

── PRIORITISED SKILLS ──
{prioritised_skills}

── MILESTONE SCHEDULE ──
{milestones}

── QUICK WINS ──
{quick_wins}

── PROJECT IDEAS ──
{projects}

── INSTRUCTIONS ──
Using the above analysis, produce the final roadmap JSON.

1. **roadmap.title** — personalised for the candidate
2. **roadmap.overview** — 2-3 sentence executive summary
3. **roadmap.total_duration** — use the milestone schedule total
4. **roadmap.expected_outcome** — concrete outcome statement
5. **roadmap.milestones** — refine the milestone schedule above into max 6 polished milestones (keep week numbers, add vivid descriptions and 2-4 tasks each)
6. **roadmap.skill_development** — max 5 entries from the prioritised skills; for each add specific `resources` (course/book names) and `practice_projects`
7. **roadmap.project_recommendations** — max 3, taken from the project ideas above
8. **learning_resources** — max 6; include real course/book titles, types, providers, and priorities
9. **quick_wins** — max 8 strings (from the quick wins above, polished)
10. **motivation_tips** — max 8 strings; practical and encouraging
11. **tools_recommended** — 4-8 tools/platforms relevant to the skill gaps
12. **common_pitfalls** — 4-6 common mistakes to avoid during the transition

Return ONLY valid minified JSON matching the schema.  No markdown, no code fences.\
"""

# Matches CareerConsultantChain.ROADMAP_SCHEMA exactly
_ROADMAP_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "roadmap": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "overview": {"type": "STRING"},
                "total_duration": {"type": "STRING"},
                "expected_outcome": {"type": "STRING"},
                "milestones": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "week": {"type": "INTEGER"},
                            "title": {"type": "STRING"},
                            "description": {"type": "STRING"},
                            "tasks": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "skills_gained": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    },
                },
                "skill_development": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "skill": {"type": "STRING"},
                            "current_level": {"type": "STRING"},
                            "target_level": {"type": "STRING"},
                            "timeline": {"type": "STRING"},
                            "resources": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "practice_projects": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    },
                },
                "project_recommendations": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "title": {"type": "STRING"},
                            "description": {"type": "STRING"},
                            "skills_demonstrated": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "timeline": {"type": "STRING"},
                        },
                    },
                },
            },
        },
        "learning_resources": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "type": {"type": "STRING"},
                    "provider": {"type": "STRING"},
                    "skill_covered": {"type": "STRING"},
                    "priority": {"type": "STRING"},
                },
            },
        },
        "quick_wins": {"type": "ARRAY", "items": {"type": "STRING"}},
        "motivation_tips": {"type": "ARRAY", "items": {"type": "STRING"}},
        "tools_recommended": {"type": "ARRAY", "items": {"type": "STRING"}},
        "common_pitfalls": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["roadmap"],
}


class RoadmapSynthesizer(SubAgent):
    """LLM agent that merges Phase 1 outputs into a polished career roadmap."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="roadmap_synthesizer", ai_client=ai_client)

    # ── helpers ──────────────────────────────────────────────────
    @staticmethod
    def _profile_summary(profile: dict) -> str:
        """One-paragraph profile digest to keep the prompt short."""
        name = profile.get("name", "Candidate")
        headline = profile.get("headline", "")
        yrs = profile.get("years_experience", "?")
        skills = ", ".join((profile.get("skills") or [])[:10])
        return f"{name} — {headline}. {yrs} yrs experience. Top skills: {skills}."

    @staticmethod
    def _truncate_json(obj: Any, limit: int = 2500) -> str:
        raw = json.dumps(obj, default=str)
        return raw[:limit]

    # ── main run ────────────────────────────────────────────────
    async def run(self, context: dict) -> SubAgentResult:
        if not self.ai_client:
            return SubAgentResult(
                agent_name=self.name,
                data={},
                confidence=0.0,
                error="ai_client required for RoadmapSynthesizer",
            )

        job_title = context.get("job_title", "Target Role")
        company = context.get("company", "Target Company")
        profile = context.get("user_profile", {})

        # Phase 1 outputs (injected by coordinator)
        phase1 = context.get("phase1_results", {})
        prioritised = phase1.get("skill_prioritizer", {})
        milestones = phase1.get("milestone_scheduler", {})
        quick_wins = phase1.get("quick_win_extractor", {})
        projects = phase1.get("project_idea_generator", {})

        prompt = _SYNTHESIS_PROMPT.format(
            job_title=job_title,
            company=company,
            profile_summary=self._profile_summary(profile),
            prioritised_skills=self._truncate_json(prioritised),
            milestones=self._truncate_json(milestones),
            quick_wins=self._truncate_json(quick_wins),
            projects=self._truncate_json(projects),
        )

        try:
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=_SYNTHESIS_SYSTEM,
                temperature=0.25,
                max_tokens=6000,
                schema=_ROADMAP_SCHEMA,
            )
        except Exception as exc:
            logger.warning("RoadmapSynthesizer LLM call failed: %s", exc)
            return SubAgentResult(
                agent_name=self.name,
                data={},
                confidence=0.0,
                error=str(exc),
            )

        # ── Ensure required top-level keys exist ────────────────
        defaults = {
            "roadmap": {},
            "learning_resources": [],
            "quick_wins": [],
            "motivation_tips": [],
            "tools_recommended": [],
            "common_pitfalls": [],
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default

        return SubAgentResult(
            agent_name=self.name,
            data=result,
            confidence=0.85,
        )
