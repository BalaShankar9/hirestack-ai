"""
Contract tests for DocumentVariantChain.compare_variants.

Pins the behaviour ratified in ADR-0016 (Variant Lab winner pick):
  - scoring is deterministic from heuristics
  - composite weights are evidence_coverage 0.45, ats 0.35, readability 0.20
  - winner is the highest-composite variant
  - winner reasoning is AI-generated but the AI cannot override the pick
  - failure of the reasoning call is non-fatal (deterministic fallback)
  - delta_vs_original is present iff original_content is supplied
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from ai_engine.chains.doc_variant import (
    WINNER_WEIGHTS,
    DocumentVariantChain,
    _ats_score,
    _composite,
    _keyword_density,
    _readability_score,
)


WINNER_REASONING_TEXT = "This variant best matches the role's evidence profile."


def _make_chain() -> DocumentVariantChain:
    client = AsyncMock()
    client.complete_json = AsyncMock(return_value={"reasoning": WINNER_REASONING_TEXT})
    return DocumentVariantChain(client)


# ── heuristic primitives ──────────────────────────────────────────────────


def test_keyword_density_zero_when_no_keywords() -> None:
    assert _keyword_density("anything", []) == 0.0


def test_keyword_density_percent_of_distinct_keywords_present() -> None:
    text = "Built scalable python pipelines on kubernetes with terraform"
    keywords = ["python", "kubernetes", "react", "rust"]
    # 2 of 4 → 50.0
    assert _keyword_density(text, keywords) == 50.0


def test_readability_score_penalises_long_sentences() -> None:
    short = "Built systems. Shipped fast. Scaled well."
    long = "Built systems and shipped fast and scaled well " * 6 + "."
    assert _readability_score(short) > _readability_score(long)


def test_ats_score_bounded_0_to_100() -> None:
    keywords = ["python", "kubernetes"]
    assert 0 <= _ats_score("", keywords) <= 100
    assert 0 <= _ats_score("python kubernetes " * 200, keywords) <= 100


def test_composite_weights_sum_to_one() -> None:
    assert round(sum(WINNER_WEIGHTS.values()), 6) == 1.0


def test_composite_picks_evidence_heavy_variant() -> None:
    # Variant A has higher coverage, B has higher readability.
    a = _composite({"evidence_coverage": 90.0, "ats_score": 70.0, "readability_score": 60.0})
    b = _composite({"evidence_coverage": 50.0, "ats_score": 70.0, "readability_score": 95.0})
    # 0.45*90 + 0.35*70 + 0.20*60 = 40.5 + 24.5 + 12.0 = 77.0
    # 0.45*50 + 0.35*70 + 0.20*95 = 22.5 + 24.5 + 19.0 = 66.0
    assert a > b


# ── compare_variants behaviour ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compare_variants_returns_one_row_per_input() -> None:
    chain = _make_chain()
    result = await chain.compare_variants(
        variants={
            "conservative": "python kubernetes terraform " * 5,
            "balanced": "python kubernetes " * 5,
            "creative": "python " * 5,
        },
        job_title="Senior Platform Engineer python kubernetes terraform",
    )
    assert len(result["comparison"]) == 3
    assert {row["variant"] for row in result["comparison"]} == {
        "conservative",
        "balanced",
        "creative",
    }


@pytest.mark.asyncio
async def test_compare_variants_winner_has_highest_composite() -> None:
    chain = _make_chain()
    result = await chain.compare_variants(
        variants={
            "conservative": "python kubernetes terraform docker " * 8,
            "balanced": "python kubernetes " * 8,
            "creative": "python " * 8,
        },
        job_title="Platform engineer python kubernetes terraform docker",
    )
    winner = result["winner"]
    assert winner is not None
    composites = {row["variant"]: row["composite_score"] for row in result["comparison"]}
    assert winner["variant"] == max(composites, key=lambda k: composites[k])
    assert winner["composite_score"] == max(composites.values())


@pytest.mark.asyncio
async def test_compare_variants_includes_evidence_coverage_per_variant() -> None:
    chain = _make_chain()
    result = await chain.compare_variants(
        variants={"balanced": "python kubernetes terraform"},
        job_title="python kubernetes terraform docker",
    )
    row = result["comparison"][0]
    assert "evidence_coverage" in row
    assert row["evidence_coverage"] == row["keyword_density"]


@pytest.mark.asyncio
async def test_compare_variants_delta_vs_original_present_when_original_supplied() -> None:
    chain = _make_chain()
    result = await chain.compare_variants(
        variants={"balanced": "python kubernetes terraform docker " * 4},
        job_title="python kubernetes terraform docker",
        original_content="python " * 4,
    )
    row = result["comparison"][0]
    assert "delta_vs_original" in row
    delta = row["delta_vs_original"]
    assert set(delta.keys()) == {"ats_score", "readability_score", "evidence_coverage"}
    assert delta["evidence_coverage"] >= 0  # variant covers more keywords than original


@pytest.mark.asyncio
async def test_compare_variants_no_delta_when_no_original() -> None:
    chain = _make_chain()
    result = await chain.compare_variants(
        variants={"balanced": "python"},
        job_title="python",
    )
    assert "delta_vs_original" not in result["comparison"][0]


@pytest.mark.asyncio
async def test_compare_variants_uses_ai_reasoning_when_available() -> None:
    chain = _make_chain()
    result = await chain.compare_variants(
        variants={"balanced": "python", "creative": "python kubernetes"},
        job_title="python kubernetes",
    )
    assert result["winner"]["reasoning"] == WINNER_REASONING_TEXT


@pytest.mark.asyncio
async def test_compare_variants_reasoning_failure_falls_back_to_blurb() -> None:
    client = AsyncMock()
    client.complete_json = AsyncMock(side_effect=RuntimeError("LLM down"))
    chain = DocumentVariantChain(client)
    result = await chain.compare_variants(
        variants={"balanced": "python"},
        job_title="python",
    )
    assert result["winner"]["reasoning"]  # non-empty
    assert "balanced" in result["winner"]["reasoning"].lower() or "evidence" in result["winner"]["reasoning"].lower() or "score" in result["winner"]["reasoning"].lower()


@pytest.mark.asyncio
async def test_compare_variants_ai_cannot_override_score_pick() -> None:
    """ADR-0016 contract: the AI returns reasoning only; the winner is
    chosen by composite score, not by the LLM. Even if the LLM tries to
    sneak in a different tone in its reasoning string, the winner.variant
    must equal the highest-composite tone."""
    client = AsyncMock()
    client.complete_json = AsyncMock(
        return_value={"reasoning": "Actually, conservative is better."}
    )
    chain = DocumentVariantChain(client)
    result = await chain.compare_variants(
        variants={
            "conservative": "python " * 2,  # low coverage
            "balanced": "python kubernetes terraform docker " * 6,  # high coverage
            "creative": "python " * 2,
        },
        job_title="python kubernetes terraform docker",
    )
    composites = {row["variant"]: row["composite_score"] for row in result["comparison"]}
    expected_winner = max(composites, key=lambda k: composites[k])
    assert result["winner"]["variant"] == expected_winner
    assert expected_winner == "balanced"


@pytest.mark.asyncio
async def test_compare_variants_empty_input_returns_no_winner() -> None:
    chain = _make_chain()
    result = await chain.compare_variants(variants={}, job_title="python")
    assert result["comparison"] == []
    assert result["winner"] is None
    assert result["weights"] == dict(WINNER_WEIGHTS)


# ── alias bug fix: original_content kwarg ─────────────────────────────────


@pytest.mark.asyncio
async def test_generate_variant_accepts_original_content_alias() -> None:
    """Service layer historically called generate_variant(original_content=...).
    Chain now accepts that alias to keep the production /api/variants/generate
    route working."""
    client = AsyncMock()
    client.complete = AsyncMock(return_value="rewritten body")
    chain = DocumentVariantChain(client)
    result = await chain.generate_variant(
        original_content="some source text",
        tone="balanced",
    )
    assert result == "rewritten body"
    # Confirm the kwarg actually reached the prompt.
    call_kwargs = client.complete.await_args.kwargs
    assert "some source text" in call_kwargs["prompt"]
