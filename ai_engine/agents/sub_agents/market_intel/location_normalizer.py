"""
LocationNormalizer — deterministic Phase 1 agent.

Normalizes location strings, determines country code, currency,
and cost-of-living tier.  No LLM — keyword/lookup based.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


_LOCATION_MAP: dict[str, dict[str, str]] = {
    # US cities
    "san francisco": {"country": "US", "currency": "USD", "col_tier": "very_high", "region": "West Coast"},
    "new york": {"country": "US", "currency": "USD", "col_tier": "very_high", "region": "East Coast"},
    "seattle": {"country": "US", "currency": "USD", "col_tier": "high", "region": "West Coast"},
    "austin": {"country": "US", "currency": "USD", "col_tier": "medium", "region": "South"},
    "chicago": {"country": "US", "currency": "USD", "col_tier": "high", "region": "Midwest"},
    "boston": {"country": "US", "currency": "USD", "col_tier": "high", "region": "East Coast"},
    "los angeles": {"country": "US", "currency": "USD", "col_tier": "very_high", "region": "West Coast"},
    "denver": {"country": "US", "currency": "USD", "col_tier": "medium", "region": "Mountain"},
    # UK
    "london": {"country": "GB", "currency": "GBP", "col_tier": "very_high", "region": "UK - South East"},
    "manchester": {"country": "GB", "currency": "GBP", "col_tier": "medium", "region": "UK - North West"},
    "birmingham": {"country": "GB", "currency": "GBP", "col_tier": "medium", "region": "UK - Midlands"},
    "edinburgh": {"country": "GB", "currency": "GBP", "col_tier": "medium", "region": "UK - Scotland"},
    # India
    "bangalore": {"country": "IN", "currency": "INR", "col_tier": "low", "region": "India - South"},
    "bengaluru": {"country": "IN", "currency": "INR", "col_tier": "low", "region": "India - South"},
    "hyderabad": {"country": "IN", "currency": "INR", "col_tier": "low", "region": "India - South"},
    "mumbai": {"country": "IN", "currency": "INR", "col_tier": "medium", "region": "India - West"},
    "delhi": {"country": "IN", "currency": "INR", "col_tier": "low", "region": "India - North"},
    "pune": {"country": "IN", "currency": "INR", "col_tier": "low", "region": "India - West"},
    # Europe
    "berlin": {"country": "DE", "currency": "EUR", "col_tier": "medium", "region": "Germany"},
    "amsterdam": {"country": "NL", "currency": "EUR", "col_tier": "high", "region": "Netherlands"},
    "paris": {"country": "FR", "currency": "EUR", "col_tier": "high", "region": "France"},
    "dublin": {"country": "IE", "currency": "EUR", "col_tier": "high", "region": "Ireland"},
    "zurich": {"country": "CH", "currency": "CHF", "col_tier": "very_high", "region": "Switzerland"},
    # Canada
    "toronto": {"country": "CA", "currency": "CAD", "col_tier": "high", "region": "Canada - Ontario"},
    "vancouver": {"country": "CA", "currency": "CAD", "col_tier": "high", "region": "Canada - BC"},
    # Australia
    "sydney": {"country": "AU", "currency": "AUD", "col_tier": "high", "region": "Australia"},
    "melbourne": {"country": "AU", "currency": "AUD", "col_tier": "high", "region": "Australia"},
    # Singapore
    "singapore": {"country": "SG", "currency": "SGD", "col_tier": "very_high", "region": "Southeast Asia"},
}

_COUNTRY_KEYWORD_MAP: dict[str, dict[str, str]] = {
    "united states": {"country": "US", "currency": "USD", "col_tier": "high", "region": "US"},
    "usa": {"country": "US", "currency": "USD", "col_tier": "high", "region": "US"},
    "united kingdom": {"country": "GB", "currency": "GBP", "col_tier": "medium", "region": "UK"},
    "uk": {"country": "GB", "currency": "GBP", "col_tier": "medium", "region": "UK"},
    "india": {"country": "IN", "currency": "INR", "col_tier": "low", "region": "India"},
    "germany": {"country": "DE", "currency": "EUR", "col_tier": "medium", "region": "Germany"},
    "canada": {"country": "CA", "currency": "CAD", "col_tier": "high", "region": "Canada"},
    "australia": {"country": "AU", "currency": "AUD", "col_tier": "high", "region": "Australia"},
    "remote": {"country": "US", "currency": "USD", "col_tier": "medium", "region": "Remote"},
}


class LocationNormalizer(SubAgent):
    """Normalizes a location string to country, currency, COL tier."""

    def __init__(self, ai_client=None):
        super().__init__(name="location_normalizer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        location: str = (context.get("location") or "").strip()
        loc_lower = location.lower()

        # Try city match first
        info = None
        for city, data in _LOCATION_MAP.items():
            if city in loc_lower:
                info = dict(data)
                info["normalized_location"] = city.title()
                break

        # Fallback to country match
        if info is None:
            for keyword, data in _COUNTRY_KEYWORD_MAP.items():
                if keyword in loc_lower:
                    info = dict(data)
                    info["normalized_location"] = keyword.title()
                    break

        # Default
        if info is None:
            info = {
                "country": "US",
                "currency": "USD",
                "col_tier": "medium",
                "region": "Unknown",
                "normalized_location": location or "Not specified",
            }

        return SubAgentResult(
            agent_name=self.name,
            data=info,
            confidence=0.90 if info.get("country") != "US" or "us" in loc_lower else 0.60,
        )
