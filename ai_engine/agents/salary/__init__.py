"""Salary Negotiation Script Generator (S16-P3)."""
from ai_engine.agents.salary.schemas import (
    MarketBand,
    NegotiationPlan,
    NegotiationScript,
    OfferDetails,
)
from ai_engine.agents.salary.market_intel import MarketIntelProvider, get_market_band
from ai_engine.agents.salary.negotiator import SalaryNegotiator
from ai_engine.agents.salary.script_writer import ScriptWriter
from ai_engine.agents.salary.integration import (
    build_salary_tools,
    detect_salary_intent,
)

__all__ = [
    "MarketBand",
    "NegotiationPlan",
    "NegotiationScript",
    "OfferDetails",
    "MarketIntelProvider",
    "get_market_band",
    "SalaryNegotiator",
    "ScriptWriter",
    "build_salary_tools",
    "detect_salary_intent",
]
