"""
ToneCalibratorSubAgent — analyzes and adjusts document tone.

Evaluates the tone of a draft against the target company culture and
role seniority, then produces tone adjustment recommendations or
directly calibrated text.
"""
from __future__ import annotations

import json
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient


class ToneCalibratorSubAgent(SubAgent):
    """
    Tone analysis and calibration:
    - Detects current tone (formal/casual/assertive/humble)
    - Compares against company culture signals
    - Produces adjustment recommendations or rewritten text
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="tone_calibrator", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        draft_text = context.get("draft_text", "")
        if not draft_text:
            draft_content = context.get("draft_content", {})
            draft_text = json.dumps(draft_content)[:4000] if draft_content else ""
        if not draft_text:
            return SubAgentResult(agent_name=self.name, error="No draft text to calibrate")

        company_culture = context.get("company_culture", "")
        seniority = context.get("seniority_level", "mid")
        target_tone = context.get("target_tone", "")

        prompt = (
            f"Analyze the tone of this document draft and provide calibration guidance.\n\n"
            f"## Draft Text (excerpt)\n{draft_text[:3000]}\n\n"
            f"## Company Culture Signals\n{company_culture or 'Not available'}\n\n"
            f"## Role Seniority\n{seniority}\n\n"
            f"## Target Tone\n{target_tone or 'Match company culture'}\n\n"
            f"Return JSON: {{"
            f'"current_tone": "...", '
            f'"target_tone": "...", '
            f'"tone_match_score": 0.0-1.0, '
            f'"adjustments": [{{"section": "...", "current": "...", "recommended": "...", "reason": "..."}}], '
            f'"overall_recommendation": "..."}}'
        )

        try:
            result = await self.ai_client.complete_json(
                system=(
                    "You are a tone calibration specialist. Analyze document tone and "
                    "provide specific adjustment recommendations. Consider industry norms, "
                    "company culture, and role seniority."
                ),
                prompt=prompt,
                max_tokens=1500,
                temperature=0.3,
                task_type="critique",
            )
        except Exception as exc:
            return SubAgentResult(agent_name=self.name, error=str(exc))

        match_score = result.get("tone_match_score", 0.5)
        confidence = max(0.40, min(0.90, float(match_score)))

        return SubAgentResult(
            agent_name=self.name,
            data=result,
            confidence=confidence,
        )
