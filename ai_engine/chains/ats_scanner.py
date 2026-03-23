"""
ATS Scanner Chain — World-Class 3-Pass Analysis
Pass 1: Keyword extraction + matching (structured_output model)
Pass 2: Structure/format analysis (code_analysis model)
Pass 3: Strategy + rewrite suggestions (reasoning model)
"""
import json
from typing import Dict, Any, List

from ai_engine.client import AIClient


# ── Pass 1: Keyword Analysis ──────────────────────────────────────────

KEYWORD_SYSTEM = """You are an ATS keyword extraction specialist. Your ONLY job is to:
1. Extract every skill, technology, qualification, and requirement keyword from the job description
2. Check which ones appear in the resume (exact match OR semantic equivalent)
3. Identify missing keywords that could cost the candidate their application

Be thorough — ATS systems are literal. "React.js" and "React" are the same, but "JavaScript" and "TypeScript" are different.
Return ONLY valid JSON."""

KEYWORD_PROMPT = """Extract ALL keywords from this job description, then check which appear in the resume.

JOB DESCRIPTION:
{jd_text}

RESUME/CV:
{document_content}

Return JSON:
{{
  "keyword_score": 0-100,
  "total_jd_keywords": 0,
  "present": ["keywords found in resume"],
  "missing": ["keywords NOT found in resume"],
  "partial": ["keywords partially matched or similar"],
  "synonym_matches": [{{"jd_term": "React.js", "resume_term": "React", "match_quality": "exact|strong|weak"}}],
  "critical_missing": ["the 3-5 MOST important missing keywords that would cause ATS rejection"]
}}
Max 25 items per array."""

# ── Pass 2: Structure Analysis ────────────────────────────────────────

STRUCTURE_SYSTEM = """You are an ATS parsing engine simulator. Analyze the resume as if you were
Workday ATS, Greenhouse, or Lever parsing it. Check:
- Section headers (are they standard? "Experience" not "My Journey")
- Date formats (consistent? parseable?)
- Contact info (email, phone, location — present and findable?)
- Bullet point structure (action verb + metric + result?)
- File structure (would tables/columns break parsing?)
- Length and density (too short? too long? appropriate for role level?)
Return ONLY valid JSON."""

STRUCTURE_PROMPT = """Parse this resume as an ATS system would. Identify every structural issue.

RESUME/CV:
{document_content}

Return JSON:
{{
  "format_score": 0-100,
  "sections_found": {{
    "contact_info": true/false,
    "summary": true/false,
    "experience": true/false,
    "education": true/false,
    "skills": true/false,
    "certifications": true/false,
    "projects": true/false
  }},
  "parsing_issues": [
    {{"issue": "description", "severity": "critical|major|minor", "fix": "how to fix it"}}
  ],
  "date_consistency": {{"consistent": true/false, "format_used": "MM/YYYY", "issues": []}},
  "bullet_quality": {{
    "total_bullets": 0,
    "action_verb_starts": 0,
    "quantified_results": 0,
    "score": 0-100
  }},
  "length_assessment": {{
    "word_count": 0,
    "page_estimate": 1,
    "verdict": "appropriate|too_short|too_long",
    "recommendation": ""
  }},
  "ats_friendly_rating": "excellent|good|fair|poor"
}}"""

# ── Pass 3: Strategy Analysis ─────────────────────────────────────────

STRATEGY_SYSTEM = """You are a senior career strategist and hiring manager with 20 years experience.
You've reviewed 50,000+ resumes and know exactly what makes one stand out vs get filtered.
Your job is to provide SPECIFIC, ACTIONABLE rewrite suggestions — not generic advice.
Each suggestion must include the exact text to add or change.
Return ONLY valid JSON."""

STRATEGY_PROMPT = """Compare this resume against the job description and provide strategic improvements.

JOB DESCRIPTION:
{jd_text}

RESUME/CV:
{document_content}

KEYWORD ANALYSIS (from previous pass):
Present: {present_keywords}
Missing: {missing_keywords}

Return JSON:
{{
  "strategy_score": 0-100,
  "overall_verdict": "strong_match|competitive|needs_work|significant_gaps",
  "competitive_position": "Top 10%|Top 25%|Top 50%|Below average",
  "rewrite_suggestions": [
    {{
      "section": "which section to modify",
      "current_text": "what they currently have (brief)",
      "suggested_text": "EXACT text to replace/add — ready to copy-paste",
      "reason": "why this change matters",
      "impact": "high|medium|low",
      "keywords_addressed": ["which missing keywords this fixes"]
    }}
  ],
  "quick_wins": ["3-5 changes that take <5 minutes and boost score significantly"],
  "deal_breakers": ["issues that would cause immediate rejection"],
  "strengths": ["what's already working well — keep these"],
  "overall_assessment": "2-3 sentence summary of the candidate's competitive position"
}}
Max 10 rewrite_suggestions, 5 quick_wins, 5 deal_breakers, 5 strengths."""


class ATSScannerChain:
    """World-class 3-pass ATS analysis chain."""

    VERSION = "2.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def scan_document(
        self,
        document_content: str,
        jd_text: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Run all 3 passes and combine results."""
        doc = document_content[:8000]
        jd = jd_text[:6000]

        # Pass 1: Keywords (structured_output model — minimax-m2)
        keyword_result = await self._pass_keywords(doc, jd)

        # Pass 2: Structure (code_analysis model — qwen3-coder)
        structure_result = await self._pass_structure(doc)

        # Pass 3: Strategy (reasoning model — deepseek)
        strategy_result = await self._pass_strategy(doc, jd, keyword_result)

        # Combine scores: Keywords 40% + Structure 30% + Strategy 30%
        k_score = min(100, max(0, keyword_result.get("keyword_score", 50)))
        s_score = min(100, max(0, structure_result.get("format_score", 50)))
        r_score = min(100, max(0, strategy_result.get("strategy_score", 50)))
        ats_score = round(k_score * 0.4 + s_score * 0.3 + r_score * 0.3)

        # Determine pass probability
        if ats_score >= 80:
            pass_probability = "high"
        elif ats_score >= 60:
            pass_probability = "medium"
        elif ats_score >= 40:
            pass_probability = "low"
        else:
            pass_probability = "very_low"

        return {
            "ats_score": ats_score,
            "pass_probability": pass_probability,
            "score_breakdown": {
                "keyword_score": k_score,
                "structure_score": s_score,
                "strategy_score": r_score,
                "weights": "Keywords 40% | Structure 30% | Strategy 30%",
            },
            "keywords": {
                "present": keyword_result.get("present", []),
                "missing": keyword_result.get("missing", []),
                "partial": keyword_result.get("partial", []),
                "synonym_matches": keyword_result.get("synonym_matches", []),
                "critical_missing": keyword_result.get("critical_missing", []),
                "total_jd_keywords": keyword_result.get("total_jd_keywords", 0),
            },
            "keyword_match_rate": round(
                len(keyword_result.get("present", [])) /
                max(keyword_result.get("total_jd_keywords", 1), 1) * 100, 1
            ),
            "structure": {
                "sections_found": structure_result.get("sections_found", {}),
                "parsing_issues": structure_result.get("parsing_issues", []),
                "date_consistency": structure_result.get("date_consistency", {}),
                "bullet_quality": structure_result.get("bullet_quality", {}),
                "length_assessment": structure_result.get("length_assessment", {}),
                "ats_friendly_rating": structure_result.get("ats_friendly_rating", "unknown"),
            },
            "strategy": {
                "overall_verdict": strategy_result.get("overall_verdict", "needs_work"),
                "competitive_position": strategy_result.get("competitive_position", "Unknown"),
                "rewrite_suggestions": strategy_result.get("rewrite_suggestions", []),
                "quick_wins": strategy_result.get("quick_wins", []),
                "deal_breakers": strategy_result.get("deal_breakers", []),
                "strengths": strategy_result.get("strengths", []),
                "overall_assessment": strategy_result.get("overall_assessment", ""),
            },
            "section_analysis": structure_result.get("sections_found", {}),
            "formatting_issues": structure_result.get("parsing_issues", []),
            "suggestions": strategy_result.get("rewrite_suggestions", []),
            "overall_assessment": strategy_result.get("overall_assessment", ""),
        }

    async def _pass_keywords(self, doc: str, jd: str) -> Dict[str, Any]:
        """Pass 1: Keyword extraction and matching."""
        prompt = KEYWORD_PROMPT.format(document_content=doc, jd_text=jd)
        try:
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=KEYWORD_SYSTEM,
                temperature=0.0,
                max_tokens=3000,
                task_type="structured_output",
            )
        except Exception as e:
            return {"keyword_score": 50, "present": [], "missing": [], "error": str(e)[:100]}
        result.setdefault("keyword_score", 50)
        result.setdefault("present", [])
        result.setdefault("missing", [])
        result.setdefault("partial", [])
        result.setdefault("synonym_matches", [])
        result.setdefault("critical_missing", [])
        result.setdefault("total_jd_keywords", len(result["present"]) + len(result["missing"]))
        return result

    async def _pass_structure(self, doc: str) -> Dict[str, Any]:
        """Pass 2: Structure and format analysis."""
        prompt = STRUCTURE_PROMPT.format(document_content=doc)
        try:
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=STRUCTURE_SYSTEM,
                temperature=0.0,
                max_tokens=2500,
                task_type="code_analysis",
            )
        except Exception as e:
            return {"format_score": 50, "sections_found": {}, "error": str(e)[:100]}
        result.setdefault("format_score", 50)
        result.setdefault("sections_found", {})
        result.setdefault("parsing_issues", [])
        return result

    async def _pass_strategy(self, doc: str, jd: str, keyword_result: Dict) -> Dict[str, Any]:
        """Pass 3: Strategic analysis with rewrite suggestions."""
        present = ", ".join(keyword_result.get("present", [])[:15])
        missing = ", ".join(keyword_result.get("missing", [])[:15])
        prompt = STRATEGY_PROMPT.format(
            document_content=doc, jd_text=jd,
            present_keywords=present or "None identified",
            missing_keywords=missing or "None identified",
        )
        try:
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=STRATEGY_SYSTEM,
                temperature=0.2,
                max_tokens=4000,
                task_type="reasoning",
            )
        except Exception as e:
            return {"strategy_score": 50, "rewrite_suggestions": [], "error": str(e)[:100]}
        result.setdefault("strategy_score", 50)
        result.setdefault("rewrite_suggestions", [])
        result.setdefault("quick_wins", [])
        result.setdefault("deal_breakers", [])
        result.setdefault("strengths", [])
        result.setdefault("overall_assessment", "")
        return result
