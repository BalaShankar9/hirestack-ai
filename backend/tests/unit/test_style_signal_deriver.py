"""Phase C.2 — derive_style_signals unit tests."""
from __future__ import annotations

from ai_engine.agents.style_signal_deriver import derive_style_signals


GOOD_SCORES = {"impact": 85, "clarity": 80, "tone_match": 78, "completeness": 82}
MEDIOCRE_SCORES = {"impact": 60, "clarity": 65, "tone_match": 55, "completeness": 60}


def test_returns_empty_when_quality_below_threshold() -> None:
    out = derive_style_signals(
        draft_content="x" * 1000,
        critic_quality_scores=MEDIOCRE_SCORES,
    )
    assert out == {}


def test_returns_empty_when_fact_check_flags_fabrication() -> None:
    out = derive_style_signals(
        draft_content="some content " * 100,
        critic_quality_scores=GOOD_SCORES,
        fact_check_summary={"fabricated": 2},
    )
    assert out == {}


def test_length_bucket_short() -> None:
    out = derive_style_signals(
        draft_content=" ".join(["word"] * 150),
        critic_quality_scores=GOOD_SCORES,
    )
    assert out.get("length") == "short"


def test_length_bucket_medium() -> None:
    out = derive_style_signals(
        draft_content=" ".join(["word"] * 300),
        critic_quality_scores=GOOD_SCORES,
    )
    assert out.get("length") == "medium"


def test_length_bucket_long() -> None:
    out = derive_style_signals(
        draft_content=" ".join(["word"] * 700),
        critic_quality_scores=GOOD_SCORES,
    )
    assert out.get("length") == "long"


def test_length_skipped_for_truncated_draft() -> None:
    out = derive_style_signals(
        draft_content="too short",
        critic_quality_scores=GOOD_SCORES,
    )
    assert "length" not in out


def test_extracts_content_from_dict_payload() -> None:
    out = derive_style_signals(
        draft_content={"content": " ".join(["word"] * 300)},
        critic_quality_scores=GOOD_SCORES,
    )
    assert out.get("length") == "medium"


def test_tone_inferred_from_jd_when_tone_match_strong() -> None:
    jd = (
        "We are a regulated enterprise looking for a stakeholder-focused "
        "executive to drive compliance, governance and board reporting."
    )
    out = derive_style_signals(
        draft_content=" ".join(["word"] * 300),
        critic_quality_scores=GOOD_SCORES,
        enriched_context={"jd_text": jd},
    )
    assert out.get("tone") == "formal"


def test_tone_skipped_when_tone_match_weak() -> None:
    weak = {**GOOD_SCORES, "tone_match": 60}
    jd = "regulated compliance governance stakeholder enterprise"
    out = derive_style_signals(
        draft_content=" ".join(["word"] * 300),
        critic_quality_scores=weak,
        enriched_context={"jd_text": jd},
    )
    assert "tone" not in out


def test_tone_skipped_when_jd_signal_too_weak() -> None:
    jd = "We need a great teammate who codes."
    out = derive_style_signals(
        draft_content=" ".join(["word"] * 300),
        critic_quality_scores=GOOD_SCORES,
        enriched_context={"jd_text": jd},
    )
    assert "tone" not in out


def test_preferred_keywords_intersect_jd_and_draft() -> None:
    jd = (
        "Looking for distributed systems expert with kubernetes kafka rust "
        "experience building scalable microservices observability."
    )
    draft = (
        "I have built distributed kubernetes microservices using rust "
        "with deep observability for scalable systems. " * 10
    )
    out = derive_style_signals(
        draft_content=draft,
        critic_quality_scores=GOOD_SCORES,
        enriched_context={"jd_text": jd},
    )
    kw = out.get("preferred_keywords", [])
    assert "kubernetes" in kw
    assert "distributed" in kw
    assert "rust" in kw


def test_preferred_keywords_skipped_when_too_few_overlap() -> None:
    jd = "kubernetes kafka rust scalability microservices"
    draft = "I write web pages using JavaScript and CSS. " * 30
    out = derive_style_signals(
        draft_content=draft,
        critic_quality_scores=GOOD_SCORES,
        enriched_context={"jd_text": jd},
    )
    assert "preferred_keywords" not in out
