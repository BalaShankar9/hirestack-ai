"""
PlannerAgent — top-level planner for dynamic pipeline composition.

Instead of always routing a user request to a single hard-coded pipeline,
the PlannerAgent uses an LLM to decide which pipeline(s) to run — and in
what order — to best fulfil the request.  It can:
  • Choose a single pipeline (fast path, equivalent to the old routing)
  • Compose multiple sequential pipelines (e.g. gap_analysis → cv_generation)
  • Merge the outputs of parallel pipelines (e.g. cover_letter ∥ personal_statement)

Enhanced with evidence-aware quality scoring to adapt pipeline behaviour
based on the strength of available evidence and input quality.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

logger = logging.getLogger("hirestack.planner")

# ── Data classes ──────────────────────────────────────────────────

@dataclass
class PipelineStep:
    """A single pipeline invocation within a plan."""
    pipeline_name: str
    reason: str = ""
    depends_on: list[str] = field(default_factory=list)
    context_overrides: dict = field(default_factory=dict)


@dataclass
class PipelinePlan:
    """Output of the PlannerAgent — a DAG of pipeline steps."""
    steps: list[PipelineStep]
    reasoning: str = ""
    estimated_latency_hint: str = ""  # "fast" / "medium" / "slow"

    @property
    def pipeline_names(self) -> list[str]:
        return [s.pipeline_name for s in self.steps]

    @property
    def is_single(self) -> bool:
        return len(self.steps) == 1


@dataclass
class PlanArtifact:
    """Audit artifact from adaptive planning — persisted to pipeline_plans table."""
    plan: PipelinePlan
    jd_quality_score: int = 0         # 0-100
    profile_quality_score: int = 0    # 0-100
    evidence_strength_score: int = 0  # 0-100
    risk_mode: str = "normal"         # conservative / normal / aggressive
    input_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "plan": {
                "steps": [
                    {"pipeline_name": s.pipeline_name, "reason": s.reason,
                     "depends_on": s.depends_on, "context_overrides": s.context_overrides}
                    for s in self.plan.steps
                ],
                "reasoning": self.plan.reasoning,
                "estimated_latency_hint": self.plan.estimated_latency_hint,
            },
            "jd_quality_score": self.jd_quality_score,
            "profile_quality_score": self.profile_quality_score,
            "evidence_strength_score": self.evidence_strength_score,
            "risk_mode": self.risk_mode,
            "input_summary": self.input_summary,
        }


# ── Available pipelines (kept in sync with pipelines.py registry) ──

AVAILABLE_PIPELINES = {
    "resume_parse": "Parse and structure a resume/CV from raw text or file",
    "benchmark": "Score a user profile against a job description",
    "gap_analysis": "Identify skill/experience gaps between profile and JD",
    "cv_generation": "Generate a tailored CV/resume document",
    "cover_letter": "Generate a tailored cover letter",
    "personal_statement": "Generate a personal/professional statement",
    "portfolio": "Generate a portfolio or project showcase document",
    "ats_scanner": "Scan a document for ATS compatibility issues",
    "interview": "Generate interview prep material and practice questions",
    "career_roadmap": "Create a career development roadmap",
    "ab_lab": "Generate A/B variants of a document for comparison",
    "salary_coach": "Provide salary negotiation guidance and benchmarks",
    "learning": "Generate a personalised learning plan",
}

_PLANNER_SYSTEM_PROMPT_PATH = (
    Path(__file__).parent / "prompts" / "planner_system.md"
)


def _load_system_prompt() -> str:
    """Load the planner system prompt from disk, with fallback."""
    try:
        return _PLANNER_SYSTEM_PROMPT_PATH.read_text()
    except FileNotFoundError:
        return (
            "You are a pipeline planner for HireStack AI. "
            "Given a user request and available pipelines, decide which "
            "pipeline(s) to run and in what order. Respond with JSON."
        )


class PlannerAgent(BaseAgent):
    """Decides which pipeline(s) to run for a given user request."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(
            name="planner",
            system_prompt=_load_system_prompt(),
            output_schema={},  # free-form JSON
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        """Analyse the user request and produce a PipelinePlan.

        Expected context keys:
          - user_request: str  (the high-level task description or doc_type)
          - user_profile: optional dict
          - jd_text: optional str
          - available_data: optional dict summarising what inputs are present
        """
        start = time.perf_counter()

        user_request = context.get("user_request", "")
        available_data = context.get("available_data", {})

        # Fast path: if user_request exactly matches a pipeline name, skip LLM
        if user_request in AVAILABLE_PIPELINES:
            plan = PipelinePlan(
                steps=[PipelineStep(pipeline_name=user_request, reason="exact_match")],
                reasoning=f"Request '{user_request}' maps directly to a pipeline.",
                estimated_latency_hint="fast",
            )
            latency = int((time.perf_counter() - start) * 1000)
            return AgentResult(
                content={"plan": self._plan_to_dict(plan)},
                quality_scores={},
                flags=[],
                latency_ms=latency,
                metadata={"plan": plan, "source": "exact_match"},
            )

        # Build prompt for LLM planning
        pipelines_desc = "\n".join(
            f'- "{name}": {desc}' for name, desc in AVAILABLE_PIPELINES.items()
        )
        data_summary = json.dumps(available_data, indent=2, default=str)[:1000]

        planning_prompt = (
            f"## User Request\n{user_request}\n\n"
            f"## Available Data\n{data_summary}\n\n"
            f"## Available Pipelines\n{pipelines_desc}\n\n"
            "Decide which pipeline(s) to run. You may:\n"
            "1. Choose a SINGLE pipeline (most common for simple requests)\n"
            "2. Chain multiple pipelines sequentially (output of one feeds into next)\n"
            "3. Run pipelines in parallel then merge results\n\n"
            "Respond with JSON:\n"
            "{\n"
            '  "steps": [\n'
            '    {"pipeline_name": "...", "reason": "...", "depends_on": []},\n'
            "    ...\n"
            "  ],\n"
            '  "reasoning": "...",\n'
            '  "estimated_latency_hint": "fast|medium|slow"\n'
            "}\n\n"
            "Rules:\n"
            "- Only use pipeline names from the Available Pipelines list\n"
            "- depends_on lists pipeline_names that must complete first\n"
            "- Keep it minimal — don't add pipelines that aren't needed\n"
            "- For document generation requests, usually gap_analysis before the doc pipeline is beneficial"
        )

        try:
            result = await self.ai_client.complete_json(
                prompt=planning_prompt,
                system=self.system_prompt,
                max_tokens=400,
                temperature=0.1,
                task_type="structured_output",
            )
            plan = self._parse_plan(result)
        except Exception as e:
            logger.warning("planner_llm_failed", error=str(e))
            plan = self._fallback_plan(user_request)

        latency = int((time.perf_counter() - start) * 1000)
        logger.info(
            "planner_decision",
            pipelines=plan.pipeline_names,
            reasoning=plan.reasoning[:200],
            latency_ms=latency,
        )

        return AgentResult(
            content={"plan": self._plan_to_dict(plan)},
            quality_scores={},
            flags=[],
            latency_ms=latency,
            metadata={"plan": plan, "source": "llm"},
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _parse_plan(self, raw: dict) -> PipelinePlan:
        """Parse LLM JSON into a PipelinePlan, filtering invalid pipeline names."""
        steps = []
        for step_data in raw.get("steps", []):
            name = step_data.get("pipeline_name", "")
            if name not in AVAILABLE_PIPELINES:
                logger.warning("planner_invalid_pipeline", name=name)
                continue
            steps.append(PipelineStep(
                pipeline_name=name,
                reason=step_data.get("reason", ""),
                depends_on=[
                    d for d in step_data.get("depends_on", [])
                    if d in AVAILABLE_PIPELINES
                ],
                context_overrides=step_data.get("context_overrides", {}),
            ))
        if not steps:
            return self._fallback_plan("")
        return PipelinePlan(
            steps=steps,
            reasoning=raw.get("reasoning", ""),
            estimated_latency_hint=raw.get("estimated_latency_hint", "medium"),
        )

    def _fallback_plan(self, user_request: str) -> PipelinePlan:
        """Deterministic fallback when LLM is unavailable or returns garbage."""
        req_lower = user_request.lower()

        # Simple keyword mapping
        keyword_map = {
            "cv": "cv_generation",
            "resume": "cv_generation",
            "cover letter": "cover_letter",
            "cover_letter": "cover_letter",
            "personal statement": "personal_statement",
            "personal_statement": "personal_statement",
            "portfolio": "portfolio",
            "interview": "interview",
            "salary": "salary_coach",
            "learning": "learning",
            "career": "career_roadmap",
            "roadmap": "career_roadmap",
            "ats": "ats_scanner",
            "benchmark": "benchmark",
            "gap": "gap_analysis",
            "parse": "resume_parse",
            "ab": "ab_lab",
        }

        for keyword, pipeline in keyword_map.items():
            if keyword in req_lower:
                return PipelinePlan(
                    steps=[PipelineStep(pipeline_name=pipeline, reason="keyword_fallback")],
                    reasoning=f"Fallback: matched keyword '{keyword}'",
                    estimated_latency_hint="fast",
                )

        # Default to cv_generation if nothing matches
        return PipelinePlan(
            steps=[PipelineStep(pipeline_name="cv_generation", reason="default_fallback")],
            reasoning="Fallback: no matching keyword found, defaulting to cv_generation",
            estimated_latency_hint="fast",
        )

    @staticmethod
    def _plan_to_dict(plan: PipelinePlan) -> dict:
        return {
            "steps": [
                {
                    "pipeline_name": s.pipeline_name,
                    "reason": s.reason,
                    "depends_on": s.depends_on,
                    "context_overrides": s.context_overrides,
                }
                for s in plan.steps
            ],
            "reasoning": plan.reasoning,
            "estimated_latency_hint": plan.estimated_latency_hint,
        }

    # ── Evidence-aware quality scoring ────────────────────────────

    @staticmethod
    def score_jd_quality(jd_text: str) -> int:
        """Score JD quality 0-100 based on structural signals.

        Looks for: length, section headers, requirements lists,
        salary info, company description, specific technologies.
        """
        if not jd_text or not jd_text.strip():
            return 0

        score = 0
        text = jd_text.strip()

        # Length scoring: 200+ chars = 20pts, 500+ = 30pts, 1000+ = 35pts
        if len(text) >= 1000:
            score += 35
        elif len(text) >= 500:
            score += 30
        elif len(text) >= 200:
            score += 20
        else:
            score += 10

        # Section headers (requirements, responsibilities, qualifications, etc.)
        section_patterns = [
            r"(?:requirements|qualifications|what we.re looking for)",
            r"(?:responsibilities|what you.ll do|the role)",
            r"(?:benefits|perks|compensation|salary)",
            r"(?:about us|about the company|who we are)",
        ]
        for pattern in section_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += 8

        # Bullet points / lists suggest structure
        bullet_count = len(re.findall(r"^\s*[-•*]\s", text, re.MULTILINE))
        if bullet_count >= 5:
            score += 10
        elif bullet_count >= 2:
            score += 5

        # Specific technologies / skills mentioned
        tech_count = len(re.findall(
            r"\b(?:Python|Java|JavaScript|TypeScript|React|AWS|Docker|Kubernetes|SQL|"
            r"Node\.js|Go|Rust|C\+\+|Ruby|Swift|Terraform|Git)\b",
            text, re.IGNORECASE,
        ))
        score += min(15, tech_count * 3)

        return min(100, score)

    @staticmethod
    def score_profile_quality(user_profile: dict) -> int:
        """Score user profile completeness 0-100.

        Checks for: name, contact, experience entries, education,
        skills list, summary/objective.
        """
        if not user_profile:
            return 0

        score = 0

        # Basic fields
        if user_profile.get("name") or user_profile.get("full_name"):
            score += 10
        if user_profile.get("email") or user_profile.get("contact"):
            score += 5

        # Experience
        experience = user_profile.get("experience") or user_profile.get("work_experience") or []
        if isinstance(experience, list):
            exp_count = len(experience)
            if exp_count >= 3:
                score += 25
            elif exp_count >= 1:
                score += 15
        elif experience:
            score += 10

        # Education
        education = user_profile.get("education") or []
        if isinstance(education, list) and len(education) >= 1:
            score += 15
        elif education:
            score += 10

        # Skills
        skills = user_profile.get("skills") or user_profile.get("technical_skills") or []
        if isinstance(skills, list):
            if len(skills) >= 5:
                score += 20
            elif len(skills) >= 1:
                score += 10
        elif skills:
            score += 5

        # Summary / objective
        summary = user_profile.get("summary") or user_profile.get("objective") or ""
        if isinstance(summary, str) and len(summary) > 50:
            score += 15
        elif summary:
            score += 5

        # Certifications
        certs = user_profile.get("certifications") or []
        if certs:
            score += 10

        return min(100, score)

    @staticmethod
    def determine_risk_mode(
        jd_score: int,
        profile_score: int,
        evidence_score: int,
    ) -> str:
        """Determine planning risk mode based on input quality scores.

        Returns: "conservative" | "normal" | "aggressive"
        - conservative: low-quality inputs → more research stages, extra validation
        - normal: decent inputs → standard pipeline
        - aggressive: high-quality inputs → skip optional stages, prioritise speed
        """
        avg_score = (jd_score + profile_score + evidence_score) / 3

        if avg_score >= 70:
            return "aggressive"
        elif avg_score >= 40:
            return "normal"
        else:
            return "conservative"

    def build_plan_artifact(
        self,
        plan: PipelinePlan,
        jd_text: str = "",
        user_profile: Optional[dict] = None,
        evidence_score: int = 0,
    ) -> PlanArtifact:
        """Build a full PlanArtifact with quality scoring for audit/persistence."""
        jd_score = self.score_jd_quality(jd_text)
        profile_score = self.score_profile_quality(user_profile or {})
        risk_mode = self.determine_risk_mode(jd_score, profile_score, evidence_score)

        return PlanArtifact(
            plan=plan,
            jd_quality_score=jd_score,
            profile_quality_score=profile_score,
            evidence_strength_score=evidence_score,
            risk_mode=risk_mode,
            input_summary={
                "jd_length": len(jd_text) if jd_text else 0,
                "profile_fields": len(user_profile) if user_profile else 0,
                "has_experience": bool((user_profile or {}).get("experience")),
                "has_skills": bool((user_profile or {}).get("skills")),
            },
        )
