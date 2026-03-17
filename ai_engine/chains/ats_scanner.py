"""
ATS Scanner Chain
Analyzes documents against job descriptions for ATS compatibility
"""
from typing import Dict, Any

from ai_engine.client import AIClient


ATS_SCANNER_SYSTEM = """You are an expert ATS (Applicant Tracking System) specialist and recruiter.
You know exactly how modern ATS systems parse and score resumes/CVs.

Analyze documents for:
- Keyword match rates against job descriptions
- Formatting issues that block ATS parsing
- Missing critical keywords and phrases
- Section structure and completeness
- Quantified achievement gaps

Provide actionable, specific recommendations to maximize ATS score."""


ATS_SCAN_PROMPT = """Analyze this document against the job description for ATS compatibility.

DOCUMENT:
{document_content}

JOB DESCRIPTION:
{jd_text}

Return ONLY valid MINIFIED JSON (no markdown, no code fences, no extra whitespace).
Hard limits: keywords.present max 20, keywords.missing max 20, suggestions max 15.
"""

ATS_SCAN_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "ats_score": {"type": "INTEGER"},
        "keyword_match_rate": {"type": "NUMBER"},
        "keywords": {
            "type": "OBJECT",
            "properties": {
                "present": {"type": "ARRAY", "items": {"type": "STRING"}},
                "missing": {"type": "ARRAY", "items": {"type": "STRING"}},
                "partially_matched": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        },
        "formatting_issues": {"type": "ARRAY", "items": {"type": "STRING"}},
        "section_analysis": {
            "type": "OBJECT",
            "properties": {
                "has_summary": {"type": "BOOLEAN"},
                "has_skills": {"type": "BOOLEAN"},
                "has_experience": {"type": "BOOLEAN"},
                "has_education": {"type": "BOOLEAN"},
                "missing_sections": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        },
        "suggestions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "priority": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "suggestion": {"type": "STRING"},
                    "impact": {"type": "STRING"},
                },
            },
        },
        "overall_assessment": {"type": "STRING"},
        "pass_probability": {"type": "STRING"},
    },
    "required": ["ats_score", "keywords", "suggestions", "overall_assessment"],
}


class ATSScannerChain:
    """Chain for ATS compatibility scanning."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def scan_document(
        self,
        document_content: str,
        jd_text: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Scan a document for ATS compatibility."""
        prompt = ATS_SCAN_PROMPT.format(
            document_content=document_content[:6000],
            jd_text=jd_text[:4000],
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=ATS_SCANNER_SYSTEM,
            temperature=0.0,
            max_tokens=2000,
            schema=ATS_SCAN_SCHEMA,
        )

        return self._validate_result(result)

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if "ats_score" in result:
            result["ats_score"] = max(0, min(100, result["ats_score"]))
        defaults: Dict[str, Any] = {
            "ats_score": 50,
            "keyword_match_rate": 0.0,
            "keywords": {"present": [], "missing": [], "partially_matched": []},
            "formatting_issues": [],
            "section_analysis": {},
            "suggestions": [],
            "overall_assessment": "",
            "pass_probability": "unknown",
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default
        return result
