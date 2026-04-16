"""
IntelCoordinator — orchestrates the full intel sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel): WebsiteIntel, GitHubIntel, CareersIntel, JDIntel, MarketPosition
    → All run simultaneously for maximum speed
  Phase 2 (sequential): CompanyProfile → ApplicationStrategy
    → Profile runs first, then strategy uses profile output

Returns the final merged intel dict compatible with the existing
CompanyIntelChain interface so streaming, storage, and document
generation all work without changes.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional, Callable, Awaitable

import structlog

from ai_engine.agents.sub_agents.base import SubAgentCoordinator, SubAgentResult
from ai_engine.agents.sub_agents.intel.website_intel import WebsiteIntelAgent
from ai_engine.agents.sub_agents.intel.github_intel import GitHubIntelAgent
from ai_engine.agents.sub_agents.intel.careers_intel import CareersIntelAgent
from ai_engine.agents.sub_agents.intel.jd_intel import JDIntelAgent
from ai_engine.agents.sub_agents.intel.market_position import MarketPositionAgent
from ai_engine.agents.sub_agents.intel.company_profile import CompanyProfileAgent
from ai_engine.agents.sub_agents.intel.application_strategy import ApplicationStrategyAgent
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.coordinator")

IntelEventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class IntelCoordinator:
    """
    Two-phase intel sub-agent coordinator.

    Phase 1 — Parallel data gathering (all at once):
      • WebsiteIntelAgent   — crawls company website pages
      • GitHubIntelAgent    — GitHub org/repo analysis
      • CareersIntelAgent   — careers page + ATS detection
      • JDIntelAgent        — deep JD signal extraction
      • MarketPositionAgent — Glassdoor, LinkedIn, news, competitors, salary

    Phase 2 — LLM synthesis (sequential, after Phase 1 completes):
      • CompanyProfileAgent     — structured company profile
      • ApplicationStrategyAgent — actionable guidance (consumes profile output)

    Returns a merged dict compatible with the legacy CompanyIntelChain output.
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    async def gather_intel(
        self,
        company: str,
        job_title: str,
        jd_text: str,
        company_url: Optional[str] = None,
        on_event: Optional[IntelEventCallback] = None,
    ) -> dict[str, Any]:
        """Full multi-agent intel gathering with two-phase execution."""
        start = time.monotonic()

        if on_event:
            await self._emit(on_event, f"Intel swarm deploying 5 sub-agents for {company}…", "running", "recon")

        # Build shared context for all agents
        base_context: dict[str, Any] = {
            "company": company,
            "company_name": company,
            "company_url": company_url,
            "job_title": job_title,
            "jd_text": jd_text,
            "on_event": on_event,
        }

        # ── PHASE 1: Parallel data gathering ──────────────────────
        phase1_agents = [
            WebsiteIntelAgent(ai_client=self.ai_client),
            GitHubIntelAgent(ai_client=self.ai_client),
            CareersIntelAgent(ai_client=self.ai_client),
            JDIntelAgent(ai_client=self.ai_client),
            MarketPositionAgent(ai_client=self.ai_client),
        ]

        coordinator = SubAgentCoordinator(phase1_agents)
        try:
            phase1_results = await asyncio.wait_for(
                coordinator.gather(base_context),
                timeout=20,
            )
        except asyncio.TimeoutError:
            logger.warning("intel_phase1_timeout", agents=[a.name for a in phase1_agents])
            # Return empty results for timed-out agents
            phase1_results = [
                SubAgentResult(agent_name=a.name, error="Phase 1 timeout (20s)")
                for a in phase1_agents
            ]

        # Collect results by agent name
        raw_intel: dict[str, dict] = {}
        all_evidence: list[dict] = []
        data_sources: list[str] = []
        agent_latencies: dict[str, int] = {}

        for result in phase1_results:
            agent_latencies[result.agent_name] = result.latency_ms
            if result.ok:
                raw_intel[result.agent_name] = result.data
                all_evidence.extend(result.evidence_items)
                # Track which sources actually provided data
                if result.data and result.confidence > 0.2:
                    data_sources.append(result.agent_name)
            else:
                logger.warning("intel_agent_failed", agent=result.agent_name, error=result.error)
                raw_intel[result.agent_name] = {"error": result.error}

        phase1_time = time.monotonic() - start

        if on_event:
            source_count = len(data_sources)
            await self._emit(
                on_event,
                f"Phase 1 complete: {source_count}/5 agents returned data in {phase1_time:.1f}s. Running synthesis…",
                "running", "analysis",
                metadata={
                    "sources": data_sources,
                    "latencies": agent_latencies,
                    "phase1_seconds": round(phase1_time, 1),
                },
            )

        # ── PHASE 2a: Company Profile synthesis ────────────────────
        synthesis_context = {
            **base_context,
            "raw_intel": raw_intel,
        }

        profile_agent = CompanyProfileAgent(ai_client=self.ai_client)
        profile_result = await profile_agent.safe_run(synthesis_context)

        # ── PHASE 2b: Application Strategy (needs profile output) ─────
        # Strategy agent reads the company profile, so it must run AFTER
        # CompanyProfileAgent completes — NOT in parallel.
        if profile_result.ok:
            raw_intel["company_profile"] = profile_result.data
        strategy_context = {
            **base_context,
            "raw_intel": raw_intel,
        }
        strategy_agent = ApplicationStrategyAgent(ai_client=self.ai_client)
        strategy_result = await strategy_agent.safe_run(strategy_context)

        agent_latencies[profile_result.agent_name] = profile_result.latency_ms
        agent_latencies[strategy_result.agent_name] = strategy_result.latency_ms

        if profile_result.ok:
            all_evidence.extend(profile_result.evidence_items)
        if strategy_result.ok:
            all_evidence.extend(strategy_result.evidence_items)

        total_time = time.monotonic() - start

        # ── MERGE into legacy-compatible format ───────────────────
        merged = self._merge_results(
            company=company,
            raw_intel=raw_intel,
            profile=profile_result.data if profile_result.ok else {},
            strategy=strategy_result.data if strategy_result.ok else {},
            data_sources=data_sources,
            all_evidence=all_evidence,
            agent_latencies=agent_latencies,
            total_time_s=total_time,
        )

        if on_event:
            await self._emit(
                on_event,
                f"Intel complete: {len(data_sources)} sources, {len(all_evidence)} evidence items, {merged['confidence']} confidence ({total_time:.1f}s).",
                "completed", "recon",
                metadata={
                    "confidence": merged["confidence"],
                    "data_sources": merged["data_sources"],
                    "evidence_count": len(all_evidence),
                    "total_seconds": round(total_time, 1),
                    "agent_latencies": agent_latencies,
                },
            )

        return merged

    def _merge_results(
        self,
        company: str,
        raw_intel: dict[str, dict],
        profile: dict,
        strategy: dict,
        data_sources: list[str],
        all_evidence: list[dict],
        agent_latencies: dict[str, int],
        total_time_s: float,
    ) -> dict[str, Any]:
        """Merge all sub-agent data into the legacy CompanyIntelChain output format."""

        jd = raw_intel.get("jd_intel", {})
        website = raw_intel.get("website_intel", {})
        github = raw_intel.get("github_intel", {})
        careers = raw_intel.get("careers_intel", {})
        market = raw_intel.get("market_position", {})

        # Use profile (LLM-synthesized) as the base, then enrich with raw data
        result: dict[str, Any] = {}

        # Company overview
        result["company_overview"] = profile.get("company_overview", {})
        if not result["company_overview"]:
            result["company_overview"] = {"name": company}
        result["company_overview"].setdefault("name", company)
        if website.get("base_url"):
            result["company_overview"]["website"] = website["base_url"]

        # Culture and values — merge profile + JD + careers
        result["culture_and_values"] = profile.get("culture_and_values", {})
        result["culture_and_values"].setdefault("core_values", [])
        if jd.get("culture_signals"):
            result["culture_and_values"]["jd_culture_signals"] = jd["culture_signals"]
        if jd.get("red_flags"):
            result["culture_and_values"]["red_flags"] = jd["red_flags"]
        if careers.get("benefits"):
            result["culture_and_values"]["employee_benefits"] = careers["benefits"]
        if careers.get("work_model"):
            result["culture_and_values"]["work_style"] = careers["work_model"]
        if jd.get("work_model") and jd["work_model"] != "unknown":
            result["culture_and_values"]["work_style"] = jd["work_model"]
        if careers.get("interview_hints"):
            result["culture_and_values"]["interview_hints"] = careers["interview_hints"]

        # Tech and engineering — merge profile + JD + GitHub
        result["tech_and_engineering"] = profile.get("tech_and_engineering", {})
        if jd.get("tech_stack"):
            result["tech_and_engineering"]["jd_tech_stack"] = jd["tech_stack"]
        if jd.get("all_technologies"):
            result["tech_and_engineering"]["tech_stack"] = list(set(
                result["tech_and_engineering"].get("tech_stack", []) + jd["all_technologies"]
            ))
        if github.get("org_name"):
            result["tech_and_engineering"]["github_stats"] = {
                "org_name": github.get("org_name", ""),
                "public_repos": github.get("repo_count", 0),
                "top_languages": list(github.get("languages", {}).keys())[:10],
                "notable_repos": [r.get("name", "") for r in github.get("notable_repos", [])[:5]],
                "activity_level": github.get("activity_level", "Unknown"),
                "total_stars": github.get("total_stars", 0),
                "culture_signals": github.get("culture_signals", []),
                "topics": github.get("topics", [])[:15],
            }

        # Products and services
        result["products_and_services"] = profile.get("products_and_services", {})

        # Market position — merge profile + market intel
        result["market_position"] = profile.get("market_position", {})
        if market.get("competitors") and isinstance(market["competitors"], dict):
            result["market_position"]["market_research"] = {
                k: v for k, v in market.items()
                if k not in ("error",) and isinstance(v, dict)
            }

        # Recent developments
        result["recent_developments"] = profile.get("recent_developments", {})
        if market.get("news") and isinstance(market["news"], dict):
            result["recent_developments"]["news_data"] = market["news"]

        # Hiring intelligence — merge profile + JD + careers
        result["hiring_intelligence"] = profile.get("hiring_intelligence", {})
        if jd.get("must_have_skills"):
            result["hiring_intelligence"]["must_have_skills"] = jd["must_have_skills"]
        if jd.get("nice_to_have_skills"):
            result["hiring_intelligence"]["nice_to_have_skills"] = jd["nice_to_have_skills"]
        if jd.get("seniority"):
            result["hiring_intelligence"]["seniority_signals"] = jd["seniority"]
        if jd.get("years_required"):
            result["hiring_intelligence"]["years_required"] = jd["years_required"]
        if jd.get("salary_range"):
            result["hiring_intelligence"]["salary_range"] = jd["salary_range"]
        if careers.get("estimated_open_roles"):
            result["hiring_intelligence"]["estimated_open_roles"] = careers["estimated_open_roles"]
        if careers.get("ats_platform"):
            result["hiring_intelligence"]["ats_platform"] = careers["ats_platform"]
        if careers.get("teams_hiring"):
            result["hiring_intelligence"]["teams_hiring"] = careers["teams_hiring"]
        if market.get("cross_ref") and isinstance(market["cross_ref"], dict):
            if market["cross_ref"].get("hiring_volume"):
                result["hiring_intelligence"]["hiring_volume"] = market["cross_ref"]["hiring_volume"]

        # Application strategy — from the dedicated strategy agent
        result["application_strategy"] = strategy if strategy else {}
        result["application_strategy"].setdefault("keywords_to_use", [])
        result["application_strategy"].setdefault("values_to_emphasize", [])
        result["application_strategy"].setdefault("things_to_mention", [])
        result["application_strategy"].setdefault("things_to_avoid", [])
        result["application_strategy"].setdefault("cover_letter_hooks", [])
        result["application_strategy"].setdefault("interview_prep_topics", [])
        result["application_strategy"].setdefault("questions_to_ask", [])

        # Confidence — based on data completeness
        has_website = "website_intel" in data_sources
        has_github = "github_intel" in data_sources
        has_careers = "careers_intel" in data_sources
        has_jd = "jd_intel" in data_sources
        has_market = "market_position" in data_sources
        source_count = sum([has_website, has_github, has_careers, has_jd, has_market])

        if source_count >= 4:
            confidence = "high"
        elif source_count >= 3:
            confidence = "medium"
        elif source_count >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        result["confidence"] = confidence
        result["data_completeness"] = {
            "website_data": has_website,
            "jd_analysis": has_jd,
            "github_data": has_github,
            "careers_page": has_careers,
            "market_data": has_market,
            "company_profile_synthesized": bool(profile),
            "strategy_generated": bool(strategy),
        }

        # Human-readable source names
        source_names = []
        if has_website:
            source_names.append("Company website")
        if has_github:
            source_names.append("GitHub organization")
        if has_careers:
            source_names.append("Careers page")
        if has_jd:
            source_names.append("Job description analysis")
        if has_market:
            source_names.append("Market intelligence")
        if profile:
            source_names.append("AI company profile synthesis")
        if strategy:
            source_names.append("AI application strategy")
        result["data_sources"] = source_names or ["Job description inference only"]

        # Metadata for debugging
        result["_intel_meta"] = {
            "agent_latencies_ms": agent_latencies,
            "total_time_s": round(total_time_s, 2),
            "evidence_count": len(all_evidence),
            "phase1_agents": ["website_intel", "github_intel", "careers_intel", "jd_intel", "market_position"],
            "phase2_agents": ["company_profile", "application_strategy"],
            "version": "2.0",
        }

        return result

    async def _emit(self, callback, message, status, source, url=None, metadata=None):
        if not callback:
            return
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
