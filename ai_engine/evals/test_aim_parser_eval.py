"""Live eval for AIM parser. Gated on AIM_EVAL_LIVE=1 to avoid burning quota in CI."""
from __future__ import annotations

import os

import pytest

from ai_engine.agents.aim.parser import AIMParserAgent
from ai_engine.evals.aim_corpus import AIM_PARSER_CORPUS

pytestmark = pytest.mark.aim_eval

LIVE = os.getenv("AIM_EVAL_LIVE") == "1"


@pytest.mark.skipif(not LIVE, reason="set AIM_EVAL_LIVE=1 to run live AIM evals")
@pytest.mark.parametrize("case", AIM_PARSER_CORPUS, ids=lambda c: c["id"])
@pytest.mark.asyncio
async def test_parser_extracts_directive_and_word_count(case):
    agent = AIMParserAgent()
    result = await agent.run({"brief_text": case["brief"], "rubric_text": ""})
    parsed = result.content

    directive = (parsed.get("directive") or "").lower()
    assert any(k in directive for k in case["expected_directive_keywords"]), (
        f"directive '{directive}' missing expected keywords {case['expected_directive_keywords']}"
    )

    wc = parsed.get("word_count_target") or parsed.get("word_count") or 0
    # Allow \u00b110% slack on word count parsing
    target = case["expected_word_count"]
    assert abs(int(wc) - target) <= int(target * 0.1), (
        f"word count {wc} too far from expected {target}"
    )
