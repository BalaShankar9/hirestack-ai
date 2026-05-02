"""Tests for ai_engine.agents.voice_guard — Wave 0 / V1 (tone reversal)."""
from __future__ import annotations

import pytest

from ai_engine.agents.voice_guard import (
    DEFAULT_VOICE,
    BannedPhraseHit,
    banned_phrases_for,
    scan_for_banned_phrases,
    tone_penalty,
)


# ── Pure scan ─────────────────────────────────────────────────────────────

def test_clean_text_returns_no_hits():
    text = "Led the migration of three production services to Postgres 16."
    assert scan_for_banned_phrases(text) == []


def test_default_voice_catches_passionate_about():
    text = "I am passionate about distributed systems."
    hits = scan_for_banned_phrases(text)
    phrases = {h.phrase for h in hits}
    assert "passionate about" in phrases


def test_default_voice_catches_multiple_phrases():
    text = (
        "I would love the opportunity to join your team. "
        "I'm a results-oriented team player who can hit the ground running."
    )
    phrases = {h.phrase for h in scan_for_banned_phrases(text)}
    assert "would love the opportunity" in phrases
    assert "results-oriented" in phrases
    assert "team player" in phrases
    assert "hit the ground running" in phrases


def test_count_reflects_repetition():
    text = "Synergy here, synergy there, SYNERGY everywhere."
    hits = scan_for_banned_phrases(text)
    syn = next(h for h in hits if h.phrase == "synergy")
    assert syn.count == 3
    assert syn.as_issue()["severity"] == "critical"  # ≥3 escalates


def test_case_insensitive():
    text = "PASSIONATE ABOUT Kubernetes."
    assert scan_for_banned_phrases(text)


# ── Substring safety ──────────────────────────────────────────────────────

def test_no_false_positive_on_substring_inside_word():
    # "synergies" should NOT match "synergy" via substring; we use word boundary
    # AND we ban "synergies" separately, so this still hits — but for a phrase
    # that is genuinely a substring of an unrelated word, it must not match.
    # "leverage my" must not match "leveraged my fastapi skills".
    text = "Leveraged my FastAPI skills to ship the API."
    hits = scan_for_banned_phrases(text)
    phrases = {h.phrase for h in hits}
    assert "leverage my" not in phrases
    assert "leveraging my" not in phrases


# ── HTML handling ─────────────────────────────────────────────────────────

def test_strips_html_before_scanning():
    html = "<p>I am <strong>passionate about</strong> ML.</p>"
    hits = scan_for_banned_phrases(html)
    assert any(h.phrase == "passionate about" for h in hits)


# ── Dict / list coercion ──────────────────────────────────────────────────

def test_handles_dict_draft():
    draft = {"html": "<p>I'm a go-getter.</p>", "summary": "Strong fit for the role."}
    phrases = {h.phrase for h in scan_for_banned_phrases(draft)}
    assert "go-getter" in phrases
    assert "strong fit" in phrases


def test_handles_list_draft():
    draft = ["I would love the opportunity", "to bring synergies"]
    phrases = {h.phrase for h in scan_for_banned_phrases(draft)}
    assert "would love the opportunity" in phrases
    assert "synergies" in phrases


def test_handles_none_and_empty():
    assert scan_for_banned_phrases(None) == []
    assert scan_for_banned_phrases("") == []
    assert scan_for_banned_phrases({}) == []


# ── Voice presets ─────────────────────────────────────────────────────────

def test_warm_eager_allows_excited_to_apply():
    # warm_eager keeps "excited to apply" as acceptable
    text = "I'm excited to apply for the senior role."
    hits = scan_for_banned_phrases(text, voice="warm_eager")
    phrases = {h.phrase for h in hits}
    assert "excited to apply" not in phrases


def test_default_blocks_excited_to_apply():
    text = "I'm excited to apply for the senior role."
    phrases = {h.phrase for h in scan_for_banned_phrases(text)}
    assert "excited to apply" in phrases


def test_unknown_voice_falls_back_to_default():
    a = scan_for_banned_phrases("passionate about ML", voice="nonsense")
    b = scan_for_banned_phrases("passionate about ML", voice=DEFAULT_VOICE)
    assert {h.phrase for h in a} == {h.phrase for h in b}


def test_formal_traditional_drops_would_love():
    text = "I would love to discuss this role with you."
    phrases = {h.phrase for h in scan_for_banned_phrases(text, voice="formal_traditional")}
    assert "would love" in phrases


def test_banned_phrases_for_returns_tuple():
    out = banned_phrases_for("confident_selective")
    assert isinstance(out, tuple)
    assert "passionate about" in out


def test_banned_phrases_for_none_uses_default():
    assert banned_phrases_for(None) == banned_phrases_for(DEFAULT_VOICE)


# ── Extra banned (user-supplied) ──────────────────────────────────────────

def test_extra_banned_phrases_are_added():
    text = "I am a rock star ninja unicorn engineer."
    hits = scan_for_banned_phrases(
        text,
        extra_banned=["rock star", "ninja", "unicorn"],
    )
    phrases = {h.phrase for h in hits}
    assert {"rock star", "ninja", "unicorn"}.issubset(phrases)


def test_extra_banned_dedups_with_default_set():
    # If user redundantly adds a phrase already banned by default,
    # we still report only one hit per phrase.
    hits = scan_for_banned_phrases(
        "passionate about engineering",
        extra_banned=["passionate about", "PASSIONATE ABOUT"],
    )
    matching = [h for h in hits if h.phrase.lower() == "passionate about"]
    assert len(matching) == 1


# ── Penalty + as_issue ────────────────────────────────────────────────────

def test_penalty_is_zero_for_no_hits():
    assert tone_penalty([]) == 0


def test_penalty_increases_with_hits():
    hits = [
        BannedPhraseHit(phrase="passionate about", count=1),
        BannedPhraseHit(phrase="synergy", count=2),
    ]
    # 5 + (5+2) = 12
    assert tone_penalty(hits) == 12


def test_penalty_capped_at_40():
    hits = [BannedPhraseHit(phrase=f"phrase{i}", count=5) for i in range(20)]
    assert tone_penalty(hits) == 40


def test_as_issue_renders_expected_shape():
    hit = BannedPhraseHit(phrase="passionate about", count=2)
    issue = hit.as_issue()
    assert issue["dimension"] == "tone_match"
    assert issue["severity"] == "high"
    assert "passionate about" in issue["issue"]
    assert issue["section"] == "voice"
    assert issue["expected_gain"] == 6


def test_as_issue_escalates_to_critical_at_three_hits():
    hit = BannedPhraseHit(phrase="synergy", count=3)
    assert hit.as_issue()["severity"] == "critical"


def test_punctuation_does_not_block_match():
    text = 'I am, indeed, "passionate about" Kubernetes.'
    assert any(h.phrase == "passionate about" for h in scan_for_banned_phrases(text))


@pytest.mark.parametrize(
    "phrase",
    [
        "passionate about",
        "would love the opportunity",
        "strong fit",
        "team player",
        "hit the ground running",
        "leverage my",
    ],
)
def test_default_voice_blocks_canonical_phrases(phrase: str):
    text = f"This sentence contains the {phrase} marker."
    phrases = {h.phrase for h in scan_for_banned_phrases(text)}
    assert phrase in phrases
