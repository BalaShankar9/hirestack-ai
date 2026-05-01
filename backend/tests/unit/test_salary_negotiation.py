"""S16-P3 — Salary Negotiation Generator tests."""
from __future__ import annotations

import pytest

from ai_engine.agents.salary import (
    OfferDetails,
    SalaryNegotiator,
    ScriptWriter,
    build_salary_tools,
    detect_salary_intent,
    get_market_band,
)
from ai_engine.agents.salary.integration import generate_negotiation


# ─── stub LLM ───────────────────────────────────────────────────────

class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, **kwargs):
        return self._payload


class _RaisingClient:
    async def complete_json(self, **kwargs):
        raise RuntimeError("no llm")


def _offer(**overrides) -> OfferDetails:
    base = dict(
        role="Software Engineer", level="senior", location="us-bay",
        base=200_000, bonus=20_000, equity=400_000, sign_on=30_000,
        company="Acme",
    )
    base.update(overrides)
    return OfferDetails(**base)


# ─── intent ─────────────────────────────────────────────────────────

def test_intent_positive():
    assert detect_salary_intent("Help me negotiate my salary") is not None
    assert detect_salary_intent("How do I counter this offer?") is not None


def test_intent_negative():
    assert detect_salary_intent("I want to learn Python") is None
    assert detect_salary_intent("") is None


# ─── market intel ──────────────────────────────────────────────────

def test_market_band_lookup_hit():
    band = get_market_band("Software Engineer", "senior", "us-bay")
    assert band is not None
    assert band.role == "software_engineer"
    assert band.level == "senior"
    assert band.location == "us-bay"
    assert band.p25 < band.p50 < band.p75 < band.p90


def test_market_band_aliasing():
    band = get_market_band("SWE", "sr", "San Francisco")
    assert band is not None
    assert band.role == "software_engineer"
    assert band.level == "senior"
    assert band.location == "us-bay"


def test_market_band_relaxes_to_remote_when_unknown_location():
    band = get_market_band("Software Engineer", "senior", "Mars Colony")
    assert band is not None
    assert band.location == "us-remote"


def test_market_band_miss_returns_none():
    assert get_market_band("Astrophysicist", "principal", "us-bay") is None


# ─── negotiator ─────────────────────────────────────────────────────

def test_negotiator_clamps_counter_within_5_to_20_pct():
    offer = _offer(base=200_000)
    plan = SalaryNegotiator().plan(offer)
    assert offer.base * 1.05 <= plan.counter_base <= offer.base * 1.20
    assert plan.target_range_low <= plan.counter_base <= plan.target_range_high


def test_negotiator_synthesizes_band_when_none_known():
    offer = _offer(role="Astrophysicist", level="principal", location="us-bay", base=300_000)
    plan = SalaryNegotiator().plan(offer)
    assert plan.market_band.source == "offer_synth"
    assert plan.counter_base > offer.base


def test_negotiator_flags_below_p25_offer():
    # us-bay senior SWE p25 = 210k; offer below it.
    offer = _offer(base=180_000)
    plan = SalaryNegotiator().plan(offer)
    assert any("below market p25" in flag for flag in plan.red_flags)


def test_negotiator_rejects_zero_base():
    with pytest.raises(ValueError):
        SalaryNegotiator().plan(_offer(base=0))


def test_negotiator_includes_competing_offer_rationale():
    offer = _offer(competing_offers=[{"company": "Beta", "base": 240_000, "total_comp": 320_000}])
    plan = SalaryNegotiator().plan(offer)
    assert any("Beta" in r for r in plan.rationale)


# ─── script writer ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_script_writer_uses_llm_payload():
    payload = {
        "opening": "LLM-OPEN",
        "anchor": "LLM-ANCHOR",
        "silence_cue": "LLM-SILENCE",
        "counter": "LLM-COUNTER",
        "close": "LLM-CLOSE",
        "talking_points": ["one", "two"],
        "email_template": "LLM-EMAIL",
    }
    offer = _offer()
    plan = SalaryNegotiator().plan(offer)
    script = await ScriptWriter(ai_client=_StubClient(payload)).write(
        offer, plan, tone="firm",
    )
    assert script.tone == "firm"
    assert script.opening == "LLM-OPEN"
    assert script.email_template == "LLM-EMAIL"
    assert script.talking_points == ["one", "two"]


@pytest.mark.asyncio
async def test_script_writer_falls_back_when_llm_raises():
    offer = _offer()
    plan = SalaryNegotiator().plan(offer)
    script = await ScriptWriter(ai_client=_RaisingClient()).write(offer, plan)
    assert script.opening
    assert script.anchor
    assert "Subject:" in script.email_template
    assert script.tone == "collaborative"


@pytest.mark.asyncio
async def test_script_writer_normalizes_unknown_tone():
    offer = _offer()
    plan = SalaryNegotiator().plan(offer)
    script = await ScriptWriter(ai_client=_RaisingClient()).write(offer, plan, tone="aggressive")
    assert script.tone == "collaborative"


# ─── end-to-end via integration helper ─────────────────────────────

@pytest.mark.asyncio
async def test_generate_negotiation_e2e():
    report = await generate_negotiation(_offer(), tone="warm")
    assert report.plan.counter_base > 0
    assert report.script.tone == "warm"
    assert report.script.email_template
    assert isinstance(report.latency_ms, int)


# ─── tool registry ─────────────────────────────────────────────────

def test_build_salary_tools_registers_negotiation():
    reg = build_salary_tools()
    tool = reg.get("generate_salary_negotiation")
    assert tool is not None
    assert "offer" in tool.parameters["required"]
