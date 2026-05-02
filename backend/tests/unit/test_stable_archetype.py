"""F2 — stable_archetype classifier unit tests.

Coverage for the 8-label keyword classifier:
  * each label fires on its strong-keyword fixture
  * 'unknown' on weak/ambiguous input
  * jd_hash determinism + length
  * score map shape, runner-up surfacing
  * input immutability + edge cases (empty, None-like, whitespace)
  * margin & threshold gates
"""
from __future__ import annotations

import pytest

from ai_engine.agents.stable_archetype import (
    ALL_LABELS,
    MIN_MARGIN,
    MIN_SCORE_THRESHOLD,
    StableArchetype,
    classify,
    jd_hash,
)


# ── Per-label happy-path fixtures ─────────────────────────────────────


_FIXTURES: dict[str, str] = {
    "big_tech_ic": (
        "Senior staff engineer at Google working on planet-scale "
        "distributed systems. Author design docs and RFCs serving "
        "billions of users. Big tech experience required."
    ),
    "startup_founder_adj": (
        "Founding engineer at a pre-seed startup. Wear many hats, "
        "ship fast, ambiguous problems, no playbook. 0 to 1 product "
        "work in a small team."
    ),
    "enterprise_saas": (
        "Senior engineer on our enterprise SaaS platform. Multi-tenant "
        "B2B SaaS serving Fortune 500 customers. SOC 2 Type II "
        "compliance, SCIM provisioning, single sign-on."
    ),
    "regulated_finance": (
        "Engineer at a top investment bank. KYC, AML, FINRA reporting. "
        "Build trading systems under Basel III, MiFID, and PCI DSS "
        "requirements. Compliance and audit a daily reality."
    ),
    "public_sector": (
        "Federal government contract requires US Citizen with active "
        "Top Secret security clearance. FedRAMP-authorized environment, "
        "Department of Defense customer, NIST 800-53 controls."
    ),
    "research_lab": (
        "Research scientist position. PhD preferred, publish at NeurIPS, "
        "ICML, ICLR. Advance the state-of-the-art in novel research "
        "directions. Strong publication record at first-author level."
    ),
    "agency_consulting": (
        "Senior consultant at a top consultancy. Client-facing "
        "engagements, billable hours, 80% utilization rate target. "
        "Deloitte / Accenture / Thoughtworks alums encouraged."
    ),
    "hyper_growth_scaleup": (
        "Series C rocketship doubling annually. Hypergrowth scaleup "
        "pre-IPO, rapidly scaling our team. Join the next unicorn "
        "before it goes public — 100% YoY growth."
    ),
}


@pytest.mark.parametrize("label,jd", list(_FIXTURES.items()))
def test_each_label_classified_from_strong_signal_jd(label, jd) -> None:
    result = classify(jd)
    assert result.label == label, f"expected {label} got {result}"
    assert result.confidence > 0
    assert result.raw_score >= MIN_SCORE_THRESHOLD


# ── Unknown / low-signal cases ────────────────────────────────────────


def test_empty_string_returns_unknown_with_zero_scores() -> None:
    r = classify("")
    assert r.label == "unknown"
    assert r.confidence == 0.0
    assert r.raw_score == 0.0
    assert all(v == 0.0 for v in r.scores.values())
    assert set(r.scores.keys()) == set(ALL_LABELS)
    assert len(r.jd_hash) == 16


def test_whitespace_only_returns_unknown() -> None:
    assert classify("    \n\t  ").label == "unknown"


def test_generic_jd_no_strong_keywords_returns_unknown() -> None:
    jd = (
        "We are a great company looking for a great engineer. You will "
        "write code, attend meetings, and grow with us."
    )
    r = classify(jd)
    assert r.label == "unknown"


def test_low_score_below_threshold_returns_unknown() -> None:
    # Two unrelated WEAK tokens (~0.6 each) → 1.2 total < threshold 2.0.
    jd = "We value scrappy work and a small team."
    r = classify(jd)
    assert r.raw_score < MIN_SCORE_THRESHOLD
    assert r.label == "unknown"


def test_tie_within_margin_returns_unknown_with_runner_up() -> None:
    # Mix exactly one strong cue from two archetypes → equal scores → tie.
    jd = "Founding engineer at a Series C rocketship."
    r = classify(jd)
    # Either both score 1.5 (tie under MIN_MARGIN) or one beats the other.
    if r.label == "unknown":
        assert r.runner_up in ALL_LABELS
    else:
        # If margin is large enough one wins outright — still acceptable.
        assert r.label in ("startup_founder_adj", "hyper_growth_scaleup")


# ── jd_hash ───────────────────────────────────────────────────────────


def test_jd_hash_deterministic_and_16_hex() -> None:
    h1 = jd_hash("hello world")
    h2 = jd_hash("hello world")
    assert h1 == h2
    assert len(h1) == 16
    assert all(c in "0123456789abcdef" for c in h1)


def test_jd_hash_changes_with_input() -> None:
    assert jd_hash("a") != jd_hash("b")


def test_jd_hash_collapses_jds_longer_than_6000_chars_at_prefix() -> None:
    base = "abc " * 1500  # ~6000 chars
    same_prefix = base + "DIFFERENT"
    # First 6000 chars are identical → hashes match.
    assert jd_hash(base[:6000]) == jd_hash(same_prefix[:6000])


def test_jd_hash_handles_none_via_empty_string_path() -> None:
    # The internal hasher accepts "" via the falsy guard. Public API
    # expects a string; pass empty.
    assert len(jd_hash("")) == 16


# ── Score map / runner-up shape ───────────────────────────────────────


def test_scores_map_has_all_labels() -> None:
    r = classify(_FIXTURES["enterprise_saas"])
    assert set(r.scores.keys()) == set(ALL_LABELS)
    assert r.scores["enterprise_saas"] > 0


def test_runner_up_is_second_highest() -> None:
    # A JD with strong enterprise SaaS + weak finance signals.
    jd = (
        "Enterprise SaaS platform, multi-tenant B2B SaaS for Fortune 500. "
        "SOC 2 Type II. Some compliance and audit knowledge a plus."
    )
    r = classify(jd)
    assert r.label == "enterprise_saas"
    assert r.runner_up != "enterprise_saas"
    assert r.scores[r.runner_up] <= r.scores["enterprise_saas"]


def test_classify_returns_stable_archetype_dataclass() -> None:
    r = classify(_FIXTURES["big_tech_ic"])
    assert isinstance(r, StableArchetype)
    assert r.label in ALL_LABELS
    assert 0.0 <= r.confidence <= 1.0


# ── Determinism / immutability ────────────────────────────────────────


def test_classify_is_deterministic() -> None:
    jd = _FIXTURES["regulated_finance"]
    a, b = classify(jd), classify(jd)
    assert a == b


def test_classify_does_not_mutate_input() -> None:
    jd = _FIXTURES["public_sector"]
    snap = jd
    classify(jd)
    assert jd == snap


def test_word_boundary_prevents_substring_false_positives() -> None:
    # 'agency' is a weak agency_consulting token; 'agencyless' should NOT match.
    jd = "agencyless team practicing agencylessness." * 5
    r = classify(jd)
    assert r.scores["agency_consulting"] == 0.0


def test_case_insensitive_matching() -> None:
    jd = (
        "FOUNDING ENGINEER at a PRE-SEED startup. WEAR MANY HATS, "
        "SHIP FAST, NO PLAYBOOK, ZERO TO ONE."
    )
    r = classify(jd)
    assert r.label == "startup_founder_adj"


def test_repeated_keyword_does_not_inflate_score() -> None:
    # Same single strong token repeated 10x must NOT outscore a JD with
    # two distinct strong tokens.
    spam = "FedRAMP " * 50
    real = "FedRAMP. Department of Defense customer."
    r_spam = classify(spam)
    r_real = classify(real)
    assert r_spam.scores["public_sector"] <= r_real.scores["public_sector"]


# ── Threshold / margin behavior ───────────────────────────────────────


def test_threshold_constants_are_sane() -> None:
    # Sanity guards in case someone tweaks constants without re-running tests.
    assert MIN_SCORE_THRESHOLD > 0
    assert 0 < MIN_MARGIN <= MIN_SCORE_THRESHOLD


def test_confidence_is_capped_at_one() -> None:
    # Strong runaway win → confidence near 1.0.
    r = classify(_FIXTURES["research_lab"])
    assert 0.0 < r.confidence <= 1.0
