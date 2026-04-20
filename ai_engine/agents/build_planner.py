"""
BuildPlanner — produces a typed BuildPlan for an application generation run.

This is the v4 entry point that turns a user request ("build me a CV +
Cover Letter for this JD") into an explicit DAG that the runtime executes.

Distinct from the legacy `PlannerAgent` in ai_engine/agents/planner.py
(which composes pipeline names dynamically). This planner produces a
typed `BuildPlan` artifact aligned with the orchestration foundation.

Why this is rule-based today (not LLM-driven):
  - The 7-phase pipeline is fixed today (recon → atlas → cipher → quill →
    forge → sentinel → nova). What varies is which document modules are
    requested.
  - A deterministic planner gives us reliable progress weights, replayable
    execution, and a real artifact to persist — without betting on an LLM
    hallucinating a different topology each run.
  - When we add a true reasoning planner, it slots in by overriding
    `BuildPlanner.plan()`. The artifact contract stays stable.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

import structlog

from ai_engine.agents.artifact_contracts import (
    BuildPlan,
    EvidenceTier,
    StagePlan,
)

logger = structlog.get_logger(__name__)


# Canonical ordering of the 7 phases — must stay aligned with
# pipeline_runtime._PHASE_ORDER.
_PHASE_ORDER: List[str] = [
    "recon", "atlas", "cipher", "quill", "forge", "sentinel", "nova",
]

# Stage weights by phase. Heavier where there's real LLM work +
# document generation. Used by progress_calculator for truthful %.
_PHASE_WEIGHT = {
    "recon": 1.0,
    "atlas": 1.5,
    "cipher": 1.5,
    "quill": 3.0,        # CV + cover letter + roadmap
    "forge": 2.0,        # personal statement + portfolio
    "sentinel": 1.0,
    "nova": 0.5,
}

# Module → phase that produces it.
_MODULE_PHASE = {
    "cv": "quill",
    "resume": "quill",
    "cover_letter": "quill",
    "roadmap": "quill",
    "learning_plan": "quill",
    "personal_statement": "forge",
    "portfolio": "forge",
}


class BuildPlanner:
    """Builds a BuildPlan from the request shape."""

    def __init__(self, *, agent_name: str = "build_planner") -> None:
        self._agent_name = agent_name

    def plan(
        self,
        *,
        application_id: Optional[str],
        job_title: str = "",
        company: str = "",
        requested_modules: Optional[Iterable[str]] = None,
    ) -> BuildPlan:
        modules = self._normalize_modules(requested_modules)
        stages = self._build_stages(modules)

        rationale = (
            f"Canonical 7-phase pipeline for application "
            f"{application_id or 'n/a'} with modules={modules}. "
            f"Stage weights tuned for truthful progress."
        )

        plan = BuildPlan(
            application_id=application_id,
            created_by_agent=self._agent_name,
            confidence=1.0,
            evidence_tier=EvidenceTier.DERIVED,
            job_title=job_title or "",
            company=company or "",
            requested_modules=list(modules),
            stages=stages,
            rationale=rationale,
        )
        logger.info("build_planner.plan_built",
                    application_id=application_id,
                    stage_count=len(stages),
                    modules=modules)
        return plan

    # ── internals ──────────────────────────────────────────────────────

    @staticmethod
    def _normalize_modules(requested: Optional[Iterable[str]]) -> List[str]:
        if not requested:
            return ["cv", "cover_letter", "roadmap"]
        seen: List[str] = []
        for m in requested:
            if not m:
                continue
            key = str(m).strip().lower()
            if key and key not in seen:
                seen.append(key)
        return seen or ["cv", "cover_letter", "roadmap"]

    def _build_stages(self, modules: List[str]) -> List[StagePlan]:
        stages: List[StagePlan] = []

        stages.append(StagePlan(
            stage_id="recon.intel",
            agent_name="recon",
            description="Gather public company intelligence (web research swarm).",
            depends_on=[],
            expected_artifact_type="CompanyIntelReport",
            optional=True,
            weight=_PHASE_WEIGHT["recon"],
            timeout_s=120.0,
        ))

        stages.append(StagePlan(
            stage_id="atlas.benchmark",
            agent_name="atlas",
            description="Parse resume and build canonical benchmark profile.",
            depends_on=["recon.intel"],
            expected_artifact_type="BenchmarkProfile",
            optional=False,
            weight=_PHASE_WEIGHT["atlas"],
            timeout_s=180.0,
        ))

        stages.append(StagePlan(
            stage_id="cipher.gaps",
            agent_name="cipher",
            description="Compute skills/experience gaps between profile and JD.",
            depends_on=["atlas.benchmark"],
            expected_artifact_type="SkillGapMap",
            optional=False,
            weight=_PHASE_WEIGHT["cipher"],
            timeout_s=180.0,
        ))

        quill_modules = [m for m in modules if _MODULE_PHASE.get(m) == "quill"]
        if quill_modules:
            stages.append(StagePlan(
                stage_id="quill.documents",
                agent_name="quill",
                description=f"Tailor and draft documents: {quill_modules}.",
                depends_on=["cipher.gaps"],
                expected_artifact_type="TailoredDocumentBundle",
                optional=False,
                weight=_PHASE_WEIGHT["quill"],
                timeout_s=300.0,
            ))

        forge_modules = [m for m in modules if _MODULE_PHASE.get(m) == "forge"]
        if forge_modules:
            stages.append(StagePlan(
                stage_id="forge.long_form",
                agent_name="forge",
                description=f"Generate long-form documents: {forge_modules}.",
                depends_on=["cipher.gaps"],
                expected_artifact_type="TailoredDocumentBundle",
                optional=True,
                weight=_PHASE_WEIGHT["forge"],
                timeout_s=240.0,
            ))

        post_doc_deps = [s.stage_id for s in stages if s.stage_id.startswith(("quill.", "forge."))]
        stages.append(StagePlan(
            stage_id="sentinel.validate",
            agent_name="sentinel",
            description="Validate quality, factuality, and brand consistency.",
            depends_on=post_doc_deps or ["cipher.gaps"],
            expected_artifact_type="ValidationReport",
            optional=False,
            weight=_PHASE_WEIGHT["sentinel"],
            timeout_s=120.0,
        ))

        stages.append(StagePlan(
            stage_id="nova.assemble",
            agent_name="nova",
            description="Assemble the final application pack and persist.",
            depends_on=["sentinel.validate"],
            expected_artifact_type="FinalApplicationPack",
            optional=False,
            weight=_PHASE_WEIGHT["nova"],
            timeout_s=60.0,
        ))

        return stages
