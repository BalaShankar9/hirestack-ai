"""
MarketRangeEstimator — deterministic Phase 1 agent.

Estimates salary ranges based on title, years of experience, location,
and industry using heuristic tables.  No LLM call.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


# Base medians (USD) by generic role family
_ROLE_BASELINES: dict[str, int] = {
    "engineer": 120000,
    "developer": 110000,
    "designer": 95000,
    "manager": 130000,
    "analyst": 90000,
    "scientist": 135000,
    "architect": 160000,
    "director": 180000,
    "vp": 220000,
    "default": 100000,
}

# Multiplier by seniority
_SENIORITY_MULT: dict[str, float] = {
    "intern": 0.40, "junior": 0.65, "mid": 1.0,
    "senior": 1.30, "staff": 1.55, "principal": 1.80,
    "director": 1.90, "vp": 2.40,
}

# COL adjustment
_COL_MULT: dict[str, float] = {
    "very_high": 1.30, "high": 1.10, "medium": 1.0, "low": 0.55,
}

# Currency conversion from USD (approximate)
_CURRENCY_CONVERSION: dict[str, float] = {
    "USD": 1.0, "GBP": 0.80, "EUR": 0.92, "INR": 83.0,
    "CAD": 1.36, "AUD": 1.54, "CHF": 0.88, "SGD": 1.34,
}

_SENIORITY_KEYWORDS: dict[str, str] = {
    "intern": "intern", "junior": "junior", "entry": "junior",
    "mid": "mid", "senior": "senior", "sr.": "senior", "lead": "senior",
    "staff": "staff", "principal": "principal", "architect": "staff",
    "director": "director", "vp": "vp", "chief": "vp",
}


class MarketRangeEstimator(SubAgent):
    """Estimates salary ranges using heuristic tables."""

    def __init__(self, ai_client=None):
        super().__init__(name="market_range_estimator", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        title: str = (context.get("job_title") or "developer").lower()
        years: int = context.get("years_experience", 0)
        location: str = (context.get("location") or "").lower()
        currency: str = context.get("_currency", "USD")
        col_tier: str = context.get("_col_tier", "medium")

        # Detect role family
        baseline = _ROLE_BASELINES["default"]
        for role, base in _ROLE_BASELINES.items():
            if role in title:
                baseline = base
                break

        # Detect seniority from title
        seniority = "mid"
        for kw, level in _SENIORITY_KEYWORDS.items():
            if kw in title:
                seniority = level
                break
        # Override with years if no title signal
        if seniority == "mid":
            if years <= 2:
                seniority = "junior"
            elif years >= 8:
                seniority = "senior" if years < 12 else "staff"

        sen_mult = _SENIORITY_MULT.get(seniority, 1.0)
        col_mult = _COL_MULT.get(col_tier, 1.0)
        fx = _CURRENCY_CONVERSION.get(currency, 1.0)

        median_usd = int(baseline * sen_mult * col_mult)
        median_local = int(median_usd * fx)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "currency": currency,
                "low": int(median_local * 0.80),
                "median": median_local,
                "high": int(median_local * 1.35),
                "seniority": seniority,
                "col_tier": col_tier,
                "baseline_usd": baseline,
                "percentile_estimate": f"Based on {seniority}-level {title.split()[0] if title else 'developer'} in {col_tier} COL market",
            },
            confidence=0.70,
        )
