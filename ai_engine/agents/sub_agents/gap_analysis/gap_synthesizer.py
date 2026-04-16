"""
GapSynthesizer — Phase 2 LLM synthesis agent for the Gap Analysis swarm.

Takes the structured outputs from all five Phase 1 deterministic agents
(TechnicalSkillAnalyst, ExperienceAnalyst, EducationCertAnalyst,
SoftSkillCultureAnalyst, StrengthMapper) and produces a coherent,
human-quality final analysis:
  • Executive summary narrative
  • Unified compatibility_score
  • Readiness level classification
  • Prioritised recommendations with action items
  • Interview readiness assessment

Uses a single LLM call with a tight schema to stay within token budget.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

_SYNTHESIS_SYSTEM = """You are an expert career gap analyst.
You receive raw analysis data from five specialist assessment agents.
Your task is to produce a unified, human-readable gap analysis report.

Rules:
- Scores are 0–100. Be honest — don't inflate.
- Executive summary 2–3 sentences max, specific to this candidate.
- Recommendations sorted by impact (highest first).
- Quick wins are things achievable in <1 week.
- Keep all strings concise (<180 chars).
- Return ONLY valid minified JSON matching the schema — no markdown, no commentary."""

_SYNTHESIS_PROMPT = """Synthesise a gap analysis report from these specialist assessments.

ROLE: {job_title} at {company}

TECHNICAL SKILLS ANALYSIS:
{technical}

EXPERIENCE ANALYSIS:
{experience}

EDUCATION & CERTIFICATIONS:
{education}

SOFT SKILLS & CULTURE:
{soft_skills}

STRENGTHS & QUICK WINS:
{strengths}

Using the data above, produce a unified gap analysis. The category_scores.*.weight
values must sum to 1.0 across the 6 categories. Use these defaults unless the data
strongly suggests otherwise:
  technical_skills=0.30, experience=0.25, education=0.10,
  certifications=0.10, soft_skills=0.15, projects_portfolio=0.10.

Return ONLY valid minified JSON matching the provided schema."""


_SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "executive_summary": {"type": "STRING"},
        "compatibility_score": {"type": "INTEGER"},
        "readiness_level": {
            "type": "STRING",
            "enum": ["needs-work", "competitive", "strong-match", "not-ready"],
        },
        "category_scores": {
            "type": "OBJECT",
            "properties": {
                "technical_skills": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "experience": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "education": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "certifications": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "soft_skills": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "projects_portfolio": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
            },
        },
        "recommendations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "priority": {"type": "INTEGER"},
                    "category": {
                        "type": "STRING",
                        "enum": ["skills", "experience", "certification", "project", "other"],
                    },
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "action_items": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "estimated_effort": {"type": "STRING"},
                    "impact": {"type": "STRING"},
                },
            },
        },
        "quick_wins": {"type": "ARRAY", "items": {"type": "STRING"}},
        "interview_readiness": {
            "type": "OBJECT",
            "properties": {
                "ready_to_interview": {"type": "BOOLEAN"},
                "preparation_needed": {"type": "ARRAY", "items": {"type": "STRING"}},
                "potential_questions": {"type": "ARRAY", "items": {"type": "STRING"}},
                "talking_points": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        },
    },
    "required": ["executive_summary", "compatibility_score", "readiness_level"],
}


class GapSynthesizer(SubAgent):
    """LLM synthesis agent — merges Phase 1 outputs into a unified gap report."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="gap_synthesizer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        phase1 = context.get("phase1_results", {})
        job_title = context.get("job_title", "Unknown Role")
        company = context.get("company", "Unknown Company")

        # Compact JSON strings for each specialist (truncate to keep within token budget)
        def _compact(data: dict, limit: int = 2500) -> str:
            return json.dumps(data, separators=(",", ":"), ensure_ascii=False)[:limit]

        prompt = _SYNTHESIS_PROMPT.format(
            job_title=job_title,
            company=company,
            technical=_compact(phase1.get("technical_skill_analyst", {})),
            experience=_compact(phase1.get("experience_analyst", {})),
            education=_compact(phase1.get("education_cert_analyst", {})),
            soft_skills=_compact(phase1.get("soft_skill_analyst", {})),
            strengths=_compact(phase1.get("strength_mapper", {})),
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=_SYNTHESIS_SYSTEM,
            temperature=0.0,
            max_tokens=3000,
            schema=_SYNTHESIS_SCHEMA,
        )

        # Inject the deterministic sub-fields the LLM doesn't produce
        result = self._merge_deterministic(result, phase1)
        result = self._validate(result)

        confidence = 0.7 if result.get("executive_summary") else 0.3

        return SubAgentResult(
            agent_name=self.name,
            data=result,
            confidence=confidence,
        )

    def _merge_deterministic(self, llm_result: dict, phase1: dict) -> dict:
        """Merge the raw deterministic skill_gaps, experience_gaps, strengths
        from Phase 1 agents into the LLM output since those are best kept exact."""

        tech = phase1.get("technical_skill_analyst", {})
        exp = phase1.get("experience_analyst", {})
        edu = phase1.get("education_cert_analyst", {})
        strengths = phase1.get("strength_mapper", {})

        # Skill gaps from deterministic agent (more precise than LLM guesses)
        if tech.get("skill_gaps"):
            llm_result["skill_gaps"] = tech["skill_gaps"][:12]

        # Experience gaps
        if exp.get("experience_gaps"):
            llm_result["experience_gaps"] = exp["experience_gaps"][:6]

        # Strengths from the strength mapper
        if strengths.get("strengths"):
            llm_result["strengths"] = strengths["strengths"][:8]

        # Quick wins — merge LLM + strength_mapper, deduplicate
        llm_qw = llm_result.get("quick_wins", [])
        det_qw = strengths.get("quick_wins", [])
        seen = set()
        merged_qw = []
        for qw in det_qw + llm_qw:
            if isinstance(qw, str) and qw not in seen:
                seen.add(qw)
                merged_qw.append(qw)
        llm_result["quick_wins"] = merged_qw[:8]

        return llm_result

    def _validate(self, result: dict) -> dict:
        """Clamp scores, fill defaults, sort recommendations."""
        if "compatibility_score" in result:
            result["compatibility_score"] = max(0, min(100, result["compatibility_score"]))

        defaults = {
            "compatibility_score": 50,
            "readiness_level": "needs-work",
            "executive_summary": "",
            "category_scores": {},
            "skill_gaps": [],
            "experience_gaps": [],
            "strengths": [],
            "recommendations": [],
            "quick_wins": [],
            "interview_readiness": {},
        }
        for key, default in defaults.items():
            result.setdefault(key, default)

        # Clean recommendations
        if result.get("recommendations"):
            result["recommendations"] = [
                r for r in result["recommendations"] if isinstance(r, dict)
            ]
            result["recommendations"].sort(key=lambda x: x.get("priority", 99))
            result["recommendations"] = result["recommendations"][:10]

        # Ensure interview_readiness has expected sub-keys
        ir = result.get("interview_readiness", {})
        ir.setdefault("ready_to_interview", False)
        ir.setdefault("preparation_needed", [])
        ir.setdefault("potential_questions", [])
        ir.setdefault("talking_points", [])
        result["interview_readiness"] = ir

        return result
