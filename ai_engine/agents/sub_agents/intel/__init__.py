"""
Intel Sub-Agent Swarm — specialized agents for maximum company intelligence.

Seven parallel sub-agents coordinated under IntelCoordinator:
  1. WebsiteIntelAgent   — Deep website crawl (homepage, about, team, blog)
  2. GitHubIntelAgent    — GitHub org/repos/tech stack analysis
  3. CareersIntelAgent   — Careers page + open-role cross-reference
  4. JDIntelAgent        — Deep JD analysis (hidden reqs, culture, red flags)
  5. CompanyProfileAgent — LLM synthesis of company identity
  6. MarketPositionAgent — Competitor, market, salary intel
  7. ApplicationStrategyAgent — Strategic application guidance from all data
"""
from ai_engine.agents.sub_agents.intel.website_intel import WebsiteIntelAgent
from ai_engine.agents.sub_agents.intel.github_intel import GitHubIntelAgent
from ai_engine.agents.sub_agents.intel.careers_intel import CareersIntelAgent
from ai_engine.agents.sub_agents.intel.jd_intel import JDIntelAgent
from ai_engine.agents.sub_agents.intel.company_profile import CompanyProfileAgent
from ai_engine.agents.sub_agents.intel.market_position import MarketPositionAgent
from ai_engine.agents.sub_agents.intel.application_strategy import ApplicationStrategyAgent
from ai_engine.agents.sub_agents.intel.coordinator import IntelCoordinator

__all__ = [
    "WebsiteIntelAgent",
    "GitHubIntelAgent",
    "CareersIntelAgent",
    "JDIntelAgent",
    "CompanyProfileAgent",
    "MarketPositionAgent",
    "ApplicationStrategyAgent",
    "IntelCoordinator",
]
