"""
Researcher Agent — retrieval agent with deterministic-first tool loop.

Gathers evidence from JD, company context, user profile, and stored memory.
Runs a tool-calling loop until coverage_score meets threshold or max steps.

v2: deterministic tool ordering (always run core tools before LLM planning),
    explicit uncertainty exposure via coverage gaps, better stopping criteria.
v3: ResearchDepth modes, parallel core-tool execution, sub-agent coordinator,
    multi-pass verification, raised limits for thorough research.
"""
from __future__ import annotations

import asyncio
import json
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import RESEARCHER_SCHEMA
from ai_engine.agents.tools import ToolRegistry, build_researcher_tools, ToolPlan
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.agents.researcher")


def _truncate_dict(d: dict, max_chars: int = 1500) -> dict:
    """Truncate dict values for LLM context windows."""
    out = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > max_chars:
            out[k] = v[:max_chars] + "..."
        elif isinstance(v, dict):
            out[k] = _truncate_dict(v, max_chars // 2)
        elif isinstance(v, list) and len(str(v)) > max_chars:
            out[k] = v[:10]
        else:
            out[k] = v
    return out

_PROMPT_PATH = Path(__file__).parent / "prompts" / "researcher_system.md"

# Deterministic tool execution order — always run these first
_CORE_TOOLS = ["parse_jd", "extract_profile_evidence", "compute_keyword_overlap"]

# Web search tools that can safely execute in parallel
_WEB_TOOLS = [
    "search_company_info",
    "search_glassdoor_reviews",
    "search_linkedin_insights",
    "search_company_news",
    "search_competitor_landscape",
    "search_tech_blog",
]


class ResearchDepth(str, Enum):
    """Controls how deep and wide the researcher gathers evidence."""
    QUICK = "quick"           # Fast path: core tools only, minimal LLM planning
    THOROUGH = "thorough"     # Default: core + web + LLM planning, higher coverage bar
    EXHAUSTIVE = "exhaustive" # Maximum depth: all tools, max steps, verification pass


# Per-depth configuration: (max_tool_steps, coverage_threshold, run_web_tools, run_verification)
_DEPTH_CONFIG: dict[ResearchDepth, tuple[int, float, bool, bool]] = {
    ResearchDepth.QUICK:      (5,  0.70, False, False),
    ResearchDepth.THOROUGH:   (12, 0.88, True,  False),
    ResearchDepth.EXHAUSTIVE: (20, 0.95, True,  True),
}


class ResearcherAgent(BaseAgent):
    """Retrieval agent with deterministic-first tool execution.

    v3 improvements:
    - ResearchDepth modes: QUICK / THOROUGH / EXHAUSTIVE
    - Core tools run in parallel (Phase A: parse_jd ∥ extract_profile,
      Phase B: keyword_overlap depends on A)
    - Web search tools run in parallel (Phase C)
    - Sub-agent coordinator mode (when sub-agents available)
    - Multi-pass verification for EXHAUSTIVE depth
    - Raised limits: up to 20 tool steps, 0.95 coverage threshold
    """

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        tools: Optional[ToolRegistry] = None,
        db: Any = None,
        research_depth: ResearchDepth = ResearchDepth.THOROUGH,
    ):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="researcher",
            system_prompt=system_prompt,
            output_schema=RESEARCHER_SCHEMA,
            ai_client=ai_client,
        )
        self._db = db
        self.tools = tools or build_researcher_tools(db=db)
        self.depth = research_depth
        depth_cfg = _DEPTH_CONFIG[research_depth]
        self.MAX_TOOL_STEPS = depth_cfg[0]
        self.COVERAGE_THRESHOLD = depth_cfg[1]
        self._run_web_tools = depth_cfg[2]
        self._run_verification = depth_cfg[3]
        # Sub-agents (set externally by coordinator)
        self._sub_agents: list[Any] = []

    async def run(self, context: dict) -> AgentResult:
        # v3: if sub-agents are available, delegate to coordinator mode
        if self._sub_agents:
            return await self._run_coordinated(context)
        return await self._run_monolithic(context)

    async def _run_monolithic(self, context: dict) -> AgentResult:
        """Original monolithic run — upgraded with parallel tools & depth modes."""
        start = time.monotonic_ns()
        jd_text = context.get("jd_text", "")
        job_title = context.get("job_title", "")
        company = context.get("company", "")
        user_profile = context.get("user_profile", {})
        memories = context.get("agent_memories", [])
        user_id = context.get("user_id", "")

        # Rebuild tools with user_id if available (enables DB-backed tools)
        if user_id and self._db and not self.tools.get("query_user_history"):
            self.tools = build_researcher_tools(db=self._db, user_id=user_id)

        # Working memory — accumulates tool results across loop iterations
        working_memory: dict = {
            "job_title": job_title,
            "company": company,
            "jd_length": len(jd_text),
            "profile_available": bool(user_profile),
            "tool_results": {},
        }

        # ── Phase 1A: Parallel deterministic tools (parse_jd ∥ extract_profile) ─
        steps_taken = 0
        phase_a_tasks = []
        phase_a_names = []

        for tool_name in ["parse_jd", "extract_profile_evidence"]:
            tool = self.tools.get(tool_name)
            if not tool:
                continue
            tool_props = tool.parameters.get("properties", {})
            tool_args: dict = {}
            if "jd_text" in tool_props:
                tool_args["jd_text"] = jd_text
            if "user_profile" in tool_props:
                tool_args["user_profile"] = user_profile
            if "jd_text" in tool_props and not jd_text:
                continue
            if "user_profile" in tool_props and not user_profile:
                continue
            phase_a_tasks.append(tool.execute(**tool_args))
            phase_a_names.append(tool_name)

        if phase_a_tasks:
            phase_a_results = await asyncio.gather(*phase_a_tasks, return_exceptions=True)
            for name, result in zip(phase_a_names, phase_a_results):
                if isinstance(result, Exception):
                    logger.warning("researcher_core_tool_failed", tool=name, error=str(result))
                    working_memory["tool_results"][name] = {"error": str(result)}
                else:
                    working_memory["tool_results"][name] = result
                steps_taken += 1

        # ── Phase 1B: keyword overlap (depends on Phase A outputs) ────────
        kw_tool = self.tools.get("compute_keyword_overlap")
        if kw_tool and jd_text:
            try:
                doc_text = self._profile_to_document_text(
                    user_profile,
                    working_memory["tool_results"].get("extract_profile_evidence"),
                )
                kw_result = await kw_tool.execute(document_text=doc_text, jd_text=jd_text)
                working_memory["tool_results"]["compute_keyword_overlap"] = kw_result
                steps_taken += 1
            except Exception as e:
                logger.warning("researcher_core_tool_failed", tool="compute_keyword_overlap", error=str(e))
                working_memory["tool_results"]["compute_keyword_overlap"] = {"error": str(e)}

        # ── Phase 1C: Parallel web search tools (if depth allows) ─────────
        if self._run_web_tools and company:
            web_tasks = []
            web_names = []
            for tool_name in _WEB_TOOLS:
                tool = self.tools.get(tool_name)
                if not tool:
                    continue
                tool_props = tool.parameters.get("properties", {})
                tool_args = {}
                if "company_name" in tool_props:
                    tool_args["company_name"] = company
                if "company" in tool_props:
                    tool_args["company"] = company
                if "job_title" in tool_props:
                    tool_args["job_title"] = job_title
                if "jd_text" in tool_props:
                    tool_args["jd_text"] = jd_text
                if "industry" in tool_props:
                    tool_args["industry"] = ""  # let tool infer
                web_tasks.append(tool.execute(**tool_args))
                web_names.append(tool_name)

            if web_tasks:
                web_results = await asyncio.gather(*web_tasks, return_exceptions=True)
                for name, result in zip(web_names, web_results):
                    if isinstance(result, Exception):
                        logger.warning("researcher_web_tool_failed", tool=name, error=str(result))
                        working_memory["tool_results"][name] = {"error": str(result)}
                    else:
                        working_memory["tool_results"][name] = result
                    steps_taken += 1

        # ── Phase 1.5: LLM-driven planning loop (agentic) ────────
        #   The LLM decides what additional tools to call based on
        #   what's already in working memory.  Runs until the LLM
        #   says "done", coverage is sufficient, or we hit max steps.
        remaining_steps = self.MAX_TOOL_STEPS - steps_taken
        plan_context = (
            f"Job Title: {job_title}\nCompany: {company}\n"
            f"JD snippet: {jd_text[:500]}\n"
            f"Profile available: {bool(user_profile)}\n"
            f"Task: gather all research context needed for high-quality document generation."
        )

        # If targeted re-research was requested, inject focus areas into planning context
        research_targets = context.get("_research_targets", {})
        if research_targets:
            target_categories = research_targets.get("categories", [])
            plan_context += (
                f"\n\nPRIORITY: Targeted re-research requested. "
                f"Focus on verifying and gathering evidence for these categories: {target_categories}. "
                f"Claims in these areas were flagged as fabricated or unverifiable. "
                f"Prioritize tools that can validate or replace these specific claims."
            )

        for _step in range(remaining_steps):
            plan: ToolPlan = await self.tools.select_and_execute(
                ai_client=self.ai_client,
                context=plan_context,
                working_memory=working_memory["tool_results"],
                system_prompt=(
                    "You are a research planner for a career document AI. "
                    "Decide which tools to call to fill knowledge gaps. "
                    "Always set done=true when working memory is sufficient."
                ),
            )

            if plan.done and not plan.calls:
                logger.info(
                    "researcher_planning_done",
                    step=_step,
                    coverage=plan.coverage_estimate,
                    reason=plan.reasoning,
                )
                break

            for tool_call in plan.calls:
                tool = self.tools.get(tool_call.tool_name)
                if not tool:
                    continue

                # Merge context-derived args with LLM-selected args
                call_args = dict(tool_call.arguments)
                tool_props = tool.parameters.get("properties", {})
                if "jd_text" in tool_props and "jd_text" not in call_args:
                    call_args["jd_text"] = jd_text
                if "user_profile" in tool_props and "user_profile" not in call_args:
                    call_args["user_profile"] = user_profile
                if "company_name" in tool_props and "company_name" not in call_args:
                    call_args["company_name"] = company

                try:
                    tool_result = await tool.execute(**call_args)
                    working_memory["tool_results"][tool_call.tool_name] = tool_result
                    steps_taken += 1
                except Exception as e:
                    logger.warning(
                        "researcher_planned_tool_failed",
                        tool=tool_call.tool_name, error=str(e),
                    )
                    working_memory["tool_results"][tool_call.tool_name] = {"error": str(e)}

            if plan.coverage_estimate >= self.COVERAGE_THRESHOLD:
                logger.info(
                    "researcher_coverage_met",
                    coverage=plan.coverage_estimate,
                    steps=steps_taken,
                )
                break

        # ── Phase 2: Coverage gap analysis ────────────────────────
        coverage_gaps: list[str] = []
        if not jd_text:
            coverage_gaps.append("No job description provided — keyword analysis limited")
        if not user_profile:
            coverage_gaps.append("No user profile provided — cannot assess fit")
        if not company:
            coverage_gaps.append("No company name — culture/tone inference limited")

        jd_result = working_memory["tool_results"].get("parse_jd", {})
        if jd_result and not jd_result.get("top_keywords"):
            coverage_gaps.append("JD parsing yielded no keywords — JD may be too short")

        # ── Synthesis — produce final research from all gathered evidence ──
        memories_text = ""
        if memories:
            # v3: recall more memories for thorough/exhaustive research
            mem_limit = 15 if self.depth != ResearchDepth.QUICK else 5
            memories_text = f"\nUser Preferences (from memory):\n{json.dumps(memories[:mem_limit], default=str)[:2000]}\n"

        synthesis_prompt = (
            f"Synthesize a research context from the gathered evidence.\n\n"
            f"Job Title: {job_title}\n"
            f"Company: {company}\n"
            f"Job Description:\n{jd_text[:3000]}\n\n"
            f"User Profile Summary:\n"
            f"- Skills: {', '.join(s.get('name', s) if isinstance(s, dict) else str(s) for s in (user_profile.get('skills') or [])[:20])}\n"
            f"- Experience: {len(user_profile.get('experience') or [])} roles\n"
            f"- Education: {len(user_profile.get('education') or [])} entries\n"
            f"{memories_text}\n"
            f"## Tool Results\n{json.dumps(working_memory['tool_results'], indent=2)[:4000]}\n\n"
            f"## Coverage Gaps (be transparent about these)\n"
            + ("\n".join(f"- {g}" for g in coverage_gaps) if coverage_gaps else "- None — full context available")
            + "\n\n"
            f"Produce a comprehensive research context.\n"
            f"Set coverage_score (0-1) based on actual data availability:\n"
            f"- 0.9-1.0: JD + profile + company all available with rich data\n"
            f"- 0.6-0.8: Some gaps but enough to produce a good document\n"
            f"- 0.3-0.5: Significant gaps that will limit quality\n"
            f"- 0.0-0.2: Insufficient data for meaningful output"
        )

        result = await self.ai_client.complete_json(
            prompt=synthesis_prompt,
            system=self.system_prompt,
            max_tokens=2048,
            temperature=0.3,
            schema=self.output_schema,
            task_type="research",
        )

        result["tools_used"] = list(working_memory["tool_results"].keys())
        result["tool_steps"] = steps_taken
        result["coverage_gaps"] = coverage_gaps
        result["tool_results"] = working_memory["tool_results"]
        result["research_depth"] = self.depth.value

        # ── Phase 4 (EXHAUSTIVE only): Verification pass ─────────
        verification_flags: list[str] = []
        if self._run_verification and steps_taken > 3:
            verification_flags = self._verify_intel_consistency(working_memory["tool_results"])
            result["verification_flags"] = verification_flags

        return self._timed_result(
            start_ns=start,
            content=result,
            metadata={
                "agent": self.name,
                "jd_length": len(jd_text),
                "tool_steps": steps_taken,
                "tools_used": list(working_memory["tool_results"].keys()),
                "coverage_score": result.get("coverage_score", 0),
                "coverage_gaps": len(coverage_gaps),
                "research_depth": self.depth.value,
                "verification_flags": len(verification_flags),
            },
        )

    async def _run_coordinated(self, context: dict) -> AgentResult:
        """v3: Coordinate parallel sub-agents for maximum research depth.

        Flow:
          1. Fan-out: all sub-agents run in parallel
          2. Collect: gather results (error-tolerant)
          3. Synthesize: LLM merges all sub-agent outputs
          4. Verify: cross-reference consistency
          5. Score: per-sub-agent coverage contributes to total
        """
        start = time.monotonic_ns()
        jd_text = context.get("jd_text", "")
        job_title = context.get("job_title", "")
        company = context.get("company", "")
        user_profile = context.get("user_profile", {})
        memories = context.get("agent_memories", [])

        # Fan-out to all sub-agents
        tasks = [sa.run(context) for sa in self._sub_agents]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results, tolerating failures
        sub_outputs: dict[str, dict] = {}
        failed_agents: list[str] = []
        total_latency = 0
        all_tools_used: list[str] = []

        for sa, result in zip(self._sub_agents, raw_results):
            agent_name = getattr(sa, "name", str(sa))
            if isinstance(result, Exception):
                logger.warning("sub_agent_failed", agent=agent_name, error=str(result))
                failed_agents.append(agent_name)
                continue
            sub_outputs[agent_name] = result.content
            total_latency = max(total_latency, result.latency_ms)
            all_tools_used.extend(result.metadata.get("tools_used", []))

        # Synthesize all sub-agent outputs into unified research context
        combined_data = json.dumps(
            {name: _truncate_dict(data, 1500) for name, data in sub_outputs.items()},
            default=str,
        )[:8000]

        mem_limit = 15 if self.depth != ResearchDepth.QUICK else 5
        memories_text = ""
        if memories:
            memories_text = f"\nUser Preferences (from memory):\n{json.dumps(memories[:mem_limit], default=str)[:2000]}\n"

        synthesis_prompt = (
            f"Synthesize a unified research context from {len(sub_outputs)} specialist sub-agent reports.\n\n"
            f"Job Title: {job_title}\nCompany: {company}\n"
            f"JD snippet: {jd_text[:1500]}\n"
            f"Profile available: {bool(user_profile)}\n"
            f"{memories_text}\n"
            f"## Sub-Agent Reports\n{combined_data}\n\n"
            f"## Failed Sub-Agents: {failed_agents or 'None'}\n\n"
            f"Produce a comprehensive research context. Weight each section by data quality.\n"
            f"Set coverage_score (0-1): deduct 0.15-0.20 per failed sub-agent."
        )

        result = await self.ai_client.complete_json(
            prompt=synthesis_prompt,
            system=self.system_prompt,
            max_tokens=3000,
            temperature=0.3,
            schema=self.output_schema,
            task_type="research",
        )

        # Merge sub-agent tool results into unified tool_results
        merged_tool_results: dict = {}
        for data in sub_outputs.values():
            if isinstance(data, dict) and "tool_results" in data:
                merged_tool_results.update(data["tool_results"])

        result["tools_used"] = list(set(all_tools_used))
        result["tool_steps"] = len(all_tools_used)
        result["tool_results"] = merged_tool_results
        result["research_depth"] = self.depth.value
        result["sub_agent_reports"] = list(sub_outputs.keys())
        result["failed_sub_agents"] = failed_agents

        # Verification pass
        verification_flags: list[str] = []
        if self._run_verification and merged_tool_results:
            verification_flags = self._verify_intel_consistency(merged_tool_results)
            result["verification_flags"] = verification_flags

        return self._timed_result(
            start_ns=start,
            content=result,
            metadata={
                "agent": self.name,
                "tool_steps": len(all_tools_used),
                "tools_used": list(set(all_tools_used)),
                "coverage_score": result.get("coverage_score", 0),
                "research_depth": self.depth.value,
                "sub_agents": len(self._sub_agents),
                "sub_agents_succeeded": len(sub_outputs),
                "sub_agents_failed": len(failed_agents),
                "verification_flags": len(verification_flags),
            },
        )

    @staticmethod
    def _verify_intel_consistency(tool_results: dict) -> list[str]:
        """Cross-reference gathered data for contradictions."""
        flags: list[str] = []

        # Check tech stack consistency between JD parse and company intel
        jd_data = tool_results.get("parse_jd", {})
        company_data = tool_results.get("search_company_info", {})
        if isinstance(jd_data, dict) and isinstance(company_data, dict):
            jd_keywords = set(jd_data.get("top_keywords", []))
            company_tech = set()
            tech_stack = company_data.get("tech_stack", [])
            if isinstance(tech_stack, list):
                company_tech = {t.lower() for t in tech_stack if isinstance(t, str)}
            if jd_keywords and company_tech:
                overlap = jd_keywords & company_tech
                if not overlap and len(jd_keywords) > 5:
                    flags.append(
                        "TECH_MISMATCH: JD keywords and company tech stack have no overlap "
                        "— JD may be for a different team or the company data is stale."
                    )

        # Check salary consistency
        salary_data = tool_results.get("search_salary_data", {})
        jd_salary = tool_results.get("analyze_jd_sentiment", {})
        if isinstance(salary_data, dict) and isinstance(jd_salary, dict):
            market_min = salary_data.get("salary_min", 0)
            jd_min = jd_salary.get("salary_min", 0)
            if market_min and jd_min and abs(market_min - jd_min) > 30000:
                flags.append(
                    f"SALARY_DISCREPANCY: Market data suggests ${market_min:,}+ "
                    f"but JD indicates ${jd_min:,}. Possible mismatch."
                )

        return flags

    @staticmethod
    def _profile_to_document_text(
        user_profile: dict,
        extracted_evidence: Optional[dict] = None,
    ) -> str:
        """Flatten profile data into document text for overlap analysis tools."""
        parts: list[str] = []

        if isinstance(extracted_evidence, dict) and extracted_evidence:
            for field in (
                "skills",
                "companies",
                "titles",
                "education",
                "certifications",
            ):
                values = extracted_evidence.get(field, [])
                if isinstance(values, list) and values:
                    parts.append(" ".join(str(value) for value in values if value))

        if not parts:
            for field in ("title", "summary", "headline"):
                value = user_profile.get(field)
                if isinstance(value, str) and value.strip():
                    parts.append(value)

            for skill in user_profile.get("skills") or []:
                if isinstance(skill, dict):
                    name = skill.get("name")
                    if name:
                        parts.append(str(name))
                elif skill:
                    parts.append(str(skill))

            for exp in user_profile.get("experience") or []:
                if isinstance(exp, dict):
                    for field in ("title", "company", "description"):
                        value = exp.get(field)
                        if isinstance(value, str) and value.strip():
                            parts.append(value)

        return "\n".join(parts) if parts else json.dumps(user_profile)
