"""
Researcher Agent — gathers context before drafting.

Analyzes job descriptions, company signals, and user profiles
to produce research context that shapes the Drafter's output.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import RESEARCHER_SCHEMA
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "researcher_system.md"


class ResearcherAgent(BaseAgent):
    """Gathers context: industry signals, culture, keywords."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="researcher",
            system_prompt=system_prompt,
            output_schema=RESEARCHER_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()
        jd_text = context.get("jd_text", "")
        job_title = context.get("job_title", "")
        company = context.get("company", "")
        user_profile = context.get("user_profile", {})
        memories = context.get("agent_memories", [])

        prompt = (
            f"Analyze this job posting and user profile to extract research context.\n\n"
            f"Job Title: {job_title}\n"
            f"Company: {company}\n"
            f"Job Description:\n{jd_text[:3000]}\n\n"
            f"User Profile Summary:\n"
            f"- Skills: {', '.join(s.get('name', s) if isinstance(s, dict) else str(s) for s in (user_profile.get('skills') or [])[:20])}\n"
            f"- Experience: {len(user_profile.get('experience') or [])} roles\n"
            f"- Education: {len(user_profile.get('education') or [])} entries\n"
        )
        if memories:
            prompt += f"\nUser Preferences (from memory):\n{memories[:5]}\n"

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=2048,
            temperature=0.3,
            schema=self.output_schema,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            metadata={"agent": self.name, "jd_length": len(jd_text)},
        )
