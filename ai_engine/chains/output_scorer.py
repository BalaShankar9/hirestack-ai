"""
Output Quality Scorer — 4-dimension scoring for generated documents.

Dimensions:
  1. Relevance  (0-10): How well the output addresses the job description
  2. Formatting (0-10): Structure, layout, readability of HTML/text
  3. Keyword Coverage (0-10): JD keyword presence in the generated content
  4. Readability (0-10): Clarity, tone, professional quality
"""
import json
import re
from typing import Dict, Any, Optional

from ai_engine.client import AIClient


SCORER_SYSTEM = """You are an expert career document quality analyst.
Score the provided document on four specific dimensions.
Be strict and calibrated — do NOT default to 8/10 for everything.
A score of 5 means average, 7 means good, 9+ means exceptional.
Justify every score with a specific observation from the document."""


SCORE_PROMPT = """Score this generated {document_type} against the job description on 4 dimensions.

JOB DESCRIPTION:
{jd_text}

GENERATED DOCUMENT:
{content}

USER PROFILE SUMMARY:
{profile_summary}

Score each dimension 0-10 and provide a one-sentence justification:

Return ONLY valid JSON:
{{
  "relevance": {{
    "score": 0,
    "justification": "How well the document targets the specific role/JD requirements"
  }},
  "formatting": {{
    "score": 0,
    "justification": "Structure quality, section organization, visual hierarchy"
  }},
  "keyword_coverage": {{
    "score": 0,
    "justification": "Presence of key JD terms, skills, and qualifications in the output"
  }},
  "readability": {{
    "score": 0,
    "justification": "Clarity, professional tone, grammar, sentence flow"
  }},
  "overall": {{
    "score": 0,
    "justification": "Overall assessment"
  }},
  "top_improvement": "The single most impactful change to raise quality"
}}"""


SCORE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "relevance": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER"},
                "justification": {"type": "STRING"},
            },
            "required": ["score", "justification"],
        },
        "formatting": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER"},
                "justification": {"type": "STRING"},
            },
            "required": ["score", "justification"],
        },
        "keyword_coverage": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER"},
                "justification": {"type": "STRING"},
            },
            "required": ["score", "justification"],
        },
        "readability": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER"},
                "justification": {"type": "STRING"},
            },
            "required": ["score", "justification"],
        },
        "overall": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER"},
                "justification": {"type": "STRING"},
            },
            "required": ["score", "justification"],
        },
        "top_improvement": {"type": "STRING"},
    },
    "required": ["relevance", "formatting", "keyword_coverage", "readability", "overall", "top_improvement"],
}


def _strip_html(html: str) -> str:
    """Lightweight HTML tag removal for readability analysis."""
    return re.sub(r"<[^>]+>", " ", html).strip()


def _summarize_profile(profile: Dict[str, Any]) -> str:
    """Build a concise profile summary for the scorer prompt."""
    parts = []
    name = profile.get("name") or profile.get("full_name", "")
    if name:
        parts.append(f"Name: {name}")
    title = profile.get("title") or profile.get("current_title", "")
    if title:
        parts.append(f"Title: {title}")
    skills = profile.get("skills") or []
    if skills:
        skill_names = [s.get("name", s) if isinstance(s, dict) else str(s) for s in skills[:15]]
        parts.append(f"Skills: {', '.join(skill_names)}")
    experience = profile.get("experience") or []
    if experience:
        parts.append(f"Experience: {len(experience)} positions")
    return "; ".join(parts) if parts else "No profile data available"


class OutputScorer:
    """Score generated documents on 4 quality dimensions using AI."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def score(
        self,
        document_type: str,
        content: str,
        jd_text: str,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Score a generated document.

        Returns:
            {
                "relevance": {"score": int, "justification": str},
                "formatting": {"score": int, "justification": str},
                "keyword_coverage": {"score": int, "justification": str},
                "readability": {"score": int, "justification": str},
                "overall": {"score": int, "justification": str},
                "top_improvement": str,
                "composite_score": float,
            }
        """
        clean_content = _strip_html(content)
        if not clean_content or len(clean_content) < 20:
            return _empty_scores("Document is empty or too short to score")

        profile_summary = _summarize_profile(user_profile or {})

        prompt = SCORE_PROMPT.format(
            document_type=document_type,
            jd_text=jd_text[:4000],  # cap to avoid token overflow
            content=clean_content[:6000],
            profile_summary=profile_summary,
        )

        try:
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=SCORER_SYSTEM,
                temperature=0.2,
                max_tokens=1500,
                schema=SCORE_SCHEMA,
                task_type="quality_scoring",
            )
        except Exception:
            return _empty_scores("Scoring failed due to AI error")

        # Clamp scores to 0-10 range
        for dim in ("relevance", "formatting", "keyword_coverage", "readability", "overall"):
            if dim in result and isinstance(result[dim], dict):
                result[dim]["score"] = max(0, min(10, int(result[dim].get("score", 0))))

        # Compute weighted composite (0-100)
        weights = {"relevance": 0.3, "formatting": 0.15, "keyword_coverage": 0.3, "readability": 0.25}
        composite = sum(
            result.get(dim, {}).get("score", 0) * w
            for dim, w in weights.items()
        ) * 10
        result["composite_score"] = round(composite, 1)

        return result


def _empty_scores(reason: str) -> Dict[str, Any]:
    """Return a zeroed score set with an explanation."""
    empty_dim = {"score": 0, "justification": reason}
    return {
        "relevance": dict(empty_dim),
        "formatting": dict(empty_dim),
        "keyword_coverage": dict(empty_dim),
        "readability": dict(empty_dim),
        "overall": dict(empty_dim),
        "top_improvement": reason,
        "composite_score": 0.0,
    }
