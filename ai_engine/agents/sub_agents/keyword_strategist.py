"""
KeywordStrategistSubAgent — optimizes keyword placement in documents.

Analyzes JD keywords, identifies optimal placement opportunities, and
provides insertion guidance that reads naturally.
"""
from __future__ import annotations

import json
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import _compute_keyword_overlap
from ai_engine.client import AIClient


class KeywordStrategistSubAgent(SubAgent):
    """
    Keyword strategy:
    - Compute current keyword coverage
    - Identify high-priority missing keywords
    - Suggest natural insertion points
    - Provide rewrite snippets for keyword incorporation
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="keyword_strategist", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        draft_text = context.get("draft_text", "")
        if not draft_text:
            draft_content = context.get("draft_content", {})
            draft_text = json.dumps(draft_content)[:4000] if draft_content else ""

        jd_text = context.get("jd_text", "")
        if not draft_text or not jd_text:
            return SubAgentResult(
                agent_name=self.name,
                error="Need both draft_text and jd_text",
            )

        # Deterministic overlap computation
        overlap = await _compute_keyword_overlap(
            document_text=draft_text, jd_text=jd_text,
        )

        missing = overlap.get("missing_keywords", [])
        current_pct = overlap.get("overlap_pct", 0)

        if not missing:
            return SubAgentResult(
                agent_name=self.name,
                data={
                    "overlap": overlap,
                    "strategy": "No missing keywords — coverage is excellent.",
                    "insertions": [],
                },
                confidence=0.90,
            )

        # Use LLM to produce natural insertion suggestions
        prompt = (
            f"You have a document draft and a list of missing keywords from the job description.\n"
            f"Current keyword overlap: {current_pct}%\n\n"
            f"## Missing Keywords (priority order)\n{', '.join(missing[:15])}\n\n"
            f"## Draft Excerpt\n{draft_text[:2500]}\n\n"
            f"For each missing keyword, suggest a natural insertion:\n"
            f"Return JSON: {{"
            f'"insertions": [{{"keyword": "...", "target_section": "...", "suggested_sentence": "...", "priority": "high|medium"}}], '
            f'"expected_new_overlap_pct": 0-100}}'
        )

        try:
            result = await self.ai_client.complete_json(
                system=(
                    "You are an ATS keyword strategist. Suggest natural keyword insertions "
                    "that improve ATS compatibility without sounding forced or fabricated. "
                    "ONLY suggest insertions for skills/experience the candidate actually has."
                ),
                prompt=prompt,
                max_tokens=1500,
                temperature=0.3,
                task_type="optimization",
            )
        except Exception as exc:
            return SubAgentResult(agent_name=self.name, error=str(exc))

        insertions = result.get("insertions", [])
        confidence = min(0.85, 0.50 + len(insertions) * 0.05)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "overlap": overlap,
                "insertions": insertions,
                "expected_new_overlap_pct": result.get("expected_new_overlap_pct", current_pct),
            },
            confidence=confidence,
        )
