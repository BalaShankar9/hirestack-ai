"""
Critic Agent — rubric-based quality engine with section-level scoring.

Outputs severity-ranked, machine-actionable issues tied to exact sections.
Decision logic is deterministic (score thresholds), LLM provides assessments.

v2: section-by-section scoring, per-pipeline threshold calibration,
    structured repair instructions, quality delta tracking.
v3: parallel sub-agent evaluation mode for deeper analysis.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import CRITIC_SCHEMA
from ai_engine.agents.sub_agents.base import SubAgentCoordinator
from ai_engine.agents.sub_agents.critic_specialists import (
    ImpactCriticSubAgent,
    ClarityCriticSubAgent,
    ToneMatchCriticSubAgent,
    CompletenessCriticSubAgent,
)
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "critic_system.md"

# Per-pipeline threshold calibration —
# (revision_threshold, pass_threshold)
# Below revision_threshold on ANY dimension → must revise
# All dimensions above pass_threshold → safe to skip revision
_PIPELINE_THRESHOLDS: dict[str, tuple[int, int]] = {
    "cv_generation":      (72, 82),   # Higher bar for CVs
    "cover_letter":       (70, 80),   # Standard bar
    "benchmark":          (65, 78),   # Slightly lower
    "gap_analysis":       (60, 75),   # Analysis output, lower bar
    "interview":          (65, 78),   # Interview prep
    "career_roadmap":     (60, 75),   # Advisory output
    "ats_scanner":        (60, 75),   # Analysis output
    "portfolio":          (70, 80),   # Standard bar
    "personal_statement": (72, 82),   # Higher bar for personal content
}
_DEFAULT_THRESHOLDS = (70, 80)

# Per-pipeline dimension weights (sum to 1.0)
_DIMENSION_WEIGHTS: dict[str, dict[str, float]] = {
    "cv_generation":      {"impact": 0.35, "clarity": 0.25, "tone_match": 0.15, "completeness": 0.25},
    "cover_letter":       {"impact": 0.25, "clarity": 0.30, "tone_match": 0.25, "completeness": 0.20},
    "interview":          {"impact": 0.20, "clarity": 0.35, "tone_match": 0.20, "completeness": 0.25},
    "benchmark":          {"impact": 0.20, "clarity": 0.20, "tone_match": 0.10, "completeness": 0.50},
}
_DEFAULT_WEIGHTS = {"impact": 0.25, "clarity": 0.25, "tone_match": 0.25, "completeness": 0.25}


class CriticAgent(BaseAgent):
    """Rubric engine — structured quality assessment with deterministic decisions.

    v2 improvements:
    - Section-level scoring (not just global)
    - Per-pipeline threshold calibration
    - Structured repair instructions with priority ranking
    - Quality delta tracking for revision loops
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="critic",
            system_prompt=system_prompt,
            output_schema=CRITIC_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
        else:
            draft_content = context.get("content") or context.get("draft", {})

        evaluation_mode = context.get("evaluation_mode", "single") if isinstance(context, dict) else "single"

        if evaluation_mode == "comparative":
            return await self._run_comparative(start, context)

        # Get agent memories for user preferences (if available)
        memories = context.get("agent_memories", []) if isinstance(context, dict) else []
        original_ctx = context.get("original_context", {}) if isinstance(context, dict) else {}
        pipeline_name = original_ctx.get("pipeline", "") if isinstance(original_ctx, dict) else ""

        # Get previous scores for delta tracking
        prev_scores = context.get("previous_quality_scores", {}) if isinstance(context, dict) else {}

        prompt = (
            f"Evaluate this document draft for quality on four dimensions:\n"
            f"- Impact (0-100): quantified achievements, strong verbs, measurable results\n"
            f"- Clarity (0-100): clear writing, good structure, appropriate jargon\n"
            f"- Tone Match (0-100): matches target company culture\n"
            f"- Completeness (0-100): all sections present, no gaps\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n"
        )

        if original_ctx.get("job_title"):
            prompt += f"\nTarget Role: {original_ctx['job_title']}"
        if original_ctx.get("company"):
            prompt += f"\nTarget Company: {original_ctx['company']}"
        if memories:
            prompt += f"\n\nUser Preferences (from memory):\n{json.dumps(memories[:3], default=str)[:500]}"

        # v5: evidence-aware evaluation — include ledger so critic can check claim backing
        evidence_ledger = context.get("evidence_ledger") if isinstance(context, dict) else None
        if evidence_ledger and hasattr(evidence_ledger, "to_prompt_context"):
            ledger_ctx = evidence_ledger.to_prompt_context(max_items=30)
            if ledger_ctx:
                prompt += (
                    f"\n\nEvidence Ledger (verified source data):\n{ledger_ctx}\n"
                    "When evaluating completeness and impact, check whether key claims in the draft "
                    "are backed by evidence items above. Flag claims that lack evidentiary support "
                    "as a critical_issue with severity 'high'."
                )

        prompt += (
            "\n\nFor EACH critical issue, provide:\n"
            "1. The exact section or HTML element where the problem is\n"
            "2. Severity: 'critical' (must fix), 'high' (should fix), 'medium' (nice to fix)\n"
            "3. A precise, machine-usable repair instruction (e.g., 'Replace \"managed projects\" "
            "with \"managed 5 cross-functional projects delivering $2M in annual savings\"')\n"
            "4. Expected score improvement if fixed\n\n"
            "Rank all issues by impact on overall quality (most impactful first).\n"
            "Return a confidence score (0-1) for your overall assessment."
        )

        if prev_scores:
            prompt += (
                f"\n\nPrevious scores (for delta tracking): {json.dumps(prev_scores)}\n"
                f"Focus on dimensions that still need improvement."
            )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=2048,
            temperature=0.3,
            schema=self.output_schema,
            task_type="critique",
        )

        quality_scores = result.get("quality_scores", {})
        feedback = result.get("feedback", {})

        # Clamp LLM-returned scores to valid 0-100 range
        for dim in ("impact", "clarity", "tone_match", "completeness"):
            raw = quality_scores.get(dim, 0)
            if not isinstance(raw, (int, float)):
                raw = 0
            quality_scores[dim] = max(0, min(100, round(float(raw))))

        # Deterministic revision decision with pipeline-calibrated thresholds
        rev_thresh, pass_thresh = _PIPELINE_THRESHOLDS.get(pipeline_name, _DEFAULT_THRESHOLDS)
        scores = [
            quality_scores["impact"],
            quality_scores["clarity"],
            quality_scores["tone_match"],
            quality_scores["completeness"],
        ]
        needs_revision = any(s < rev_thresh for s in scores)
        if not needs_revision:
            needs_revision = not all(s >= pass_thresh for s in scores)

        # If we have previous scores, check if revision made meaningful progress
        # If it didn't improve by at least 3 points on any dimension, stop revising
        if prev_scores and needs_revision:
            deltas = [
                quality_scores.get(d, 0) - prev_scores.get(d, 0)
                for d in ("impact", "clarity", "tone_match", "completeness")
            ]
            max_improvement = max(deltas) if deltas else 0
            if max_improvement < 3:
                needs_revision = False  # Diminishing returns — stop

        # Override LLM's needs_revision with our deterministic decision
        result["needs_revision"] = needs_revision

        # Compute weighted quality score
        weights = _DIMENSION_WEIGHTS.get(pipeline_name, _DEFAULT_WEIGHTS)
        weighted_score = sum(
            quality_scores.get(dim, 0) * w
            for dim, w in weights.items()
        )
        result["weighted_quality_score"] = round(weighted_score, 1)

        # Track quality deltas if previous scores available
        if prev_scores:
            result["quality_deltas"] = {
                dim: round(quality_scores.get(dim, 0) - prev_scores.get(dim, 0), 1)
                for dim in ("impact", "clarity", "tone_match", "completeness")
            }

        # Build ranked_issues — structured list sorted by severity then expected gain
        ranked_issues = self._build_ranked_issues(result, quality_scores, pipeline_name)
        result["ranked_issues"] = ranked_issues

        return self._timed_result(
            start_ns=start,
            content=result,
            quality_scores=quality_scores,
            needs_revision=needs_revision,
            feedback={**feedback, "ranked_issues": ranked_issues},
        )

    @staticmethod
    def _build_ranked_issues(
        result: dict, quality_scores: dict, pipeline_name: str,
    ) -> list[dict]:
        """Build a severity-ranked issue list from the critic's LLM output.

        Returns a sorted list of::
            {severity, dimension, issue, section, expected_gain}
        """
        _SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        _DIMENSIONS = ("impact", "clarity", "tone_match", "completeness")

        raw_issues: list = []
        feedback = result.get("feedback", {})

        # Collect from LLM-returned critical_issues (primary source)
        crit_issues = feedback.get("critical_issues", []) if isinstance(feedback, dict) else []
        if isinstance(crit_issues, list):
            raw_issues.extend(crit_issues)

        # Also scan per-dimension feedback for issue-like entries
        for dim in _DIMENSIONS:
            dim_fb = feedback.get(dim) if isinstance(feedback, dict) else None
            if isinstance(dim_fb, list):
                for item in dim_fb:
                    if isinstance(item, dict) and item.get("issue"):
                        item.setdefault("dimension", dim)
                        raw_issues.append(item)
            elif isinstance(dim_fb, str) and dim_fb.strip():
                # Simple string feedback → create an issue
                score = quality_scores.get(dim, 75)
                sev = "critical" if score < 60 else "high" if score < 72 else "medium"
                raw_issues.append({
                    "dimension": dim,
                    "severity": sev,
                    "issue": dim_fb,
                    "expected_gain": max(0, 80 - score),
                })

        # Infer dimension from lowest scores if no explicit issues
        if not raw_issues and quality_scores:
            for dim in _DIMENSIONS:
                score = quality_scores.get(dim, 75)
                _, pass_thresh = _PIPELINE_THRESHOLDS.get(pipeline_name, _DEFAULT_THRESHOLDS)
                if score < pass_thresh:
                    raw_issues.append({
                        "dimension": dim,
                        "severity": "high" if score < 70 else "medium",
                        "issue": f"{dim} score is {score}, below pass threshold {pass_thresh}",
                        "expected_gain": pass_thresh - score,
                    })

        # Normalize and sort
        ranked = []
        for item in raw_issues:
            if not isinstance(item, dict):
                continue
            ranked.append({
                "severity": item.get("severity", "medium"),
                "dimension": item.get("dimension", item.get("section", "general")),
                "issue": item.get("issue", item.get("suggestion", "")),
                "section": item.get("section", ""),
                "expected_gain": item.get("expected_gain", item.get("expected_improvement", 0)),
            })

        ranked.sort(
            key=lambda x: (
                _SEVERITY_ORDER.get(x["severity"], 9),
                -(x.get("expected_gain", 0) or 0),
            )
        )
        return ranked

    async def _run_comparative(self, start: int, context: dict) -> AgentResult:
        """Compare multiple document variants (A/B Lab mode)."""
        variants = context.get("variants", [])
        variant_texts = []
        for i, v in enumerate(variants):
            content = v.content if isinstance(v, AgentResult) else v
            variant_texts.append(f"--- Variant {i+1} ---\n{json.dumps(content, indent=2)[:2000]}")

        prompt = (
            f"Compare these {len(variants)} document variants and rank them.\n"
            f"For each variant, score all four dimensions.\n"
            f"Then explain: which is best for the target role and why.\n\n"
            + "\n\n".join(variant_texts)
            + "\n\nReturn ranking with explanations and a confidence score (0-1)."
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt + "\n\nYou are in COMPARATIVE mode. Rank all variants.",
            max_tokens=3000,
            temperature=0.3,
            schema=self.output_schema,
            task_type="critique",
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            quality_scores=result.get("quality_scores", {}),
        )

    async def run_parallel_evaluation(self, context: dict) -> dict:
        """Run 4 specialist critic sub-agents in parallel for deeper analysis.

        Returns a merged dict with per-dimension scores and issues that can
        be used to supplement the main critic evaluation.
        """
        draft_content = context.get("content") or context.get("draft", {})
        original_ctx = context.get("original_context", {}) if isinstance(context, dict) else {}

        sub_ctx = {
            "draft_content": draft_content,
            "jd_text": original_ctx.get("jd_text", ""),
            "company_name": original_ctx.get("company", ""),
        }

        agents = [
            ImpactCriticSubAgent(ai_client=self.ai_client),
            ClarityCriticSubAgent(ai_client=self.ai_client),
            ToneMatchCriticSubAgent(ai_client=self.ai_client),
            CompletenessCriticSubAgent(ai_client=self.ai_client),
        ]

        coord = SubAgentCoordinator(agents)
        results = await coord.gather(sub_ctx)

        merged_scores: dict[str, int] = {}
        all_issues: list[dict] = []

        for r in results:
            if r.ok:
                dim = r.data.get("dimension", "")
                if dim:
                    merged_scores[dim] = r.data.get("score", 0)
                all_issues.extend(r.data.get("issues", []))

        return {
            "sub_agent_scores": merged_scores,
            "sub_agent_issues": all_issues,
            "sub_agent_count": len([r for r in results if r.ok]),
        }
