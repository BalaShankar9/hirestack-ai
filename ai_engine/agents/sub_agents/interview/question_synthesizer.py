"""
QuestionSynthesizer — Phase 2 LLM agent.

Receives structured context from Phase 1 agents and generates polished
interview questions with follow-ups and assessment hints.
"""
from __future__ import annotations

import json
from typing import Any

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult

SYNTHESIS_SYSTEM = """You are an expert interview coach and senior hiring manager.
Generate realistic, role-specific interview questions that prepare candidates
for real interviews at top companies.  Each question must include assessment
hints and natural follow-ups.  Return ONLY valid JSON."""

SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "difficulty": {"type": "STRING"},
                    "question": {"type": "STRING"},
                    "what_we_assess": {"type": "STRING"},
                    "ideal_answer_hints": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "follow_ups": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
        },
        "interview_focus": {"type": "STRING"},
    },
    "required": ["questions"],
}


class QuestionSynthesizer(SubAgent):
    """LLM-backed synthesizer that produces the final set of interview questions."""

    def __init__(self, ai_client=None):
        super().__init__(name="question_synthesizer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        phase1: dict[str, dict] = context.get("phase1_results", {})
        job_title: str = context.get("job_title", "")
        company: str = context.get("company", "")

        framework = phase1.get("question_framework_builder", {})
        role_ctx = phase1.get("role_context_extractor", {})
        gap_probes = phase1.get("candidate_gap_prober", {})
        prep_data = phase1.get("prep_tip_generator", {})

        prompt = self._build_prompt(
            job_title, company, framework, role_ctx, gap_probes,
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=SYNTHESIS_SYSTEM,
            temperature=0.35,
            max_tokens=3000,
            schema=SYNTHESIS_SCHEMA,
            task_type="creative",
        )

        questions = result.get("questions", [])
        # Assign stable IDs if missing
        for i, q in enumerate(questions, 1):
            q.setdefault("id", f"q{i}")

        return SubAgentResult(
            agent_name=self.name,
            data={
                "questions": questions,
                "interview_focus": result.get("interview_focus", ""),
            },
            confidence=0.90 if questions else 0.3,
        )

    # ── Prompt builder ────────────────────────────────────────
    @staticmethod
    def _build_prompt(
        job_title: str,
        company: str,
        framework: dict,
        role_ctx: dict,
        gap_probes: dict,
    ) -> str:
        cat_dist = framework.get("category_distribution", {})
        diff_dist = framework.get("difficulty_distribution", {})
        dimensions = framework.get("assessment_dimensions", [])
        question_count = framework.get("question_count", 10)

        jd_skills = role_ctx.get("jd_skills", [])
        seniority = role_ctx.get("seniority", "mid")
        domains = role_ctx.get("domains", [])
        strengths = role_ctx.get("candidate_strengths", [])
        culture = role_ctx.get("culture_keywords", [])

        probes = gap_probes.get("probes", [])
        missing = gap_probes.get("missing_skills", [])

        lines = [
            f"Generate exactly {question_count} interview questions.",
            f"\nROLE: {job_title}",
            f"COMPANY: {company}",
            f"SENIORITY: {seniority}",
            f"DOMAINS: {', '.join(domains)}",
            f"\nCATEGORY MIX: {json.dumps(cat_dist)}",
            f"DIFFICULTY MIX: {json.dumps(diff_dist)}",
            f"ASSESSMENT DIMENSIONS: {', '.join(dimensions)}",
        ]

        if jd_skills:
            lines.append(f"\nKEY JD SKILLS: {', '.join(jd_skills[:15])}")
        if strengths:
            lines.append(f"CANDIDATE STRENGTHS: {', '.join(strengths[:8])}")
        if missing:
            lines.append(f"CANDIDATE GAPS (probe these): {', '.join(missing[:8])}")
        if culture:
            lines.append(f"CULTURE KEYWORDS: {', '.join(culture[:6])}")
        if probes:
            probe_lines = [f"  - {p['area']} ({p['probe_type']}): {p['reason']}" for p in probes[:6]]
            lines.append("\nSPECIFIC PROBES:\n" + "\n".join(probe_lines))

        lines.append("\nReturn ONLY valid MINIFIED JSON.")
        return "\n".join(lines)
