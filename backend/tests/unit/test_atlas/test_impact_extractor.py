"""Unit tests for ATLAS impact_extractor."""
from __future__ import annotations

import asyncio

import pytest

from ai_engine.agents.artifact_contracts import ImpactSignal
from ai_engine.agents.sub_agents.atlas.impact_extractor import (
    ImpactExtractor,
    _evidence_for,
    _normalize_metric,
    _scan_regex,
)


_run = asyncio.run


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Users", "users"),
        ("Sign-Ups", "signups"),
        ("ARR", "arr"),
        ("cost savings", "cost_savings"),
    ],
)
def test_normalize_metric(raw, expected):
    assert _normalize_metric(raw) == expected


def test_evidence_for_returns_sentence():
    text = "We hired ten engineers. Then we shipped to 10M users in Q3. Then we celebrated."
    span = text.find("10M users")
    ev = _evidence_for(text, span, span + len("10M users"))
    assert "10M users" in ev
    # Sentence boundary worked — celebration sentence excluded
    assert "celebrated" not in ev


# ---------------------------------------------------------------------------
# Regex scan — counts / units
# ---------------------------------------------------------------------------

def test_scan_qty_unit_users():
    text = "Built a platform serving 10M+ users across 3 continents."
    hits = _scan_regex(text, source="resume")
    metrics = [h.metric for h in hits]
    values = [h.value for h in hits]
    assert "users" in metrics
    assert "10M+" in values
    user_hit = next(h for h in hits if h.metric == "users")
    assert user_hit.confidence == 0.7
    assert user_hit.source == "resume"
    assert "10M+ users" in user_hit.evidence


def test_scan_money_with_dollar_sign():
    text = "Drove $2.4M in ARR over 18 months."
    hits = _scan_regex(text, source="resume")
    arr = [h for h in hits if h.metric == "arr"]
    assert arr, f"expected ARR signal, got {hits}"
    assert arr[0].value == "2.4M"


def test_scan_money_skips_bare_number_no_unit():
    """Bare number with no $ and no money unit must NOT trigger money regex."""
    text = "I have 10 cats."
    hits = _scan_regex(text, source="r")
    # No money / count / team-size / pct match expected
    assert hits == []


def test_scan_team_size():
    text = "Managed 12 engineers across two timezones."
    hits = _scan_regex(text, source="resume")
    team = [h for h in hits if h.metric == "team_size"]
    assert team and team[0].value == "12"


def test_scan_team_of_phrasing():
    text = "Led a team of 8 and shipped weekly."
    hits = _scan_regex(text, source="resume")
    team = [h for h in hits if h.metric == "team_size"]
    assert team and team[0].value == "8"


def test_scan_percent_growth():
    text = "Grew monthly active users by 40% in two quarters."
    hits = _scan_regex(text, source="resume")
    pct = [h for h in hits if h.metric == "growth_pct"]
    assert pct
    assert pct[0].value == "40%"


def test_scan_percent_reduction():
    text = "Reduced p99 latency by 35% via caching."
    hits = _scan_regex(text, source="resume")
    red = [h for h in hits if h.metric == "reduction_pct"]
    assert red and red[0].value == "35%"


def test_scan_dedupes_identical_matches():
    """Same metric+value+evidence prefix should appear only once."""
    text = "Served 5M users. Served 5M users."
    hits = _scan_regex(text, source="r")
    user_hits = [h for h in hits if h.metric == "users"]
    # Identical sentence repeats → identical evidence → dedupe to 1
    assert len(user_hits) == 1
    # Distinct sentences with same metric+value → both kept (different evidence)
    text2 = "Served 5M users last year. Then we onboarded 5M users in Asia."
    user2 = [h for h in _scan_regex(text2, source="r") if h.metric == "users"]
    assert len(user2) == 2


def test_scan_returns_impact_signal_instances():
    text = "Built a 500K user product."
    hits = _scan_regex(text, source="resume")
    assert all(isinstance(h, ImpactSignal) for h in hits)


# ---------------------------------------------------------------------------
# ImpactExtractor.extract — async path
# ---------------------------------------------------------------------------

def test_extract_empty_text_returns_empty():
    ex = ImpactExtractor()
    assert _run(ex.extract("")) == []
    assert _run(ex.extract("   \n  ")) == []


def test_extract_no_client_no_regex_hits_returns_empty():
    ex = ImpactExtractor()
    out = _run(ex.extract("I am a thoughtful engineer who cares about people."))
    assert out == []


def test_extract_regex_hits_skips_llm_fallback():
    class _BoomClient:
        async def complete_json(self, **_kw):
            raise AssertionError("LLM must NOT be called when regex hits exist")

    ex = ImpactExtractor(ai_client=_BoomClient())
    out = _run(ex.extract("Shipped to 1M users last year."))
    assert out and out[0].metric == "users"


def test_extract_llm_fallback_invoked_when_regex_zero():
    class _StubClient:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **_kw):
            self.calls += 1
            return {
                "signals": [
                    {"metric": "team_size", "value": "9", "evidence": "led nine devs"}
                ]
            }

    client = _StubClient()
    ex = ImpactExtractor(ai_client=client)
    out = _run(ex.extract("I am a thoughtful engineer who cares about people."))
    assert client.calls == 1
    assert out and out[0].metric == "team_size"
    assert out[0].confidence == 0.5  # LLM confidence
    assert out[0].value == "9"


def test_extract_llm_fallback_handles_exception():
    class _BoomClient:
        async def complete_json(self, **_kw):
            raise RuntimeError("network down")

    ex = ImpactExtractor(ai_client=_BoomClient())
    out = _run(ex.extract("I am a thoughtful engineer who cares about people."))
    assert out == []  # graceful degrade


def test_extract_llm_fallback_filters_invalid_items():
    class _DirtyClient:
        async def complete_json(self, **_kw):
            return {
                "signals": [
                    {"metric": "users", "value": ""},          # empty value
                    {"metric": "", "value": "10M"},            # empty metric
                    "garbage",                                  # not a dict
                    {"metric": "Revenue", "value": "$1M",
                     "evidence": " " * 500},                   # caps evidence
                ]
            }

    ex = ImpactExtractor(ai_client=_DirtyClient())
    out = _run(ex.extract("I am a thoughtful engineer who cares about people."))
    assert len(out) == 1
    assert out[0].metric == "revenue"  # normalized lowercase
    assert out[0].value == "$1M"
    assert len(out[0].evidence) <= 280


def test_extract_llm_fallback_handles_non_dict_payload():
    class _WeirdClient:
        async def complete_json(self, **_kw):
            return ["nope", "this is a list"]

    ex = ImpactExtractor(ai_client=_WeirdClient())
    out = _run(ex.extract("vague text without numbers"))
    assert out == []


def test_extract_llm_fallback_handles_missing_signals_key():
    class _EmptyClient:
        async def complete_json(self, **_kw):
            return {}  # no 'signals' key

    ex = ImpactExtractor(ai_client=_EmptyClient())
    out = _run(ex.extract("vague text"))
    assert out == []
