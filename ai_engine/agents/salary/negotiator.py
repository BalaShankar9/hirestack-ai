"""SalaryNegotiator — produce a defensible counter from offer + market band.

Pure-python, deterministic. The LLM is only used by ScriptWriter.
"""
from __future__ import annotations

from typing import List, Optional

from ai_engine.agents.salary.market_intel import get_market_band
from ai_engine.agents.salary.schemas import MarketBand, NegotiationPlan, OfferDetails


def _clamp_pct(value: float, base: float, low_pct: float, high_pct: float) -> float:
    floor = base * (1 + low_pct)
    ceiling = base * (1 + high_pct)
    return max(floor, min(ceiling, value))


def _round_to_500(value: float) -> float:
    return float(int(round(value / 500.0) * 500))


def _equity_per_year(equity_total: float, vesting_years: int = 4) -> float:
    if equity_total <= 0:
        return 0.0
    return equity_total / max(1, vesting_years)


class SalaryNegotiator:
    def plan(self, offer: OfferDetails, market_band: Optional[MarketBand] = None) -> NegotiationPlan:
        if not offer.role or not offer.role.strip():
            raise ValueError("offer.role is required")
        if offer.base <= 0:
            raise ValueError("offer.base must be positive")

        band = market_band or get_market_band(offer.role, offer.level, offer.location)
        if band is None:
            # Synthesize a conservative band from the offer itself.
            band = MarketBand(
                role=offer.role, level=offer.level, location=offer.location,
                p25=offer.base * 0.95, p50=offer.base, p75=offer.base * 1.10,
                p90=offer.base * 1.20, source="offer_synth",
            )

        rationale: List[str] = []
        red_flags: List[str] = []

        # Anchor: aim for p75 of band, but clamp to [+5%, +20%] of offered base.
        raw_target = max(band.p75, offer.base * 1.10)
        counter_base = _round_to_500(_clamp_pct(raw_target, offer.base, 0.05, 0.20))
        target_low = _round_to_500(_clamp_pct(band.p50, offer.base, 0.03, 0.18))
        target_high = _round_to_500(_clamp_pct(band.p90, offer.base, 0.08, 0.25))

        # Walk-away: floor of p25 or current base, whichever's higher.
        walk_away = _round_to_500(max(band.p25, offer.base * 0.98))

        # Total comp counter — base + bonus + amortized equity + sign-on/4.
        equity_yr = _equity_per_year(offer.equity)
        sign_on_yr = offer.sign_on / 4.0 if offer.sign_on else 0.0
        counter_total_comp = _round_to_500(
            counter_base + offer.bonus + equity_yr + sign_on_yr
        )

        # Build rationale
        rationale.append(
            f"Market p50 = ${int(band.p50):,}, p75 = ${int(band.p75):,} "
            f"({band.source}); your offer base is ${int(offer.base):,}."
        )
        rationale.append(
            f"Counter base of ${int(counter_base):,} anchors near p75 while "
            "staying within a defensible +5%–+20% of the original offer."
        )
        if offer.competing_offers:
            best = max(offer.competing_offers, key=lambda o: o.total_comp or o.base)
            rationale.append(
                f"You have a competing offer from {best.company or 'another company'} "
                f"at total comp ${int(best.total_comp or best.base):,} — anchor on this."
            )
        if offer.your_leverage:
            rationale.append(f"Leverage cited: {offer.your_leverage[:200]}")

        # Red flags
        if offer.base < band.p25:
            red_flags.append(
                f"Offer base ${int(offer.base):,} is below market p25 "
                f"(${int(band.p25):,}) — large gap, expect resistance."
            )
        if offer.equity > 0 and offer.bonus == 0:
            red_flags.append(
                "All upside is in equity — request cash bonus or higher base "
                "if liquidity matters."
            )
        if offer.sign_on > offer.base * 0.25:
            red_flags.append(
                "Sign-on is unusually large vs. base — verify clawback terms."
            )

        return NegotiationPlan(
            counter_base=counter_base,
            counter_total_comp=counter_total_comp,
            target_range_low=target_low,
            target_range_high=target_high,
            walk_away=walk_away,
            rationale=rationale,
            red_flags=red_flags,
            market_band=band,
        )
