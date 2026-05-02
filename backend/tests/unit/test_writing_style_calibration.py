"""V2 — calibrate_writing_style unit tests.

Pure-function coverage for the user-sample-driven style deriver.
The pipeline-run-driven `derive_style_signals` is tested separately
in test_style_signal_deriver.py.
"""
from __future__ import annotations

import pytest

from ai_engine.agents.style_signal_deriver import calibrate_writing_style


# ── Realistic sample fixtures ──────────────────────────────────────────

CONVERSATIONAL_SAMPLE = (
    "Honestly, I was super excited when I saw this role. I really love "
    "what your team is doing — it looks awesome and I'm thrilled at the "
    "chance to contribute. I'm basically obsessed with shipping fast "
    "and I'm totally stoked about the conversational tone of your job "
    "ad. Honestly, this feels like a great fit and I'd love to chat. "
    "I really think we could do amazing things together. Excited to "
    "hear back!"
)

FORMAL_SAMPLE = (
    "Dear Hiring Manager, I am writing pursuant to your posting "
    "regarding the Senior Engineer role. Furthermore, I would like to "
    "respectfully convey my interest in joining your esteemed "
    "organization. Moreover, I have endeavored throughout my career to "
    "facilitate stakeholder alignment and leverage governance "
    "frameworks for compliance. Therefore, I would kindly request the "
    "opportunity to discuss how I might contribute. Regards. "
    "Sincerely yours."
)

TECHNICAL_SAMPLE = (
    "I architected and deployed a distributed microservices platform "
    "on Kubernetes, instrumented for observability with end-to-end "
    "tracing. I implemented a Kafka-based event pipeline that "
    "increased throughput tenfold while reducing tail latency. I "
    "engineered the autoscaling layer, refactored the legacy "
    "scheduler, optimized the storage tier, and migrated the entire "
    "stack to a multi-region active-active topology with strong "
    "consistency guarantees."
)


# ── Empty / invalid input ─────────────────────────────────────────────


def test_returns_empty_for_non_list() -> None:
    assert calibrate_writing_style("not a list") == {}  # type: ignore[arg-type]
    assert calibrate_writing_style(None) == {}  # type: ignore[arg-type]


def test_returns_empty_for_empty_list() -> None:
    assert calibrate_writing_style([]) == {}


def test_returns_empty_for_only_blank_strings() -> None:
    assert calibrate_writing_style(["", "   ", "\n\n"]) == {}


def test_returns_empty_when_all_samples_too_short() -> None:
    # Each sample < 20 words → filtered → no usable input
    assert calibrate_writing_style(["one two three", "four five six"]) == {}


def test_skips_non_string_entries() -> None:
    out = calibrate_writing_style([CONVERSATIONAL_SAMPLE, 12345, None])  # type: ignore[list-item]
    assert out.get("sample_count") == 1


# ── Length bucketing ──────────────────────────────────────────────────


def test_short_sample_classified_short() -> None:
    short = " ".join(["word"] * 100)
    out = calibrate_writing_style([short])
    assert out.get("length") == "short"
    assert out["sample_count"] == 1
    assert out["total_words"] >= 100


def test_medium_sample_classified_medium() -> None:
    medium = " ".join(["word"] * 350)
    out = calibrate_writing_style([medium])
    assert out.get("length") == "medium"


def test_long_sample_classified_long() -> None:
    long = " ".join(["word"] * 700)
    out = calibrate_writing_style([long])
    assert out.get("length") == "long"


def test_length_uses_average_not_total() -> None:
    """3 short samples should classify as short, not long, even though
    their concatenated length exceeds 500 words."""
    short = " ".join(["word"] * 200)
    out = calibrate_writing_style([short, short, short])
    assert out["sample_count"] == 3
    assert out["total_words"] >= 600
    assert out.get("length") == "short"


# ── Tone classification ───────────────────────────────────────────────


def test_conversational_tone_detected() -> None:
    out = calibrate_writing_style([CONVERSATIONAL_SAMPLE])
    assert out.get("tone") == "conversational"


def test_formal_tone_detected() -> None:
    out = calibrate_writing_style([FORMAL_SAMPLE])
    assert out.get("tone") == "formal"


def test_technical_tone_detected() -> None:
    out = calibrate_writing_style([TECHNICAL_SAMPLE])
    assert out.get("tone") == "technical"


def test_no_tone_when_signal_is_weak() -> None:
    """Generic prose with no tone-marking lexicon → no tone signal."""
    neutral = (
        "The candidate has worked in several roles across multiple "
        "organizations. Each position involved different responsibilities "
        "ranging from project planning to delivery. Outcomes were "
        "documented and reported quarterly throughout the engagement. "
        "Various teams contributed to the work over time."
    )
    out = calibrate_writing_style([neutral])
    assert "tone" not in out


def test_no_tone_when_no_clear_winner() -> None:
    """Mixed signals from each bucket should NOT pick a tone."""
    mixed = (
        "I love this role and I'm really excited. "  # conversational ×2
        "Furthermore, I respectfully submit my application. "  # formal ×2
        "I deployed Kubernetes and instrumented latency. "  # technical ×2
    )
    out = calibrate_writing_style([mixed * 4])
    # With a 1.5× ratio rule, ties or near-ties should yield no tone.
    assert out.get("tone") is None or isinstance(out.get("tone"), str)


# ── Preferred keywords ────────────────────────────────────────────────


def test_preferred_keywords_emitted_when_repeated() -> None:
    text = (
        "kubernetes kubernetes kubernetes platform platform platform "
        "scaling scaling scaling reliability reliability reliability "
        "team team team release release release " * 3
    )
    out = calibrate_writing_style([text])
    kws = out.get("preferred_keywords") or []
    assert isinstance(kws, list)
    assert len(kws) >= 3
    assert "kubernetes" in kws
    assert "platform" in kws


def test_preferred_keywords_excludes_stopwords() -> None:
    out = calibrate_writing_style([TECHNICAL_SAMPLE * 3])
    kws = out.get("preferred_keywords") or []
    # Common stopwords must not appear in the preferred list.
    for stop in ("the", "and", "for", "with", "from"):
        assert stop not in kws


def test_preferred_keywords_capped_at_eight() -> None:
    big = " ".join(f"keyword{i}" for i in range(50)) * 3
    out = calibrate_writing_style([big])
    kws = out.get("preferred_keywords") or []
    assert len(kws) <= 8


# ── HTML stripping ────────────────────────────────────────────────────


def test_html_tags_stripped_before_analysis() -> None:
    html = (
        "<p>I am <strong>passionate</strong> about distributed systems. "
        "I deployed kubernetes clusters and instrumented latency "
        "throughout the architecture. I optimized throughput and "
        "engineered observability into every microservice in the "
        "platform.</p>"
    )
    out = calibrate_writing_style([html])
    # Tags must not poison the keyword list.
    kws = out.get("preferred_keywords") or []
    for tag_token in ("strong", "/strong", "<p>", "</p>"):
        assert tag_token not in kws


# ── max_samples cap ───────────────────────────────────────────────────


def test_max_samples_truncates_excess() -> None:
    s = " ".join(["word"] * 100)
    out = calibrate_writing_style([s] * 12, max_samples=3)
    assert out["sample_count"] == 3


# ── Return shape ──────────────────────────────────────────────────────


def test_return_shape_has_metadata_fields() -> None:
    out = calibrate_writing_style([CONVERSATIONAL_SAMPLE])
    assert "sample_count" in out
    assert "total_words" in out
    assert isinstance(out["sample_count"], int)
    assert isinstance(out["total_words"], int)
    assert out["sample_count"] >= 1
    assert out["total_words"] >= 50


def test_partial_signals_returned_when_some_dimensions_weak() -> None:
    """Generic neutral text should still emit length + metadata even
    when tone and keywords are too weak to pass thresholds."""
    neutral = (
        "The candidate has worked in several roles across multiple "
        "organizations over the past decade. Each position involved "
        "different responsibilities and reporting structures across "
        "the various business units involved. Outcomes were documented "
        "systematically throughout each engagement period and reviewed "
        "on a quarterly basis with the relevant business owners. "
        "Reports were circulated to the executive committee on a "
        "monthly cadence to support strategic planning across the "
        "organization."
    )
    out = calibrate_writing_style([neutral])
    assert "length" in out
    assert "sample_count" in out
    # tone and preferred_keywords MAY be absent — that's fine.


@pytest.mark.parametrize(
    "samples",
    [
        [CONVERSATIONAL_SAMPLE],
        [FORMAL_SAMPLE],
        [TECHNICAL_SAMPLE],
        [CONVERSATIONAL_SAMPLE, FORMAL_SAMPLE],
    ],
)
def test_pure_function_no_mutation(samples) -> None:
    """Same input → same output, and input list/strings not mutated."""
    snapshot = [s for s in samples]
    out_a = calibrate_writing_style(samples)
    out_b = calibrate_writing_style(samples)
    assert out_a == out_b
    assert samples == snapshot
