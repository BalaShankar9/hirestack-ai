"""Phase D.1 — DocumentGeneratorChain.generate_cv_variants unit tests."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ai_engine.chains.document_generator import DocumentGeneratorChain


def _make_chain(complete_side_effect):
    ai = AsyncMock()
    ai.complete = AsyncMock(side_effect=complete_side_effect)
    return DocumentGeneratorChain(ai), ai


@pytest.mark.asyncio
async def test_generates_two_variants_in_parallel_by_default() -> None:
    calls: list[dict] = []

    async def fake_complete(**kwargs):
        calls.append(kwargs)
        # echo the variant nudge so we can assert it landed in the prompt
        if "CONCISE" in kwargs["prompt"]:
            return "## Concise CV body"
        if "NARRATIVE" in kwargs["prompt"]:
            return "## Narrative CV body"
        return ""

    chain, _ = _make_chain(fake_complete)

    out = await chain.generate_cv_variants(
        user_profile={"name": "Test"},
        job_title="SWE",
        company="Acme",
        job_requirements={"must_have": ["python"]},
    )

    assert len(out) == 2
    keys = [v["variant"] for v in out]
    assert keys == ["concise", "narrative"]
    assert out[0]["label"] == "Concise"
    assert out[1]["label"] == "Narrative"
    assert "Concise CV body" in out[0]["content"]
    assert "Narrative CV body" in out[1]["content"]
    assert len(calls) == 2  # two LLM calls


@pytest.mark.asyncio
async def test_respects_explicit_variant_list() -> None:
    async def fake_complete(**kwargs):
        return "body"

    chain, _ = _make_chain(fake_complete)
    out = await chain.generate_cv_variants(
        user_profile={},
        job_title="t",
        company="c",
        job_requirements={},
        variants=["narrative"],
    )
    assert [v["variant"] for v in out] == ["narrative"]


@pytest.mark.asyncio
async def test_filters_unknown_variant_keys() -> None:
    async def fake_complete(**kwargs):
        return "body"

    chain, _ = _make_chain(fake_complete)
    out = await chain.generate_cv_variants(
        user_profile={},
        job_title="t",
        company="c",
        job_requirements={},
        variants=["bogus", "concise", "also-bogus"],
    )
    assert [v["variant"] for v in out] == ["concise"]


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_valid_variants() -> None:
    async def fake_complete(**kwargs):
        return "body"

    chain, ai = _make_chain(fake_complete)
    out = await chain.generate_cv_variants(
        user_profile={},
        job_title="t",
        company="c",
        job_requirements={},
        variants=["unknown-only"],
    )
    assert out == []
    ai.complete.assert_not_called()


@pytest.mark.asyncio
async def test_one_variant_failure_does_not_break_the_other() -> None:
    async def fake_complete(**kwargs):
        if "NARRATIVE" in kwargs["prompt"]:
            raise RuntimeError("transient model error")
        return "concise body"

    chain, _ = _make_chain(fake_complete)
    out = await chain.generate_cv_variants(
        user_profile={},
        job_title="t",
        company="c",
        job_requirements={},
    )
    assert len(out) == 2
    by_key = {v["variant"]: v for v in out}
    assert by_key["concise"]["content"] == "concise body"
    assert by_key["narrative"]["content"] == ""  # graceful empty


@pytest.mark.asyncio
async def test_variant_styles_use_distinct_temperatures() -> None:
    seen_temps: dict[str, float] = {}

    async def fake_complete(**kwargs):
        if "CONCISE" in kwargs["prompt"]:
            seen_temps["concise"] = kwargs["temperature"]
        elif "NARRATIVE" in kwargs["prompt"]:
            seen_temps["narrative"] = kwargs["temperature"]
        return "x"

    chain, _ = _make_chain(fake_complete)
    await chain.generate_cv_variants(
        user_profile={},
        job_title="t",
        company="c",
        job_requirements={},
    )
    # narrative should have higher creativity
    assert seen_temps["narrative"] > seen_temps["concise"]
