"""Live eval for AIM reviewer. Gated on AIM_EVAL_LIVE=1.

Strong corpus entries should clear the PASS_THRESHOLD with all dimensions
passing; weak entries should land below REVISION_THRESHOLD so the gate
flags them for regeneration. Drift in either direction is a regression.
"""
from __future__ import annotations

import os

import pytest

from ai_engine.agents.aim.reviewer import (
    AIMReviewerAgent,
    PASS_THRESHOLD,
    REVISION_THRESHOLD,
)
from ai_engine.evals.aim_corpus import AIM_REVIEWER_CORPUS

pytestmark = pytest.mark.aim_eval

LIVE = os.getenv("AIM_EVAL_LIVE") == "1"

_STRONG = [c for c in AIM_REVIEWER_CORPUS if c["expected"] == "pass"]
_WEAK = [c for c in AIM_REVIEWER_CORPUS if c["expected"] == "fail"]


@pytest.mark.skipif(not LIVE, reason="set AIM_EVAL_LIVE=1 to run live AIM evals")
@pytest.mark.parametrize("case", _STRONG, ids=lambda c: c["id"])
@pytest.mark.asyncio
async def test_reviewer_passes_strong_sections(case):
    agent = AIMReviewerAgent()
    result = await agent.run({
        "section_content": case["section"],
        "section_meta": case["section_meta"],
        "parsed": case["parsed"],
        "recon": {},
    })
    content = result.content
    weighted = float(content["weighted_score"])
    sub = content["sub_scores"]
    assert weighted >= PASS_THRESHOLD, (
        f"{case['id']}: weighted {weighted} below PASS_THRESHOLD {PASS_THRESHOLD}; "
        f"sub_scores={sub}"
    )
    failing_dims = {k: v for k, v in sub.items() if float(v) < PASS_THRESHOLD}
    assert not failing_dims, (
        f"{case['id']}: weighted ok but dims below threshold: {failing_dims}"
    )
    assert content["verdict"] == "pass"


@pytest.mark.skipif(not LIVE, reason="set AIM_EVAL_LIVE=1 to run live AIM evals")
@pytest.mark.parametrize("case", _WEAK, ids=lambda c: c["id"])
@pytest.mark.asyncio
async def test_reviewer_rejects_weak_sections(case):
    agent = AIMReviewerAgent()
    result = await agent.run({
        "section_content": case["section"],
        "section_meta": case["section_meta"],
        "parsed": case["parsed"],
        "recon": {},
    })
    content = result.content
    weighted = float(content["weighted_score"])
    assert weighted < REVISION_THRESHOLD, (
        f"{case['id']}: weighted {weighted} should be below REVISION_THRESHOLD "
        f"{REVISION_THRESHOLD}; sub_scores={content['sub_scores']}"
    )
    assert content["verdict"] in {"revise", "reject"}
