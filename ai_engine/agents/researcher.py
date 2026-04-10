"""
Researcher Agent — retrieval agent with tool loop.

Gathers evidence from JD, company context, user profile, and stored memory.
Runs a tool-calling loop until coverage_score meets threshold or max steps.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import structlog

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import RESEARCHER_SCHEMA
from ai_engine.agents.tools import ToolRegistry, build_researcher_tools
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.agents.researcher")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "researcher_system.md"

# Tool-loop planning schema (what the LLM returns each step)
_PLAN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "next_tool": {"type": "string"},
        "tool_args": {"type": "object"},
        "done": {"type": "boolean"},
    },
    "required": ["reasoning", "done"],
}


class ResearcherAgent(BaseAgent):
    """Retrieval agent — gathers context until coverage is sufficient."""

    MAX_TOOL_STEPS = 5
    COVERAGE_THRESHOLD = 0.7

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        tools: Optional[ToolRegistry] = None,
    ):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="researcher",
            system_prompt=system_prompt,
            output_schema=RESEARCHER_SCHEMA,
            ai_client=ai_client,
        )
        self.tools = tools or build_researcher_tools()

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()
        jd_text = context.get("jd_text", "")
        job_title = context.get("job_title", "")
        company = context.get("company", "")
        user_profile = context.get("user_profile", {})
        memories = context.get("agent_memories", [])

        # Working memory — accumulates tool results across loop iterations
        working_memory: dict = {
            "job_title": job_title,
            "company": company,
            "jd_length": len(jd_text),
            "profile_available": bool(user_profile),
            "tool_results": {},
        }

        # ── Tool loop ──────────────────────────────────────────────
        available_tools_desc = self.tools.describe_for_llm()
        steps_taken = 0

        for step in range(self.MAX_TOOL_STEPS):
            plan_prompt = (
                f"You are a research agent gathering context for a career document.\n\n"
                f"## Current State\n"
                f"Job Title: {job_title}\n"
                f"Company: {company}\n"
                f"JD available: {bool(jd_text)} ({len(jd_text)} chars)\n"
                f"Profile available: {bool(user_profile)}\n"
                f"Tools already called: {list(working_memory['tool_results'].keys())}\n"
                f"Steps remaining: {self.MAX_TOOL_STEPS - step}\n\n"
                f"## Available Tools\n{available_tools_desc}\n\n"
                f"## Tool Results So Far\n{json.dumps(working_memory['tool_results'], indent=2)[:3000]}\n\n"
                f"Decide: should you call another tool, or are you done gathering context?\n"
                f"If calling a tool, specify 'next_tool' and 'tool_args'.\n"
                f"If done, set 'done': true."
            )

            plan = await self.ai_client.complete_json(
                prompt=plan_prompt,
                system="You are a research planning agent. Decide which tool to call next or if research is sufficient.",
                max_tokens=500,
                temperature=0.2,
                schema=_PLAN_SCHEMA,
            )

            if plan.get("done", False):
                break

            tool_name = plan.get("next_tool", "")
            tool_args = plan.get("tool_args", {})
            tool = self.tools.get(tool_name)

            if not tool:
                logger.warning("researcher_unknown_tool", tool=tool_name, step=step)
                break

            # Inject context values that the tool needs
            if "jd_text" in tool.parameters.get("properties", {}) and "jd_text" not in tool_args:
                tool_args["jd_text"] = jd_text
            if "user_profile" in tool.parameters.get("properties", {}) and "user_profile" not in tool_args:
                tool_args["user_profile"] = user_profile
            if "document_text" in tool.parameters.get("properties", {}) and "document_text" not in tool_args:
                tool_args["document_text"] = self._profile_to_document_text(
                    user_profile,
                    working_memory["tool_results"].get("extract_profile_evidence"),
                )

            try:
                tool_result = await tool.execute(**tool_args)
                working_memory["tool_results"][tool_name] = tool_result
                steps_taken += 1
            except Exception as e:
                logger.warning("researcher_tool_failed", tool=tool_name, error=str(e))
                working_memory["tool_results"][tool_name] = {"error": str(e)}

        # ── Synthesis — produce final research from all gathered evidence ──
        memories_text = ""
        if memories:
            memories_text = f"\nUser Preferences (from memory):\n{json.dumps(memories[:5], default=str)[:1000]}\n"

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
            f"Produce a comprehensive research context including coverage_score (0-1)."
        )

        result = await self.ai_client.complete_json(
            prompt=synthesis_prompt,
            system=self.system_prompt,
            max_tokens=2048,
            temperature=0.3,
            schema=self.output_schema,
        )

        result["tools_used"] = list(working_memory["tool_results"].keys())
        result["tool_steps"] = steps_taken

        return self._timed_result(
            start_ns=start,
            content=result,
            metadata={
                "agent": self.name,
                "jd_length": len(jd_text),
                "tool_steps": steps_taken,
                "tools_used": list(working_memory["tool_results"].keys()),
                "coverage_score": result.get("coverage_score", 0),
            },
        )

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
