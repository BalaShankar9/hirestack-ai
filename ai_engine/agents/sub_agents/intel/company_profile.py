"""
CompanyProfileAgent — LLM-powered deep synthesis of company identity.

Takes raw data from website, GitHub, careers, and JD agents and produces
a comprehensive, structured company profile using LLM reasoning.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import structlog

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.company_profile")

_SYSTEM = """You are an elite corporate intelligence analyst. Given raw intelligence data
gathered from multiple sources about a company, you produce a comprehensive
company profile with verified facts only.

Rules:
- ONLY state what the data supports. Never fabricate company details.
- Mark confidence for each section: high / medium / low / unknown.
- Use real names, real products, real values — no generic filler.
- If data is insufficient, say "Insufficient data" rather than guessing.
Return ONLY valid JSON."""

_PROMPT = """Synthesize a comprehensive company profile from the following multi-source intelligence.

COMPANY: {company}
JOB TITLE: {job_title}

=== WEBSITE DATA ===
{website_data}

=== GITHUB DATA ===
{github_data}

=== CAREERS PAGE DATA ===
{careers_data}

=== JD ANALYSIS DATA ===
{jd_data}

Return a JSON object:
{{
  "company_overview": {{
    "name": "Official company name",
    "industry": "Primary industry",
    "sub_industry": "Specific niche",
    "size": "Startup / Scale-up / Enterprise / Corporation",
    "stage": "Pre-seed / Seed / Series A-C / Growth / Public / Bootstrapped",
    "founded": "Year or Unknown",
    "headquarters": "City, Country",
    "offices": ["other locations"],
    "website": "Main URL",
    "description": "2-3 sentence factual description",
    "section_confidence": "high/medium/low"
  }},
  "culture_and_values": {{
    "core_values": ["Values from actual data"],
    "mission_statement": "If found",
    "work_style": "Remote / Hybrid / On-site / Flexible",
    "work_environment": "Day-to-day culture description",
    "team_structure": "How teams are organized",
    "diversity_and_inclusion": "DEI signals",
    "employee_benefits": ["Benefits found"],
    "red_flags": ["Concerns identified"],
    "section_confidence": "high/medium/low"
  }},
  "tech_and_engineering": {{
    "tech_stack": ["All technologies"],
    "programming_languages": ["Languages"],
    "frameworks": ["Frameworks"],
    "infrastructure": ["Cloud, CI/CD, monitoring"],
    "methodologies": ["Agile, Scrum, etc."],
    "engineering_culture": "Engineering approach description",
    "open_source": "OSS involvement",
    "github_stats": {{
      "org_name": "",
      "public_repos": 0,
      "top_languages": [],
      "notable_repos": [],
      "activity_level": "Very Active / Active / Moderate / Low / None",
      "total_stars": 0,
      "culture_signals": []
    }},
    "section_confidence": "high/medium/low"
  }},
  "products_and_services": {{
    "main_products": ["Products identified"],
    "target_market": "B2B / B2C / Enterprise / Developer",
    "pricing_model": "Model or Unknown",
    "key_features": ["Features found"],
    "recent_launches": ["Recent updates"],
    "section_confidence": "high/medium/low"
  }},
  "market_position": {{
    "competitors": ["Direct competitors"],
    "differentiators": ["What sets them apart"],
    "market_trends": ["Industry trends"],
    "challenges": ["Challenges"],
    "growth_trajectory": "Trajectory assessment",
    "section_confidence": "high/medium/low"
  }},
  "recent_developments": {{
    "news_highlights": ["Recent developments"],
    "growth_signals": ["Growth indicators"],
    "leadership": ["Key leaders"],
    "awards_recognition": ["Awards"],
    "section_confidence": "high/medium/low"
  }},
  "hiring_intelligence": {{
    "hiring_volume": "Aggressive / Moderate / Selective",
    "interview_process": ["Inferred stages"],
    "interview_style": "Technical / Behavioral / Mixed",
    "team_hiring_for": "Target team",
    "seniority_signals": "Actual level they want",
    "salary_range": "If available",
    "must_have_skills": ["Non-negotiable"],
    "nice_to_have_skills": ["Preferred"],
    "hidden_requirements": ["Unstated but inferred"],
    "section_confidence": "high/medium/low"
  }}
}}"""


class CompanyProfileAgent(SubAgent):
    """LLM synthesis of all raw intel into structured company profile."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="company_profile", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company", "")
        job_title = context.get("job_title", "")
        on_event = context.get("on_event")

        # Gather raw data from sibling agents
        raw = context.get("raw_intel", {})
        website_data = json.dumps(raw.get("website_intel", {}), default=str)[:5000]
        github_data = json.dumps(raw.get("github_intel", {}), default=str)[:3000]
        careers_data = json.dumps(raw.get("careers_intel", {}), default=str)[:3000]
        jd_data = json.dumps(raw.get("jd_intel", {}), default=str)[:3000]

        if on_event:
            await _emit(on_event, "Synthesizing company profile from all sources…", "running", "analysis")

        prompt = _PROMPT.format(
            company=company,
            job_title=job_title,
            website_data=website_data or "Not available",
            github_data=github_data or "Not available",
            careers_data=careers_data or "Not available",
            jd_data=jd_data or "Not available",
        )

        try:
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=_SYSTEM,
                max_tokens=4000,
                temperature=0.2,
                task_type="reasoning",
            )
        except Exception as e:
            logger.warning("company_profile_synthesis_failed", error=str(e)[:200])
            return SubAgentResult(agent_name=self.name, error=f"LLM synthesis failed: {str(e)[:200]}")

        if on_event:
            await _emit(on_event, "Company profile synthesized.", "completed", "analysis")

        # Score sections for evidence
        evidence_items: list[dict] = []
        for section_key in ["company_overview", "culture_and_values", "tech_and_engineering",
                            "products_and_services", "hiring_intelligence"]:
            section = result.get(section_key, {})
            if isinstance(section, dict) and section:
                conf = section.get("section_confidence", "unknown")
                evidence_items.append({
                    "fact": f"{section_key}: {conf} confidence",
                    "source": f"company_profile:{section_key}",
                    "tier": "DERIVED",
                    "sub_agent": self.name,
                })

        confidence = 0.80  # LLM synthesis has inherent uncertainty
        return SubAgentResult(
            agent_name=self.name,
            data=result,
            evidence_items=evidence_items,
            confidence=confidence,
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
