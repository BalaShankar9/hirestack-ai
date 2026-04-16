"""
ApplicationStrategyAgent — LLM-powered strategic application guidance.

Takes the synthesized company profile and raw intel, then generates
actionable application strategy: tone, keywords, hooks, differentiators,
interview prep, and questions to ask.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import structlog

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.strategy")

_SYSTEM = """You are an elite career strategist and application coach. Given comprehensive
company intelligence, you produce specific, actionable application strategy.

Rules:
- Every recommendation must be backed by data from the intel.
- Keywords must come from the company's actual ecosystem, not generic terms.
- Cover letter hooks must reference real company facts.
- Interview questions must demonstrate genuine knowledge.
- Be specific: "mention their Series B from 2025" not "mention their funding".
Return ONLY valid JSON."""

_PROMPT = """Generate application strategy for this role based on the gathered intelligence.

COMPANY: {company}
JOB TITLE: {job_title}

=== COMPANY PROFILE ===
{company_profile}

=== JD ANALYSIS ===
{jd_analysis}

=== MARKET INTEL ===
{market_intel}

=== CAREERS INTEL ===
{careers_intel}

Return JSON:
{{
  "tone": "What tone to use — formal/conversational/technical/passionate",
  "tone_reasoning": "Why this tone based on company data",
  "keywords_to_use": ["Exact terms FROM THEIR ecosystem"],
  "values_to_emphasize": ["Personal values that verifiably align with company"],
  "things_to_mention": ["Specific facts to reference (real products, real news, real values)"],
  "things_to_avoid": ["Topics/styles/claims that won't resonate and why"],
  "differentiator_opportunities": ["How to stand out based on what we know about them"],
  "cover_letter_hooks": [
    {{
      "hook": "Opening sentence idea",
      "based_on": "What intel this is based on"
    }}
  ],
  "interview_prep_topics": [
    {{
      "topic": "Discussion topic",
      "likely_because": "Why they'd ask about this",
      "prepare": "What to prepare"
    }}
  ],
  "questions_to_ask": [
    {{
      "question": "Smart question for interviewer",
      "shows": "What this demonstrates about you"
    }}
  ],
  "application_timing": "Best time to apply if signals available",
  "networking_angles": ["Ways to connect with people at the company"],
  "ats_tips": ["ATS-specific optimization based on their platform"]
}}"""


class ApplicationStrategyAgent(SubAgent):
    """Strategic application guidance — hooks, keywords, differentiators, prep."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="application_strategy", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company", "")
        job_title = context.get("job_title", "")
        on_event = context.get("on_event")

        raw = context.get("raw_intel", {})
        company_profile = json.dumps(raw.get("company_profile", {}), default=str)[:5000]
        jd_analysis = json.dumps(raw.get("jd_intel", {}), default=str)[:3000]
        market_intel = json.dumps(raw.get("market_position", {}), default=str)[:2000]
        careers_intel = json.dumps(raw.get("careers_intel", {}), default=str)[:2000]

        if on_event:
            await _emit(on_event, "Building application strategy from intel…", "running", "strategy")

        prompt = _PROMPT.format(
            company=company,
            job_title=job_title,
            company_profile=company_profile or "Not available",
            jd_analysis=jd_analysis or "Not available",
            market_intel=market_intel or "Not available",
            careers_intel=careers_intel or "Not available",
        )

        try:
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=_SYSTEM,
                max_tokens=3000,
                temperature=0.3,
                task_type="reasoning",
            )
        except Exception as e:
            logger.warning("strategy_synthesis_failed", error=str(e)[:200])
            return SubAgentResult(agent_name=self.name, error=f"Strategy LLM failed: {str(e)[:200]}")

        if on_event:
            hook_count = len(result.get("cover_letter_hooks", []))
            kw_count = len(result.get("keywords_to_use", []))
            await _emit(
                on_event,
                f"Strategy complete: {kw_count} keywords, {hook_count} cover letter hooks.",
                "completed", "strategy",
                metadata={"keywords": kw_count, "hooks": hook_count},
            )

        # Build evidence
        evidence_items: list[dict] = []
        for kw in result.get("keywords_to_use", [])[:10]:
            evidence_items.append({
                "fact": f"Strategic keyword: {kw}",
                "source": "strategy:keywords",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })
        for mention in result.get("things_to_mention", [])[:5]:
            evidence_items.append({
                "fact": f"Mention in application: {mention}",
                "source": "strategy:mentions",
                "tier": "INFERRED",
                "sub_agent": self.name,
            })

        return SubAgentResult(
            agent_name=self.name,
            data=result,
            evidence_items=evidence_items,
            confidence=0.80,
        )


async def _emit(callback, message, status, source, url=None, metadata=None):
    payload: dict[str, Any] = {"stage": "recon", "status": status, "message": message, "source": source}
    if url:
        payload["url"] = url
    if metadata:
        payload["metadata"] = metadata
    try:
        maybe = callback(payload)
        if asyncio.iscoroutine(maybe):
            await maybe
    except Exception:
        pass
