"""
AIM Reviewer Agent \u2014 strict examiner.

Pipeline:
  1. Run deterministic quality_filters (banned phrases, repetition, no-critique).
  2. Send section + filter findings to LLM reviewer.
  3. Apply deterministic penalties to sub-scores.
  4. Compute weighted AIM Quality Score.
  5. Decide pass / revise / reject based on PASS_THRESHOLD = 85.

Cost-aware: defaults to gemini-2.5-flash (task_type=aim_reviewer).
Orchestrator escalates to Pro by re-invoking with task_type='aim_recon' (Pro)
when score is in the 70\u201385 grey zone for second-opinion.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ai_engine.agents.aim.quality_filters import (
    deterministic_penalty,
    run_all_filters,
)
from ai_engine.agents.aim.schemas import REVIEWER_SCHEMA
from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.client import AIClient

_PROMPT = (Path(__file__).parent / "prompts" / "reviewer_system.md").read_text(encoding="utf-8")

_DIMENSION_WEIGHTS: dict[str, float] = {
    "directive_alignment": 0.25,
    "analytical_depth":    0.30,
    "academic_tone":       0.15,
    "originality":         0.15,
    "structure":           0.15,
}
PASS_THRESHOLD = 85
REVISION_THRESHOLD = 75
GREY_ZONE = (70, 85)  # below 70 \u2192 reject, 70\u201385 \u2192 candidate for Pro escalation


def _weighted_score(sub_scores: dict[str, float]) -> float:
    if not sub_scores:
        return 0.0
    total = 0.0
    weight_used = 0.0
    for k, w in _DIMENSION_WEIGHTS.items():
        if k in sub_scores:
            total += float(sub_scores[k]) * w
            weight_used += w
    return round(total / weight_used, 2) if weight_used else 0.0


class AIMReviewerAgent(BaseAgent):
    def __init__(self, ai_client: AIClient | None = None) -> None:
        super().__init__(
            name="aim_reviewer",
            system_prompt=_PROMPT,
            output_schema=REVIEWER_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict[str, Any]) -> AgentResult:
        start = time.monotonic_ns()
        section_content: str = context.get("section_content") or ""
        if not section_content.strip():
            raise ValueError("aim_reviewer: section_content required")
        section_meta = context.get("section_meta") or {}
        parsed = context.get("parsed") or {}
        recon = context.get("recon") or {}

        # 1) deterministic filters
        det_hits = run_all_filters(section_content)
        det_penalty = deterministic_penalty(det_hits)
        det_issues = [h.as_issue() for h in det_hits]

        # 2) LLM reviewer (use Pro escalation if context says so)
        task_type = "aim_recon" if context.get("escalate_to_pro") else "aim_reviewer"
        prompt = (
            f"DIRECTIVE: {parsed.get('directive', 'analyse')}\n"
            f"ACADEMIC LEVEL: {parsed.get('academic_level', 'ug')}\n"
            f"SECTION TITLE: {section_meta.get('title', '')}\n"
            f"WORD LIMIT: {section_meta.get('word_limit', 'n/a')}\n"
            f"RUBRIC CRITERIA: {parsed.get('rubric_breakdown', [])}\n"
            f"DISTINCTION STRATEGY: {recon.get('distinction_strategy', '')}\n\n"
            f"DETERMINISTIC FILTER HITS (already counted as critical issues): {det_issues}\n\n"
            f"SECTION CONTENT:\n{section_content}\n\n"
            "Score honestly. Be harsh."
        )
        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            schema=self.output_schema,
            task_type=task_type,
            temperature=0.2,
        )

        # 3) apply deterministic penalties to academic_tone / structure / analytical_depth
        sub = dict(result.get("sub_scores") or {})
        for h in det_hits:
            dim = h.as_issue()["dimension"]
            sub[dim] = max(0.0, float(sub.get(dim, 0)) - h.as_issue()["expected_gain"])
        result["sub_scores"] = sub

        # 4) merge ranked issues (deterministic first, by severity)
        ranked = list(result.get("ranked_issues") or [])
        merged = det_issues + ranked
        sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        merged.sort(key=lambda i: sev_rank.get(i.get("severity", "low"), 9))
        result["ranked_issues"] = merged

        # 5) verdict
        weighted = _weighted_score(sub)
        all_dims_pass = all(float(sub.get(k, 0)) >= PASS_THRESHOLD for k in _DIMENSION_WEIGHTS)
        any_critical = any(float(sub.get(k, 0)) < 60 for k in _DIMENSION_WEIGHTS)
        if any_critical:
            verdict = "reject"
        elif all_dims_pass and weighted >= PASS_THRESHOLD:
            verdict = "pass"
        else:
            verdict = "revise"
        result["verdict"] = verdict
        result["weighted_score"] = weighted
        result["deterministic_penalty"] = det_penalty
        result["filter_hits"] = [h.kind for h in det_hits]
        result.setdefault("confidence", 0.85)

        # quality_scores surfaced into AgentResult for the orchestrator
        scores = {**{k: float(v) for k, v in sub.items()},
                  "weighted_quality_score": weighted}

        return self._timed_result(
            start,
            content=result,
            quality_scores=scores,
            flags=([f"verdict:{verdict}"]
                   + [f"filter:{h.kind}" for h in det_hits]),
            needs_revision=(verdict != "pass"),
            feedback={"ranked_issues": result["ranked_issues"][:8]},
            metadata={
                "agent": self.name,
                "task_type_used": task_type,
                "weighted_score": weighted,
                "passed_gate": verdict == "pass",
                "in_grey_zone": GREY_ZONE[0] <= weighted < GREY_ZONE[1],
            },
        )
