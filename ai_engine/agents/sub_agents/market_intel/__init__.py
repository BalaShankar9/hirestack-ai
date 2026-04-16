"""
Market Intelligence sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel, deterministic — no LLM):
    • LocationNormalizer        — normalizes location, determines currency/COL tier
    • SkillDemandMapper         — maps skills to demand levels and trends
    • ExperienceLevelClassifier — maps title + years to standard level + salary band
    • TrendMapper               — maps skill categories to emerging trends

  Phase 2 (single LLM):
    • MarketSynthesizer         — full market intelligence report

Re-exports all agents + coordinator for convenience.
"""
from ai_engine.agents.sub_agents.market_intel.location_normalizer import LocationNormalizer
from ai_engine.agents.sub_agents.market_intel.skill_demand_mapper import SkillDemandMapper
from ai_engine.agents.sub_agents.market_intel.experience_level_classifier import ExperienceLevelClassifier
from ai_engine.agents.sub_agents.market_intel.trend_mapper import TrendMapper
from ai_engine.agents.sub_agents.market_intel.market_synthesizer import MarketSynthesizer
from ai_engine.agents.sub_agents.market_intel.coordinator import MarketIntelCoordinator

__all__ = [
    "LocationNormalizer",
    "SkillDemandMapper",
    "ExperienceLevelClassifier",
    "TrendMapper",
    "MarketSynthesizer",
    "MarketIntelCoordinator",
]
