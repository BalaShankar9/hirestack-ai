"""S18 — Free Mode Coordinator for Recon Swarm.

Enables recon using only free data sources (no API keys required).
This mode uses: GitHub, Wikipedia, SEC, HN, Reddit, arXiv, StackOverflow.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .free_providers import FREE_PROVIDERS, FreeProvider, FreeResult
from .intel_fusion import IntelFusion
from .schemas import CompanyIntelV2, IntelField, ProviderResult, ReconSwarmReport

logger = logging.getLogger(__name__)


class FreeModeRecon:
    """Recon using only free data sources.
    
    Usage:
        recon = FreeModeRecon()
        report = await recon.run("Stripe")
        print(report.intel.description.value)
    """
    
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.fusion = IntelFusion()
    
    async def run(self, company: str, **ctx) -> ReconSwarmReport:
        """Run free recon on a company.
        
        Args:
            company: Company name to research
            **ctx: Additional context (role, skills, etc.)
        
        Returns:
            ReconSwarmReport with fused intel
        """
        logger.info(f"free_recon_start: company={company}")
        
        # Fetch from all free providers concurrently with semaphore
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def fetch_with_limit(cls: type[FreeProvider]) -> FreeResult:
            async with semaphore:
                provider = cls()
                return await provider.fetch(company, **ctx)
        
        # Run all providers
        results = await asyncio.gather(
            *[fetch_with_limit(cls) for cls in FREE_PROVIDERS],
            return_exceptions=True
        )
        
        # Process results
        free_results: Dict[str, FreeResult] = {}
        provider_results: List[ProviderResult] = []
        
        for cls, result in zip(FREE_PROVIDERS, results):
            name = cls.name
            if isinstance(result, Exception):
                logger.warning(f"free_provider_failed: {name} error={result}")
                free_results[name] = FreeResult(
                    provider=name,
                    success=False,
                    data={},
                    error=str(result)[:200],
                )
                provider_results.append(ProviderResult(
                    layer=1,
                    provider=name,
                    success=False,
                    data={},
                    error=str(result)[:200],
                ))
            else:
                free_results[name] = result
                provider_results.append(ProviderResult(
                    layer=1,
                    provider=name,
                    success=result.success,
                    data=result.data,
                    error=result.error,
                ))
        
        # Convert free results to intel fusion format
        raw_payloads = [r.data for r in free_results.values() if r.success]
        
        # Fuse into structured intel
        intel = self._fuse_to_intel(raw_payloads, company)
        
        # Build report
        report = ReconSwarmReport(
            company=company,
            intel=intel,
            application_kit=None,  # Would need role/skills
            provider_results=provider_results,
            metadata={
                "mode": "free",
                "sources_used": len([r for r in free_results.values() if r.success]),
                "sources_total": len(FREE_PROVIDERS),
            },
        )
        
        logger.info(f"free_recon_complete: company={company} sources={report.metadata['sources_used']}/{report.metadata['sources_total']}")
        return report
    
    def _fuse_to_intel(self, payloads: List[Dict[str, Any]], company: str) -> CompanyIntelV2:
        """Convert free provider payloads to CompanyIntelV2.
        
        This is a simplified fusion that prioritizes free data sources.
        """
        intel = CompanyIntelV2()
        
        # Index by provider type
        by_provider: Dict[str, Dict[str, Any]] = {}
        for p in payloads:
            name = p.get("_provider", "unknown")
            by_provider[name] = p
        
        # GitHub data
        if "github_free" in by_provider:
            gh = by_provider["github_free"]
            intel.github_orgs = IntelField(value=[gh.get("github_org")], confidence="high", sources=["github_free"])
            intel.repo_count = IntelField(value=gh.get("repo_count"), confidence="high", sources=["github_free"])
            intel.languages = IntelField(value=gh.get("tech_stack", []), confidence="medium", sources=["github_free"])
        
        # Wikipedia data
        if "wikipedia_free" in by_provider:
            wiki = by_provider["wikipedia_free"]
            intel.description = IntelField(value=wiki.get("description"), confidence="high", sources=["wikipedia_free"])
            intel.industry = IntelField(value=wiki.get("industry"), confidence="medium", sources=["wikipedia_free"])
            intel.headquarters = IntelField(value=wiki.get("hq"), confidence="medium", sources=["wikipedia_free"])
            intel.founded_year = IntelField(value=wiki.get("founded"), confidence="high", sources=["wikipedia_free"])
            intel.website = IntelField(value=wiki.get("website"), confidence="high", sources=["wikipedia_free"])
        
        # SEC data
        if "sec_free" in by_provider:
            sec = by_provider["sec_free"]
            intel.ticker = IntelField(value=sec.get("ticker"), confidence="high", sources=["sec_free"])
            intel.is_public = IntelField(value=sec.get("is_public"), confidence="high", sources=["sec_free"])
        
        # HackerNews data
        if "hackernews_free" in by_provider:
            hn = by_provider["hackernews_free"]
            news_items = hn.get("news", [])
            intel.recent_news = IntelField(
                value=[n.get("title") for n in news_items[:5]],
                confidence="medium",
                sources=["hackernews_free"],
            )
        
        # arXiv data
        if "arxiv_free" in by_provider:
            arx = by_provider["arxiv_free"]
            intel.research_papers = IntelField(
                value=[p.get("title") for p in arx.get("papers", [])[:5]],
                confidence="medium",
                sources=["arxiv_free"],
            )
            intel.patents_count = IntelField(value=arx.get("paper_count"), confidence="low", sources=["arxiv_free"])
        
        # Reddit data
        if "reddit_free" in by_provider:
            rd = by_provider["reddit_free"]
            subs = rd.get("subreddits", [])
            intel.reputation_signals = IntelField(
                value={"reddit_communities": subs[:5]},
                confidence="low",
                sources=["reddit_free"],
            )
        
        # StackOverflow data
        if "stackoverflow_free" in by_provider:
            so = by_provider["stackoverflow_free"]
            tags = so.get("tech_tags", [])
            if tags and not intel.languages.value:
                intel.languages = IntelField(value=tags[:10], confidence="medium", sources=["stackoverflow_free"])
        
        # Set legal name
        intel.legal_name = IntelField(value=company, confidence="high", sources=["user_input"])
        
        return intel


# Convenience function
async def run_free_recon(company: str, **ctx) -> ReconSwarmReport:
    """Run free recon on a company.
    
    Args:
        company: Company name to research
        **ctx: Additional context
    
    Returns:
        ReconSwarmReport
    """
    recon = FreeModeRecon()
    return await recon.run(company, **ctx)
