"""
Daily Briefing Chain
Generates a personalized AI career insight based on the user's application data.
"""
from typing import Dict, Any


BRIEFING_SYSTEM = """You are a career intelligence AI. Generate a brief, actionable daily career insight.
Be specific — reference actual skills, companies, and numbers from the data provided.
Write in second person ("Your..."). Keep it under 2 sentences. Be encouraging but honest.
Return ONLY valid JSON."""

BRIEFING_PROMPT = """Generate a daily career insight for this professional.

PROFILE: {name}, {title}
TOTAL APPLICATIONS: {app_count}
AVG MATCH SCORE: {avg_match}%
TOP SKILLS: {top_skills}
OPEN TASKS: {open_tasks}
EVIDENCE ITEMS: {evidence_count}
RECENT ACTIVITY: {recent_activity}

Return JSON:
{{
  "insight": "Your personalized insight (1-2 sentences, specific and actionable)",
  "category": "skills|applications|market|growth|momentum",
  "action_label": "Short CTA button text (3-5 words)",
  "action_href": "/path-to-relevant-page"
}}"""


class DailyBriefingChain:
    """Generates AI-powered daily career insights."""

    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def generate(self, profile_data: Dict[str, Any], app_stats: Dict[str, Any]) -> Dict[str, Any]:
        skills = profile_data.get("skills") or []
        top_skills = ", ".join(
            s.get("name", "") for s in skills[:8] if isinstance(s, dict)
        ) or "Not specified"

        prompt = BRIEFING_PROMPT.format(
            name=profile_data.get("name") or "User",
            title=profile_data.get("title") or "Professional",
            app_count=app_stats.get("app_count", 0),
            avg_match=app_stats.get("avg_match", 0),
            top_skills=top_skills,
            open_tasks=app_stats.get("open_tasks", 0),
            evidence_count=app_stats.get("evidence_count", 0),
            recent_activity=app_stats.get("recent_activity", "No recent activity"),
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=BRIEFING_SYSTEM,
            max_tokens=500,
            temperature=0.7,
            task_type="creative",
        )

        result.setdefault("insight", "Keep building your career portfolio — every application makes your profile stronger.")
        result.setdefault("category", "growth")
        result.setdefault("action_label", "View Career Nexus")
        result.setdefault("action_href", "/nexus")

        return result
