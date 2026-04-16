"""
Company Intelligence Chain — Multi-Agent Intel Gathering (v2)

Delegates to IntelCoordinator which runs 7 specialised sub-agents:
  Phase 1 (parallel):
    1. WebsiteIntelAgent   — deep website crawl
    2. GitHubIntelAgent    — GitHub org analysis
    3. CareersIntelAgent   — careers page + ATS detection
    4. JDIntelAgent        — deep JD signal extraction
    5. MarketPositionAgent — competitor/salary/news intel
  Phase 2 (LLM synthesis, after Phase 1):
    6. CompanyProfileAgent     — structured company profile
    7. ApplicationStrategyAgent — actionable application guidance

Returns a structured intel report used by document generation agents.
Backward-compatible: same gather_intel() signature, same return shape.
"""
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
import structlog

# New intel sub-agents
from ai_engine.agents.sub_agents.role_intel_agent import RoleIntelSubAgent
from ai_engine.agents.sub_agents.founder_intel_agent import FounderIntelSubAgent
from ai_engine.agents.sub_agents.press_intel_agent import PressIntelSubAgent
from ai_engine.agents.sub_agents.review_intel_agent import ReviewIntelSubAgent

logger = structlog.get_logger()

IntelEventCallback = Callable[[Dict[str, Any]], Awaitable[None] | None]

# Retained for JD-only fallback when coordinator completely fails
INTEL_SYSTEM = """You are an elite corporate intelligence analyst. Given raw data from multiple sources
about a company, you extract and synthesize actionable intelligence for job applicants.

Your analysis must be:
- FACTUAL: Only state what the data supports. Never fabricate company details.
- SPECIFIC: Cite real products, real values, real tech. Generic advice is useless.
- ACTIONABLE: Every insight should help the candidate write a better application or prepare for an interview.
- HONEST: If data is limited, say so. Mark confidence levels accurately.

Return ONLY valid JSON."""

INTEL_FROM_JD_PROMPT = """The company website was not accessible. Analyze the job description thoroughly
to extract ALL possible company intelligence.

COMPANY NAME: {company}
JOB TITLE: {job_title}

FULL JOB DESCRIPTION:
{jd_text}

Extract every clue: culture signals, tech stack, team size, growth stage, values, work style,
interview hints, salary signals, hidden requirements, red flags.

Return the same comprehensive JSON format, but mark confidence appropriately.
Fields you cannot determine should be "Unknown" or empty arrays."""


# ── Application Strategy Digest prompt ──────────────────────────────

DIGEST_SYSTEM = """You are a senior recruiter who distils complex company intelligence into a crisp,
actionable brief for a job applicant. Be direct, concrete, and specific."""

DIGEST_PROMPT = """Given this company intelligence report, produce a 150-word Application Strategy Digest.

INTEL REPORT (summary):
Company: {company}
Role: {job_title}
Industry: {industry}
Stage: {stage}
Keywords to use: {keywords}
Cover letter hooks: {hooks}
Things to avoid: {avoid}
Must-have skills: {must_have}
Recent news: {news}
Founder/Leadership insight: {founder_insight}
Review insight: {review_insight}

Write exactly this structure (no headers, pure prose):
"[COMPANY SIGNAL 1] [COMPANY SIGNAL 2] [COMPANY SIGNAL 3] Keywords to use: [KEYWORD1, KEYWORD2, KEYWORD3, KEYWORD4, KEYWORD5]. Avoid: [THING1, THING2]. Hook: [ONE COMPELLING COVER LETTER OPENING SENTENCE USING FOUNDER OR PRESS INTEL]."

Keep it under 160 words. Be specific, not generic."""


class CompanyIntelChain:
    """
    Multi-agent intelligence gathering for target companies.

    v2: Delegates all work to IntelCoordinator (7 sub-agents).
    Falls back to a single LLM call on JD text if the coordinator fails entirely.
    """

    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def gather_intel(
        self,
        company: str,
        job_title: str,
        jd_text: str,
        company_url: Optional[str] = None,
        on_event: Optional[IntelEventCallback] = None,
    ) -> Dict[str, Any]:
        """Gather comprehensive multi-source company intelligence via sub-agent swarm."""
        try:
            from ai_engine.agents.sub_agents.intel.coordinator import IntelCoordinator

            coordinator = IntelCoordinator(ai_client=self.ai_client)
            result = await coordinator.gather_intel(
                company=company,
                job_title=job_title,
                jd_text=jd_text,
                company_url=company_url,
                on_event=on_event,
            )
            return result

        except Exception as e:
            logger.error("company_intel_coordinator_failed", error=str(e)[:300])

            # Emit failure event
            if on_event:
                try:
                    payload = {
                        "stage": "recon",
                        "status": "warning",
                        "message": f"Intel sub-agent swarm failed; falling back to JD inference. ({str(e)[:120]})",
                        "source": "recon",
                    }
                    maybe = on_event(payload)
                    if asyncio.iscoroutine(maybe):
                        await maybe
                except Exception:
                    pass

            return await self._fallback_jd_only(company, job_title, jd_text, on_event)

    async def _fallback_jd_only(
        self,
        company: str,
        job_title: str,
        jd_text: str,
        on_event: Optional[IntelEventCallback] = None,
    ) -> Dict[str, Any]:
        """Single LLM call fallback: extract intel from JD text alone."""
        try:
            prompt = INTEL_FROM_JD_PROMPT.format(
                company=company,
                job_title=job_title,
                jd_text=jd_text[:5000],
            )
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=INTEL_SYSTEM,
                max_tokens=4000,
                temperature=0.2,
                task_type="reasoning",
            )
        except Exception as e:
            logger.warning("company_intel_fallback_failed", error=str(e)[:200])
            result = self._minimal_fallback(company, jd_text)

        # Ensure all expected keys exist
        result.setdefault("company_overview", {"name": company})
        result.setdefault("culture_and_values", {})
        result.setdefault("tech_and_engineering", {})
        result.setdefault("products_and_services", {})
        result.setdefault("market_position", {})
        result.setdefault("recent_developments", {})
        result.setdefault("hiring_intelligence", {})
        result.setdefault("application_strategy", {})
        result["confidence"] = result.get("confidence", "low")
        result["data_sources"] = result.get("data_sources", ["Job description inference only"])
        result["data_completeness"] = {
            "website_data": False,
            "jd_analysis": True,
            "github_data": False,
            "careers_page": False,
            "market_data": False,
            "company_profile_synthesized": False,
            "strategy_generated": False,
        }

        if on_event:
            try:
                payload = {
                    "stage": "recon",
                    "status": "completed",
                    "message": f"Recon complete (JD-only fallback, {result['confidence']} confidence).",
                    "source": "recon",
                    "metadata": {"confidence": result["confidence"], "fallback": True},
                }
                maybe = on_event(payload)
                if asyncio.iscoroutine(maybe):
                    await maybe
            except Exception:
                pass

        return result

    @staticmethod
    def _minimal_fallback(company: str, jd_text: str) -> Dict[str, Any]:
        """Absolute last-resort: regex-only intel from JD."""
        lower = jd_text.lower()
        tech_keywords = [
            "react", "angular", "vue", "next.js", "python", "javascript",
            "typescript", "java", "go", "rust", "c#", "ruby", "aws", "gcp",
            "azure", "docker", "kubernetes", "terraform", "postgresql",
            "mongodb", "redis", "kafka", "graphql", "microservices",
            "machine learning", "ai", "deep learning",
        ]
        found_tech = [t for t in tech_keywords if t in lower]

        return {
            "company_overview": {"name": company},
            "culture_and_values": {"core_values": [], "work_style": "Unknown"},
            "tech_and_engineering": {
                "tech_stack": found_tech,
                "github_stats": {"activity_level": "Unknown"},
            },
            "products_and_services": {"main_products": []},
            "hiring_intelligence": {"must_have_skills": [], "nice_to_have_skills": []},
            "application_strategy": {
                "keywords_to_use": found_tech[:10],
                "values_to_emphasize": ["adaptability", "initiative"],
                "things_to_mention": [f"Your genuine interest in {company}"],
                "cover_letter_hooks": [],
                "questions_to_ask": [],
            },
            "confidence": "low",
            "application_strategy_digest": f"Limited intel for {company}. Focus on JD keywords and your direct experience.",
        }
