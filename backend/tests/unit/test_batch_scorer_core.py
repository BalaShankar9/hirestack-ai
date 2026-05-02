"""Tests for batch_scorer_core — pure-fn prompt + parser."""

from __future__ import annotations

import pytest

from app.services.batch_evaluator import BatchEntry, ScoringResult
from app.services.batch_scorer_core import (
    MAX_JD_CHARS,
    MAX_PROFILE_CHARS,
    SCORE_MAX,
    SCORE_MIN,
    SCORE_SYSTEM_PROMPT,
    build_profile_text,
    build_score_prompt,
    parse_score_response,
)


def _entry(url: str = "https://example.com/job/1") -> BatchEntry:
    return BatchEntry(raw_url=url, canonical_url=url, ats_key=None)


# ── build_profile_text ───────────────────────────────────────────────


class TestBuildProfileText:
    def test_none_profile(self):
        assert build_profile_text(None) == "(no profile on file)"

    def test_empty_dict_profile(self):
        assert build_profile_text({}) == "(profile is empty)"

    def test_full_profile(self):
        out = build_profile_text({
            "title": "Senior Engineer",
            "skills": [{"name": "Python"}, {"name": "Go"}],
            "summary": "10 years building distributed systems.",
        })
        assert "Title: Senior Engineer" in out
        assert "Skills: Python, Go" in out
        assert "Summary: 10 years building distributed systems." in out

    def test_skills_as_strings(self):
        out = build_profile_text({"title": "X", "skills": ["Rust", "K8s"]})
        assert "Skills: Rust, K8s" in out

    def test_skills_mixed_types_filters_blank(self):
        out = build_profile_text({
            "title": "X",
            "skills": [{"name": "Rust"}, {"name": ""}, "", None, "Go"],
        })
        assert "Skills: Rust, Go" in out

    def test_strips_whitespace_only_fields(self):
        out = build_profile_text({"title": "  ", "summary": "  "})
        # Both are whitespace-only → both omitted → empty fallback.
        assert out == "(profile is empty)"

    def test_long_profile_truncated_with_ellipsis(self):
        big_summary = "x" * (MAX_PROFILE_CHARS * 2)
        out = build_profile_text({"title": "T", "summary": big_summary})
        assert len(out) <= MAX_PROFILE_CHARS + 1
        assert out.endswith("…")

    def test_deterministic_ordering_for_caching(self):
        a = build_profile_text({
            "title": "T", "skills": ["A", "B"], "summary": "S",
        })
        b = build_profile_text({
            "summary": "S", "title": "T", "skills": ["A", "B"],
        })
        assert a == b


# ── build_score_prompt ───────────────────────────────────────────────


class TestBuildScorePrompt:
    def test_returns_splat_friendly_dict(self):
        block = build_score_prompt(
            profile_text="P", jd_text="J", canonical_url="https://x/y",
        )
        assert set(block.keys()) == {"system", "prompt", "max_tokens"}
        assert block["system"] == SCORE_SYSTEM_PROMPT
        assert isinstance(block["prompt"], str)
        assert isinstance(block["max_tokens"], int)
        assert block["max_tokens"] > 0

    def test_includes_profile_jd_url(self):
        block = build_score_prompt(
            profile_text="MY-PROFILE",
            jd_text="MY-JD-TEXT",
            canonical_url="https://example.com/job/1",
        )
        assert "MY-PROFILE" in block["prompt"]
        assert "MY-JD-TEXT" in block["prompt"]
        assert "https://example.com/job/1" in block["prompt"]

    def test_jd_truncated_with_ellipsis(self):
        big_jd = "z" * (MAX_JD_CHARS * 3)
        block = build_score_prompt(
            profile_text="P", jd_text=big_jd, canonical_url="https://x",
        )
        # The "z" run inside the prompt is capped + ellipsis.
        zs = block["prompt"].count("z")
        assert zs <= MAX_JD_CHARS
        assert "…" in block["prompt"]

    def test_short_jd_not_truncated(self):
        block = build_score_prompt(
            profile_text="P", jd_text="short", canonical_url="https://x",
        )
        assert "short" in block["prompt"]
        # No ellipsis appended for short JDs.
        assert not block["prompt"].rstrip().endswith("…")

    def test_schema_in_prompt(self):
        """Model should see the exact schema we expect back."""
        block = build_score_prompt(
            profile_text="P", jd_text="J", canonical_url="https://x",
        )
        for required in ("match_score", "match_reasons", "missing_skills", "title", "company"):
            assert required in block["prompt"]


# ── parse_score_response ─────────────────────────────────────────────


class TestParseScoreResponse:
    def test_valid_response(self):
        out = parse_score_response({
            "match_score": 84,
            "match_reasons": ["x"],
            "missing_skills": [],
            "title": "Senior Eng",
            "company": "Acme",
        }, _entry())
        assert out.fit_score == pytest.approx(4.2)
        assert out.error is None
        assert out.title == "Senior Eng"
        assert out.company == "Acme"

    def test_canonical_url_pinned(self):
        """Even if the model echoes a different URL, we use the entry's URL."""
        out = parse_score_response({"match_score": 80}, _entry("https://right/x"))
        assert out.canonical_url == "https://right/x"

    def test_score_clamped_high(self):
        out = parse_score_response({"match_score": 105}, _entry())
        assert out.fit_score == SCORE_MAX
        assert out.error is None  # clamping, not error

    def test_score_clamped_low(self):
        out = parse_score_response({"match_score": -10}, _entry())
        assert out.fit_score == SCORE_MIN
        assert out.error is None

    def test_score_string_coerced(self):
        out = parse_score_response({"match_score": "60"}, _entry())
        assert out.fit_score == pytest.approx(3.0)

    def test_score_float_coerced(self):
        out = parse_score_response({"match_score": 73.5}, _entry())
        assert out.fit_score == pytest.approx(73.5 / 20)

    def test_score_missing_is_parse_error(self):
        out = parse_score_response({"match_reasons": []}, _entry())
        assert out.fit_score is None
        assert out.error == "parse_error"

    def test_score_none_is_parse_error(self):
        out = parse_score_response({"match_score": None}, _entry())
        assert out.error == "parse_error"

    def test_score_non_numeric_is_parse_error(self):
        out = parse_score_response({"match_score": "high"}, _entry())
        assert out.error == "parse_error"

    def test_non_dict_response_is_parse_error(self):
        for bad in [None, "string", 42, [], True]:
            out = parse_score_response(bad, _entry())
            assert out.error == "parse_error", f"failed for {bad!r}"
            assert out.fit_score is None
            assert out.canonical_url == _entry().canonical_url

    def test_optional_title_company_missing_ok(self):
        out = parse_score_response({"match_score": 50}, _entry())
        assert out.fit_score == pytest.approx(2.5)
        assert out.error is None
        assert out.title is None
        assert out.company is None

    def test_blank_title_company_become_none(self):
        out = parse_score_response({
            "match_score": 50, "title": "  ", "company": "",
        }, _entry())
        assert out.title is None
        assert out.company is None

    def test_returns_scoring_result_type(self):
        out = parse_score_response({"match_score": 50}, _entry())
        assert isinstance(out, ScoringResult)
