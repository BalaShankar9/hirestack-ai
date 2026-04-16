"""
NegotiationFrameworkBuilder — deterministic Phase 1 agent.

Builds a negotiation strategy skeleton: recommended ask, walk-away point,
opening position, approach, and timing.  No LLM call — formula-based.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


class NegotiationFrameworkBuilder(SubAgent):
    """Builds a negotiation framework from market data and offer details."""

    def __init__(self, ai_client=None):
        super().__init__(name="negotiation_framework_builder", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        # Pull in peer data from MarketRangeEstimator if available
        market = context.get("_market_range", {})
        offer_data = context.get("_offer_data", {})

        median = market.get("median", 0)
        high = market.get("high", 0)
        low = market.get("low", 0)
        leverage = context.get("_leverage_score", 50)
        offer_salary = offer_data.get("offer_salary_extracted")
        has_offer = offer_data.get("has_offer", False)

        # If no market data, attempt from context
        if not median:
            median = self._parse_salary(context.get("current_salary", "")) or 100000
            high = int(median * 1.35)
            low = int(median * 0.80)

        # ── Strategy calculations ─────────────────────────────
        # Recommended ask: 85th percentile biased by leverage
        leverage_boost = (leverage - 50) / 100  # -0.5 to +0.5
        recommended_ask = int(median * (1.15 + leverage_boost * 0.15))
        recommended_ask = max(recommended_ask, int(median * 1.05))  # floor at 105% of median

        # Opening: 10-15% above recommended ask
        opening = int(recommended_ask * 1.12)

        # Walk-away: median minus 5%
        walk_away = int(median * 0.95)

        # Approach
        if leverage >= 70:
            approach = "strong"
            approach_desc = "You have strong leverage — lead with confidence, anchor high."
        elif leverage >= 40:
            approach = "balanced"
            approach_desc = "Balanced position — present value clearly, be prepared to justify."
        else:
            approach = "cautious"
            approach_desc = "Limited leverage — focus on total compensation and growth potential."

        # Timing
        if has_offer:
            timing = "You have an offer — respond within 2-3 business days. Don't rush, but don't delay."
        else:
            timing = "Pre-offer — discuss compensation expectations early to avoid wasting time."

        return SubAgentResult(
            agent_name=self.name,
            data={
                "recommended_ask": recommended_ask,
                "opening_position": opening,
                "walk_away_point": walk_away,
                "approach": approach,
                "approach_description": approach_desc,
                "timing": timing,
                "leverage_score": leverage,
                "market_median_used": median,
            },
            confidence=0.75,
        )

    @staticmethod
    def _parse_salary(text: str) -> int | None:
        if not text:
            return None
        cleaned = text.replace(",", "").replace("$", "").replace("£", "").replace("€", "")
        digits = "".join(c for c in cleaned if c.isdigit())
        if digits and len(digits) >= 4:
            return int(digits)
        return None
