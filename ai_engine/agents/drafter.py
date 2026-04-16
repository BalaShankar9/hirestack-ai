"""
Drafter Agent — wraps existing chains for first-pass generation.

The run() method delegates to the existing chain method (zero modifications).
The revise() method uses AIClient directly with a structured revision prompt
that prioritises critical issues and preserves factual truth.

v2: priority-ordered feedback, fabrication removal instructions,
    section-level revision targeting, diff-aware system prompt.
v3: parallel section drafting via sub-agents, tone calibration,
    keyword strategy integration.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.sub_agents.base import SubAgentCoordinator
from ai_engine.agents.sub_agents.tone_calibrator import ToneCalibratorSubAgent
from ai_engine.agents.sub_agents.keyword_strategist import KeywordStrategistSubAgent
from ai_engine.client import AIClient

_REVISION_PROMPT_PATH = Path(__file__).parent / "prompts" / "drafter_revision.md"

REVISION_SYSTEM_PROMPT = (
    "You are revising a career document based on structured feedback from quality review agents. "
    "Follow these rules strictly:\n"
    "1. Address CRITICAL issues first, then HIGH, then MEDIUM.\n"
    "2. REMOVE any fabricated claims identified by the fact-checker — do NOT rephrase them.\n"
    "3. INSERT missing keywords NATURALLY into existing sentences — do NOT add fake experience.\n"
    "4. PRESERVE all verified factual content from the original draft.\n"
    "5. Maintain the document's structure and formatting.\n"
    "6. Return the revised document in the SAME JSON format as the original."
)


class DrafterAgent(BaseAgent):
    """Wraps existing chains for first-pass content generation."""

    def __init__(
        self,
        chain: Any,
        method_name: str,
        ai_client: Optional[AIClient] = None,
    ):
        super().__init__(
            name="drafter",
            system_prompt="",
            output_schema={},
            ai_client=ai_client,
        )
        self.chain = chain
        self.method_name = method_name

    async def run(self, context: dict) -> AgentResult:
        """Delegate to existing chain method — NO modifications to chain."""
        start = time.monotonic_ns()
        method = getattr(self.chain, self.method_name)

        # Build kwargs from context, matching chain method signatures
        kwargs = self._build_chain_kwargs(context)
        result = await method(**kwargs)

        # Normalize result to dict
        if isinstance(result, str):
            content = {"html": result}
        elif isinstance(result, tuple):
            content = {"valid": result[0], "details": result[1]}
        elif isinstance(result, dict):
            content = result
        else:
            content = {"result": str(result)}

        # Heuristic draft confidence from evidence coverage
        draft_confidence = self._compute_draft_confidence(context, content)

        return self._timed_result(
            start_ns=start,
            content=content,
            metadata={
                "agent": self.name,
                "chain": type(self.chain).__name__,
                "method": self.method_name,
                "draft_confidence": draft_confidence,
            },
        )

    async def revise(self, draft: AgentResult, feedback: dict, revision_scope: Optional[dict] = None) -> AgentResult:
        """Revise using AIClient with priority-ordered feedback.

        v2: structures feedback by priority, explicitly lists fabricated
        claims for removal, and provides section-level revision targets.

        Args:
            draft: The original draft to revise.
            feedback: Structured feedback from critic, optimizer, fact-checker.
            revision_scope: Optional targeted revision scope with keys:
                ``dimensions`` — list of quality dimensions to focus on (e.g. ["impact", "clarity"])
                ``issues`` — ranked issues list from critic to prioritise
        """
        start = time.monotonic_ns()

        revision_template = ""
        if _REVISION_PROMPT_PATH.exists():
            revision_template = _REVISION_PROMPT_PATH.read_text()

        # Extract and prioritise critic issues
        critic_fb = feedback.get("critic", {})
        critical_issues = critic_fb.get("critical_issues", []) if isinstance(critic_fb, dict) else []
        prioritised_issues = sorted(
            critical_issues,
            key=lambda x: {"critical": 0, "high": 1, "medium": 2}.get(
                x.get("severity", "medium"), 3
            ),
        ) if isinstance(critical_issues, list) else []

        # Extract fabricated claims for explicit removal
        fact_flags = feedback.get("fact_check", [])
        fabricated = [
            f for f in fact_flags
            if isinstance(f, str) and f.startswith("fabricated:")
        ]

        # Build structured revision prompt
        revision_prompt = f"{revision_template}\n\n" if revision_template else ""
        revision_prompt += f"## Original Draft\n{json.dumps(draft.content, indent=2)[:5000]}\n\n"

        # v4: targeted revision scope — focus on specific dimensions/issues
        if revision_scope:
            dims = revision_scope.get("dimensions", [])
            scoped_issues = revision_scope.get("issues", [])
            if dims:
                revision_prompt += "## REVISION FOCUS (address these dimensions ONLY)\n"
                revision_prompt += f"Target dimensions: {', '.join(dims)}\n"
                revision_prompt += "Leave sections unrelated to these dimensions UNCHANGED.\n\n"
            if scoped_issues:
                revision_prompt += "## PRIORITY ISSUES (from critic ranking)\n"
                for i, issue in enumerate(scoped_issues[:8], 1):
                    sev = issue.get("severity", "medium")
                    dim = issue.get("dimension", "general")
                    txt = issue.get("issue", "")
                    revision_prompt += f"{i}. [{sev.upper()}] {dim}: {txt}\n"
                revision_prompt += "\n"

        # v3: include evidence ledger so drafter can cite evidence
        evidence_prompt = feedback.get("evidence_ledger_prompt", "")
        if evidence_prompt:
            revision_prompt += f"{evidence_prompt}\n\n"
            revision_prompt += (
                "IMPORTANT: Every material claim in the revised document MUST map to an "
                "evidence item above. Use evidence IDs (ev_...) when inserting new claims. "
                "Do NOT add claims that have no corresponding evidence item.\n\n"
            )

        # v3: include citation feedback
        citations = feedback.get("citations", [])
        unsupported = [c for c in citations if c.get("classification") == "fabricated"]
        if unsupported:
            revision_prompt += "## UNSUPPORTED CLAIMS (no evidence — REMOVE)\n"
            for c in unsupported[:10]:
                revision_prompt += f"- {c.get('claim_text', '')}\n"
            revision_prompt += "\n"

        if prioritised_issues:
            revision_prompt += "## Issues to Fix (priority order)\n"
            for i, issue in enumerate(prioritised_issues[:10], 1):
                section = issue.get("section", "general")
                severity = issue.get("severity", "medium")
                text = issue.get("issue", "") or issue.get("suggestion", "")
                revision_prompt += f"{i}. [{severity.upper()}] Section: {section} — {text}\n"
            revision_prompt += "\n"

        if fabricated:
            revision_prompt += "## FABRICATED CLAIMS — REMOVE THESE (do NOT rephrase)\n"
            for f in fabricated[:10]:
                revision_prompt += f"- {f.replace('fabricated: ', '')}\n"
            revision_prompt += "\n"

        optimizer_fb = feedback.get("optimizer", {})
        if optimizer_fb:
            missing_kws = []
            suggestions = []
            if isinstance(optimizer_fb, dict):
                kw_analysis = optimizer_fb.get("keyword_analysis", {})
                missing_kws = kw_analysis.get("missing", []) if isinstance(kw_analysis, dict) else []
                suggestions = optimizer_fb.get("suggestions", [])
            revision_prompt += "## Keyword Insertions (weave naturally)\n"
            if missing_kws:
                revision_prompt += f"Missing keywords: {', '.join(missing_kws[:10])}\n"
            if suggestions and isinstance(suggestions, list):
                for s in suggestions[:5]:
                    if isinstance(s, dict):
                        revision_prompt += f"- {s.get('text', '')}\n"
            revision_prompt += "\n"

        revision_prompt += (
            "Return the revised document as JSON with the same structure as the original draft.\n"
            "PRESERVE all verified facts. REMOVE fabricated claims. ADDRESS issues by priority."
        )

        result = await self.ai_client.complete_json(
            system=REVISION_SYSTEM_PROMPT,
            prompt=revision_prompt,
            max_tokens=6000,
            temperature=0.4,
            task_type="drafting",
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            metadata={
                "agent": self.name,
                "action": "revision",
                "issues_addressed": len(prioritised_issues),
                "revision_scope": revision_scope,
            },
        )

    @staticmethod
    def _compute_draft_confidence(context: dict, content: dict) -> float:
        """Heuristic draft confidence based on input evidence coverage.

        Returns a score 0.0–1.0 indicating how well-grounded the draft should
        be given the available inputs. Low confidence signals the orchestrator
        to consider re-research before revision.
        """
        signals = 0
        total = 5

        # 1. User profile provided and non-trivial
        profile = context.get("user_profile", {})
        if profile and isinstance(profile, dict) and len(profile) >= 3:
            signals += 1

        # 2. JD / job description present
        if context.get("jd_text") or context.get("job_requirements"):
            signals += 1

        # 3. Company intel available
        if context.get("company_intel") or context.get("company_info"):
            signals += 1

        # 4. Gap analysis / research results fed in
        if context.get("gap_analysis") or context.get("research_context"):
            signals += 1

        # 5. Content produced non-trivially (has content longer than placeholder)
        html = content.get("html", "")
        if isinstance(html, str) and len(html) > 200:
            signals += 1
        elif not html:
            # Check non-html content
            text_len = sum(len(str(v)) for v in content.values() if isinstance(v, str))
            if text_len > 200:
                signals += 1

        return round(signals / total, 2)

    def _build_chain_kwargs(self, context: dict) -> dict:
        """Map pipeline context to chain method keyword arguments.

        Uses inspect.signature to only pass parameters the target method accepts,
        avoiding 'unexpected keyword argument' errors for methods that don't
        accept all context fields (e.g. cover letter doesn't use resume_text).
        """
        import inspect

        method = getattr(self.chain, self.method_name)
        sig = inspect.signature(method)
        accepted_params = set(sig.parameters.keys()) - {"self"}

        kwargs = {}
        field_map = {
            "user_profile": "user_profile",
            "job_title": "job_title",
            "company": "company",
            "jd_text": "jd_text",
            "gap_analysis": "gap_analysis",
            "resume_text": "resume_text",
            "company_intel": "company_intel",
            "benchmark": "benchmark",
            "benchmark_data": "benchmark_data",
            "strengths": "strengths",
            "company_info": "company_info",
            "projects": "projects",
        }
        # Some chains use different parameter names for the same context data
        alias_map = {
            "jd_text": "job_description",
            "benchmark_data": "benchmark",
        }
        for ctx_key, param_name in field_map.items():
            if ctx_key in context and param_name in accepted_params:
                kwargs[param_name] = context[ctx_key]
            elif ctx_key in context and ctx_key in alias_map and alias_map[ctx_key] in accepted_params:
                kwargs[alias_map[ctx_key]] = context[ctx_key]

        return kwargs

    # ── v3: Parallel sub-agent support ─────────────────────────────────

    async def run_with_sub_agents(self, context: dict, draft: AgentResult) -> dict:
        """Run tone calibrator + keyword strategist in parallel on a completed draft.

        Returns a dict with tone and keyword feedback that can be merged into
        the revision feedback. This is called by the orchestrator between
        drafting and evaluation, or during revision.
        """
        draft_text = json.dumps(draft.content)[:4000]

        tone_ctx = {
            "draft_text": draft_text,
            "company_culture": context.get("company_culture", ""),
            "seniority_level": context.get("seniority_level", "mid"),
            "target_tone": context.get("target_tone", ""),
        }
        kw_ctx = {
            "draft_text": draft_text,
            "jd_text": context.get("jd_text", ""),
        }

        tone_agent = ToneCalibratorSubAgent(ai_client=self.ai_client)
        kw_agent = KeywordStrategistSubAgent(ai_client=self.ai_client)

        coord = SubAgentCoordinator([tone_agent, kw_agent])
        results = await coord.gather({})  # Sub-agents use their own ctx

        # Run them manually since they need different contexts
        tone_result, kw_result = await asyncio.gather(
            tone_agent.safe_run(tone_ctx),
            kw_agent.safe_run(kw_ctx),
        )

        feedback: dict[str, Any] = {}
        if tone_result.ok:
            feedback["tone_calibration"] = tone_result.data
        if kw_result.ok:
            feedback["keyword_strategy"] = kw_result.data

        return feedback
