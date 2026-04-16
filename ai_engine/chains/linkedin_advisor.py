"""
LinkedIn Profile Advisor Chain
Analyzes resume data and generates specific LinkedIn profile improvement suggestions.
"""
from typing import Dict, Any


LINKEDIN_ADVISOR_SYSTEM = """You are a world-class LinkedIn optimization expert with 15 years of experience
helping professionals across all industries maximize their LinkedIn presence.

Your analysis is based on the user's resume data. You identify gaps between their
resume content and what makes an exceptional LinkedIn profile.

Key areas to analyze:
1. HEADLINE — The 120-character tagline that appears under their name
2. ABOUT/SUMMARY — The 2,600-character narrative that tells their career story
3. SKILLS — The top skills that should be showcased and endorsed
4. EXPERIENCE — How to rephrase achievements for LinkedIn's social format
5. OVERALL PROFILE — Completeness tips and priority actions

LinkedIn best practices:
- Headlines should include role + value proposition + key skill (NOT just job title)
- About sections should start with a hook, tell a story, include keywords
- Skills should match industry demand and be specific (not vague)
- Experience bullets should quantify impact and use active voice
- Recommendations, certifications, and featured sections matter

Return ONLY valid JSON. No markdown, no code fences, just pure JSON."""

LINKEDIN_ADVISOR_PROMPT = """Analyze this professional's resume data and provide specific LinkedIn profile optimization advice.

NAME: {name}
CURRENT TITLE: {title}
SUMMARY: {summary}
LOCATION: {location}

SKILLS ({skill_count} total):
{skills}

EXPERIENCE:
{experience}

EDUCATION:
{education}

CERTIFICATIONS:
{certifications}

Return a JSON object with exactly these fields:
{{
  "headline_suggestions": ["3 optimized LinkedIn headlines — each under 120 chars, keyword-rich, value-oriented"],
  "summary_rewrite": "A complete LinkedIn About section (300-500 words). First-person, starts with a compelling hook, weaves in key skills naturally, ends with a call-to-action. Use line breaks for readability.",
  "skills_to_add": ["8-12 specific skills that should be on their LinkedIn based on their resume — include both technical and soft skills that are in demand"],
  "experience_improvements": [
    {{
      "role": "Job Title at Company",
      "current_style": "Brief note on how the resume describes it",
      "linkedin_suggestion": "How to rephrase for LinkedIn — more narrative, social-proof oriented, with metrics"
    }}
  ],
  "profile_completeness_tips": ["5-7 actionable tips to improve their LinkedIn profile beyond content — cover photo, featured section, recommendations, activity, groups"],
  "overall_score": 65,
  "priority_actions": ["Top 3 highest-impact actions to take RIGHT NOW, in priority order"]
}}"""


class LinkedInAdvisorChain:
    """Generates LinkedIn profile optimization advice based on resume data.

    v2.0.0 — delegates to LinkedInCoordinator (5-agent swarm)
    with automatic fallback to legacy single-LLM.
    """

    VERSION = "2.0.0"

    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def analyze(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze profile and return LinkedIn improvement suggestions via sub-agent swarm."""
        import logging

        logger = logging.getLogger(__name__)

        try:
            from ai_engine.agents.sub_agents.linkedin.coordinator import LinkedInCoordinator

            coordinator = LinkedInCoordinator(ai_client=self.ai_client)
            result = await coordinator.analyze(profile_data=profile_data)
            logger.info("linkedin_v2_ok", diagnostics=result.get("_diagnostics"))
            return self._validate_result(result)

        except Exception as exc:
            logger.warning("linkedin_v2_fallback reason=%s", exc)
            return await self._legacy_analyze(profile_data)

    async def _legacy_analyze(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy single-LLM LinkedIn advisor (v1 fallback)."""
        skills = profile_data.get("skills") or []
        experience = profile_data.get("experience") or []
        education = profile_data.get("education") or []
        certs = profile_data.get("certifications") or []
        contact = profile_data.get("contact_info") or {}

        # Format skills concisely
        skills_text = "\n".join(
            f"- {s['name']} ({s.get('level', 'intermediate')}, {s.get('years', '?')}y, {s.get('category', 'general')})"
            for s in skills[:30]
            if isinstance(s, dict)
        ) or "None listed"

        # Format experience
        exp_text = "\n".join(
            f"- {e.get('title', '?')} at {e.get('company', '?')} ({e.get('start_date', '?')} – {e.get('end_date', 'Present')})\n"
            f"  Achievements: {'; '.join((e.get('achievements') or [])[:3])}"
            for e in experience[:5]
            if isinstance(e, dict)
        ) or "None listed"

        # Format education
        edu_text = "\n".join(
            f"- {e.get('degree', '?')} in {e.get('field', '?')} from {e.get('institution', '?')}"
            for e in education[:3]
            if isinstance(e, dict)
        ) or "None listed"

        # Format certs
        cert_text = "\n".join(
            f"- {c.get('name', '?')} ({c.get('issuer', '?')})"
            for c in certs[:5]
            if isinstance(c, dict)
        ) or "None listed"

        prompt = LINKEDIN_ADVISOR_PROMPT.format(
            name=profile_data.get("name") or "Unknown",
            title=profile_data.get("title") or "Not specified",
            summary=(profile_data.get("summary") or "No summary provided")[:500],
            location=contact.get("location") or "Not specified",
            skill_count=len(skills),
            skills=skills_text,
            experience=exp_text,
            education=edu_text,
            certifications=cert_text,
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=LINKEDIN_ADVISOR_SYSTEM,
            max_tokens=4000,
            temperature=0.6,
            task_type="reasoning",
        )

        return self._validate_result(result)

    @staticmethod
    def _validate_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate expected fields."""
        result.setdefault("headline_suggestions", [])
        result.setdefault("summary_rewrite", "")
        result.setdefault("skills_to_add", [])
        result.setdefault("experience_improvements", [])
        result.setdefault("profile_completeness_tips", [])
        result.setdefault("overall_score", 50)
        result.setdefault("priority_actions", [])
        return result
