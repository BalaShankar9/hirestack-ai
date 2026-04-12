"""
SectionDrafterSubAgent — drafts individual document sections in parallel.

Takes a section specification (section_name, requirements, evidence) and
produces a focused draft for that section. Multiple instances run in
parallel to draft all sections concurrently.
"""
from __future__ import annotations

import json
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient


class SectionDrafterSubAgent(SubAgent):
    """
    Drafts a single section of a document (e.g. "Professional Summary",
    "Work Experience", "Skills"). Receives section-specific context and
    evidence, returns a focused section draft.
    """

    def __init__(
        self,
        section_name: str = "",
        ai_client: Optional[AIClient] = None,
    ):
        super().__init__(
            name=f"section_drafter:{section_name}" if section_name else "section_drafter",
            ai_client=ai_client,
        )
        self.section_name = section_name

    async def run(self, context: dict) -> SubAgentResult:
        section_name = self.section_name or context.get("section_name", "")
        if not section_name:
            return SubAgentResult(agent_name=self.name, error="No section_name")

        # Build section-focused prompt
        requirements = context.get("section_requirements", "")
        evidence_items = context.get("evidence_items", [])
        jd_keywords = context.get("jd_keywords", [])
        user_profile = context.get("user_profile", {})
        tone = context.get("tone", "professional")

        evidence_text = ""
        if evidence_items:
            for ev in evidence_items[:10]:
                fact = ev.get("fact", "") if isinstance(ev, dict) else str(ev)
                evidence_text += f"- {fact}\n"

        prompt = (
            f"Draft the '{section_name}' section of a career document.\n\n"
            f"## Requirements\n{requirements}\n\n"
            f"## Available Evidence (use ONLY these facts)\n{evidence_text}\n"
            f"## Target Keywords (incorporate naturally)\n{', '.join(jd_keywords[:15])}\n\n"
            f"## Tone: {tone}\n\n"
            f"Return the section content as JSON: "
            f'{{"section_name": "{section_name}", "content": "<html content>", '
            f'"keywords_used": [...], "evidence_cited": [...]}}'
        )

        try:
            result = await self.ai_client.complete_json(
                system=(
                    "You are a section-level document drafter. Write ONE section of a career document. "
                    "Use ONLY the provided evidence. NEVER fabricate facts. "
                    "Naturally incorporate target keywords where truthful."
                ),
                prompt=prompt,
                max_tokens=2000,
                temperature=0.5,
                task_type="drafting",
            )
        except Exception as exc:
            return SubAgentResult(agent_name=self.name, error=str(exc))

        return SubAgentResult(
            agent_name=self.name,
            data={
                "section_name": section_name,
                "content": result.get("content", ""),
                "keywords_used": result.get("keywords_used", []),
                "evidence_cited": result.get("evidence_cited", []),
            },
            confidence=0.75,
        )
