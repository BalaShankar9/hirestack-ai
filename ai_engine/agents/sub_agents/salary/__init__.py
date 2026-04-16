"""
Salary Coach sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel, deterministic — no LLM):
    • MarketRangeEstimator       — heuristic salary range by title/location/level
    • ValueDriverAnalyzer        — identifies candidate value drivers and detractors
    • OfferAnalyzer              — parses offer details, flags red flags
    • NegotiationFrameworkBuilder — strategy skeleton (ask, walk-away, opening)

  Phase 2 (single LLM):
    • SalarySynthesizer          — negotiation scripts, talking points, assessment

Re-exports all agents + coordinator for convenience.
"""
from ai_engine.agents.sub_agents.salary.market_range_estimator import MarketRangeEstimator
from ai_engine.agents.sub_agents.salary.value_driver_analyzer import ValueDriverAnalyzer
from ai_engine.agents.sub_agents.salary.offer_analyzer import OfferAnalyzer
from ai_engine.agents.sub_agents.salary.negotiation_framework_builder import NegotiationFrameworkBuilder
from ai_engine.agents.sub_agents.salary.salary_synthesizer import SalarySynthesizer
from ai_engine.agents.sub_agents.salary.coordinator import SalaryCoordinator

__all__ = [
    "MarketRangeEstimator",
    "ValueDriverAnalyzer",
    "OfferAnalyzer",
    "NegotiationFrameworkBuilder",
    "SalarySynthesizer",
    "SalaryCoordinator",
]
