"""
Application Coach Chain
Contextual Q&A for application workspaces — answers questions about the user's application
using the full context (JD, resume, gaps, documents).
"""
from typing import Dict, Any


COACH_SYSTEM = """You are an expert career coach embedded in a job application workspace.
You have access to the user's resume, the job description, their gap analysis, and generated documents.
Answer questions specifically and actionably based on this context.
Keep responses concise (3-5 sentences max) and always end with a specific next step.
Never make up information — only reference what's in the provided context."""

COACH_PROMPT = """The user is working on an application and asks: "{question}"

APPLICATION CONTEXT:
- Job Title: {job_title}
- Company: {company}
- Match Score: {match_score}%

JD SUMMARY (first 1500 chars):
{jd_summary}

RESUME SUMMARY (first 1000 chars):
{resume_summary}

KEY GAPS:
{gaps_summary}

GENERATED CV EXCERPT (first 500 chars):
{cv_excerpt}

Respond to their question with specific, actionable advice based on this context.
Return ONLY valid JSON:
{{
  "answer": "Your detailed response (3-5 sentences)",
  "suggested_action": "One specific thing they should do next",
  "relevant_section": "Which document/section to focus on (cv|cover_letter|skills|experience|gaps)"
}}"""


class ApplicationCoachChain:
    """Contextual Q&A coach for application workspaces."""

    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def ask(self, question: str, app_context: Dict[str, Any]) -> Dict[str, Any]:
        """Answer a question about the user's application."""
        prompt = COACH_PROMPT.format(
            question=question[:500],
            job_title=app_context.get("job_title", "Not specified"),
            company=app_context.get("company", "Not specified"),
            match_score=app_context.get("match_score", 0),
            jd_summary=app_context.get("jd_text", "")[:1500],
            resume_summary=app_context.get("resume_text", "")[:1000],
            gaps_summary=app_context.get("gaps_summary", "No gaps analyzed yet"),
            cv_excerpt=app_context.get("cv_html", "")[:500],
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=COACH_SYSTEM,
            max_tokens=1000,
            temperature=0.3,
            task_type="reasoning",
        )

        result.setdefault("answer", "I need more context to answer that. Try asking about specific keywords, sections, or improvements.")
        result.setdefault("suggested_action", "Review your gap analysis for specific improvements.")
        result.setdefault("relevant_section", "gaps")

        return result
