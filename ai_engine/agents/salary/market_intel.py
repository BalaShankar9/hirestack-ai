"""Market-intel provider for salary bands (S16-P3).

S16 ships with a small seeded JSON for the most-negotiated SWE/PM/DS/
DESIGN role-levels in three meta-locations (us-bay, us-remote, eu).
The interface is pluggable so we can swap in Levels.fyi / Lightcast /
Payscale providers later without breaking SalaryNegotiator.
"""
from __future__ import annotations

from typing import Optional, Protocol

from ai_engine.agents.salary.schemas import MarketBand


class MarketIntelProvider(Protocol):
    def lookup(self, role: str, level: str, location: str) -> Optional[MarketBand]:
        ...


# (role_key, level_key, location_key) → (p25, p50, p75, p90) base salary USD.
# Numbers are 2025 calibrated rough public ranges; replaceable.
_SEED: dict[tuple[str, str, str], tuple[float, float, float, float]] = {
    # Software engineer
    ("software_engineer", "junior", "us-bay"): (110_000, 135_000, 160_000, 185_000),
    ("software_engineer", "mid",    "us-bay"): (160_000, 195_000, 230_000, 270_000),
    ("software_engineer", "senior", "us-bay"): (210_000, 250_000, 300_000, 360_000),
    ("software_engineer", "staff",  "us-bay"): (270_000, 325_000, 390_000, 470_000),
    ("software_engineer", "junior", "us-remote"): (95_000, 115_000, 135_000, 155_000),
    ("software_engineer", "mid",    "us-remote"): (135_000, 160_000, 190_000, 225_000),
    ("software_engineer", "senior", "us-remote"): (175_000, 210_000, 250_000, 295_000),
    ("software_engineer", "staff",  "us-remote"): (220_000, 265_000, 320_000, 390_000),
    ("software_engineer", "mid",    "eu"):        (75_000, 95_000, 115_000, 140_000),
    ("software_engineer", "senior", "eu"):        (95_000, 120_000, 145_000, 175_000),
    # Product manager
    ("product_manager", "mid",    "us-bay"): (160_000, 200_000, 235_000, 280_000),
    ("product_manager", "senior", "us-bay"): (210_000, 255_000, 305_000, 365_000),
    ("product_manager", "mid",    "us-remote"): (135_000, 165_000, 195_000, 230_000),
    ("product_manager", "senior", "us-remote"): (180_000, 215_000, 255_000, 305_000),
    # Data scientist
    ("data_scientist", "mid",    "us-bay"): (155_000, 190_000, 225_000, 265_000),
    ("data_scientist", "senior", "us-bay"): (200_000, 240_000, 290_000, 345_000),
    ("data_scientist", "mid",    "us-remote"): (130_000, 160_000, 190_000, 225_000),
    # Designer
    ("designer", "mid",    "us-remote"): (110_000, 135_000, 160_000, 190_000),
    ("designer", "senior", "us-remote"): (145_000, 175_000, 210_000, 250_000),
}

_ROLE_ALIASES = {
    "swe": "software_engineer", "engineer": "software_engineer",
    "developer": "software_engineer", "software": "software_engineer",
    "pm": "product_manager", "product": "product_manager",
    "ds": "data_scientist", "data": "data_scientist",
    "designer": "designer", "design": "designer", "ux": "designer",
}

_LOCATION_ALIASES = {
    "san francisco": "us-bay", "sf": "us-bay", "bay area": "us-bay",
    "new york": "us-remote", "nyc": "us-remote", "seattle": "us-remote",
    "remote": "us-remote", "us": "us-remote", "usa": "us-remote",
    "london": "eu", "berlin": "eu", "amsterdam": "eu", "europe": "eu",
}

_LEVEL_ALIASES = {
    "intern": "junior", "entry": "junior", "jr": "junior",
    "ic2": "mid", "ic3": "mid",
    "sr": "senior", "lead": "senior",
    "principal": "staff", "staff+": "staff",
}


def _normalize_role(role: str) -> str:
    text = (role or "").lower().strip()
    for trigger, canonical in _ROLE_ALIASES.items():
        if trigger in text:
            return canonical
    # Fall through: assume canonical itself, sanitized.
    return text.replace(" ", "_")


def _normalize_level(level: str) -> str:
    text = (level or "mid").lower().strip()
    return _LEVEL_ALIASES.get(text, text if text in {"junior", "mid", "senior", "staff"} else "mid")


def _normalize_location(location: str) -> str:
    text = (location or "us-remote").lower().strip()
    if text in {"us-bay", "us-remote", "eu"}:
        return text
    for trigger, canonical in _LOCATION_ALIASES.items():
        if trigger in text:
            return canonical
    return "us-remote"


def get_market_band(role: str, level: str, location: str) -> Optional[MarketBand]:
    """Return seeded market band, or None if not in the seed."""
    role_n = _normalize_role(role)
    level_n = _normalize_level(level)
    loc_n = _normalize_location(location)
    band = _SEED.get((role_n, level_n, loc_n))
    if band is None:
        # Try a relaxed location fallback.
        band = _SEED.get((role_n, level_n, "us-remote"))
        if band is None:
            return None
        loc_n = "us-remote"
    p25, p50, p75, p90 = band
    return MarketBand(
        role=role_n, level=level_n, location=loc_n,
        p25=p25, p50=p50, p75=p75, p90=p90,
        source="seed_v1",
    )


class SeedMarketIntelProvider:
    """Default provider — returns from the in-process seed table."""

    def lookup(self, role: str, level: str, location: str) -> Optional[MarketBand]:
        return get_market_band(role, level, location)
