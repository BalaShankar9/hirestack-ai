"""S5-F3 — Pin CompanyIntelChain._minimal_fallback + ValidatorChain primitives.

Two security/safety surfaces here:

1. CompanyIntelChain._minimal_fallback is the absolute last-resort
   intel response when EVERY upstream company-intel source has failed
   (web search, scraping, LLM). The frontend assumes a fixed shape;
   any drift breaks the application strategy panel.

2. ValidatorChain has three pure helpers that are called all over the
   codebase: required-field checking, XSS sanitisation, and
   anti-fabrication detection. Drift in sanitize_content silently
   re-opens an XSS vector.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from ai_engine.chains.company_intel import CompanyIntelChain
from ai_engine.chains.validator import ValidatorChain


# ── CompanyIntelChain._minimal_fallback ───────────────────────────────


def test_minimal_fallback_returns_required_top_level_keys() -> None:
    out = CompanyIntelChain._minimal_fallback("Acme", "We need a Python engineer.")
    for key in (
        "company_overview",
        "culture_and_values",
        "tech_and_engineering",
        "products_and_services",
        "hiring_intelligence",
        "application_strategy",
        "confidence",
        "application_strategy_digest",
    ):
        assert key in out, f"_minimal_fallback missing top-level key '{key}'"


def test_minimal_fallback_marks_confidence_low() -> None:
    """Last-resort output must NEVER claim high confidence —
    downstream consumers gate behaviour on this signal."""
    out = CompanyIntelChain._minimal_fallback("Acme", "")
    assert out["confidence"] == "low"


def test_minimal_fallback_extracts_known_tech_keywords() -> None:
    jd = "Looking for a senior Python and React engineer with AWS / Kubernetes experience."
    out = CompanyIntelChain._minimal_fallback("Acme", jd)
    stack = out["tech_and_engineering"]["tech_stack"]
    assert "python" in stack
    assert "react" in stack
    assert "aws" in stack
    assert "kubernetes" in stack


def test_minimal_fallback_does_not_extract_unknown_words() -> None:
    out = CompanyIntelChain._minimal_fallback("Acme", "Cobol Fortran Pascal")
    assert out["tech_and_engineering"]["tech_stack"] == []


def test_minimal_fallback_keywords_capped_at_ten() -> None:
    """application_strategy.keywords_to_use must not blow up the
    cover-letter prompt token budget."""
    jd = " ".join([
        "react", "angular", "vue", "next.js", "python", "javascript",
        "typescript", "java", "go", "rust", "c#", "ruby", "aws", "gcp",
    ])
    out = CompanyIntelChain._minimal_fallback("Acme", jd)
    assert len(out["application_strategy"]["keywords_to_use"]) <= 10


def test_minimal_fallback_company_name_preserved() -> None:
    out = CompanyIntelChain._minimal_fallback("Stripe", "")
    assert out["company_overview"]["name"] == "Stripe"
    assert "Stripe" in out["application_strategy_digest"]


def test_minimal_fallback_jd_text_lowercased_before_matching() -> None:
    """Tech keyword detection must be case-insensitive — JDs use
    'Python' / 'PYTHON' interchangeably."""
    out = CompanyIntelChain._minimal_fallback("Acme", "PYTHON and DOCKER required")
    assert "python" in out["tech_and_engineering"]["tech_stack"]
    assert "docker" in out["tech_and_engineering"]["tech_stack"]


# ── ValidatorChain.validate_json_structure ────────────────────────────


def test_validate_json_structure_pass_when_all_present() -> None:
    chain = ValidatorChain(MagicMock())
    ok, missing = chain.validate_json_structure(
        {"a": 1, "b": 2}, ["a", "b"]
    )
    assert ok is True
    assert missing == []


def test_validate_json_structure_reports_missing_fields() -> None:
    chain = ValidatorChain(MagicMock())
    ok, missing = chain.validate_json_structure({"a": 1}, ["a", "b", "c"])
    assert ok is False
    assert set(missing) == {"b", "c"}


def test_validate_json_structure_treats_none_as_missing() -> None:
    """A None value is not a present field — downstream code that
    assumes presence == truthiness would crash."""
    chain = ValidatorChain(MagicMock())
    ok, missing = chain.validate_json_structure({"a": None}, ["a"])
    assert ok is False
    assert missing == ["a"]


# ── ValidatorChain.sanitize_content (XSS surface) ─────────────────────


def test_sanitize_content_strips_script_tags() -> None:
    """SECURITY: <script> blocks must NEVER survive sanitisation —
    rendered HTML reaches Atlas chat surface."""
    chain = ValidatorChain(MagicMock())
    out = chain.sanitize_content('Hello <script>alert(1)</script> world')
    assert "<script" not in out.lower()
    assert "alert(1)" not in out


def test_sanitize_content_strips_multiline_script_blocks() -> None:
    chain = ValidatorChain(MagicMock())
    out = chain.sanitize_content('<script>\nalert(1);\nlet x = 1;\n</script>')
    assert "alert" not in out


def test_sanitize_content_strips_event_handlers() -> None:
    """SECURITY: onclick / onerror / onload etc must be stripped."""
    chain = ValidatorChain(MagicMock())
    out = chain.sanitize_content('<img src=x onerror=alert(1)>')
    assert "onerror=" not in out.lower()


def test_sanitize_content_strips_javascript_protocol() -> None:
    """SECURITY: javascript: URI scheme is XSS bait."""
    chain = ValidatorChain(MagicMock())
    out = chain.sanitize_content('Click [here](javascript:alert(1))')
    assert "javascript:" not in out.lower()


def test_sanitize_content_preserves_safe_markdown() -> None:
    chain = ValidatorChain(MagicMock())
    safe = "# Heading\n\n**Bold** and *italic* and [link](https://example.com)"
    out = chain.sanitize_content(safe)
    assert "# Heading" in out
    assert "**Bold**" in out
    assert "https://example.com" in out


# ── ValidatorChain.check_for_fabrication ──────────────────────────────


def test_check_for_fabrication_returns_empty_when_subset() -> None:
    chain = ValidatorChain(MagicMock())
    generated = {"experience": [{"company": "Acme"}]}
    source = {"experience": [{"company": "Acme"}, {"company": "Beta"}]}
    assert chain.check_for_fabrication(generated, source) == []


def test_check_for_fabrication_flags_invented_companies() -> None:
    chain = ValidatorChain(MagicMock())
    generated = {"experience": [{"company": "GoogleX"}, {"company": "Acme"}]}
    source = {"experience": [{"company": "Acme"}]}
    warnings = chain.check_for_fabrication(generated, source)
    assert len(warnings) == 1
    assert "googlex" in warnings[0].lower()


def test_check_for_fabrication_is_case_insensitive() -> None:
    """An LLM rewriting 'acme' → 'Acme' must not be flagged as
    fabrication."""
    chain = ValidatorChain(MagicMock())
    generated = {"experience": [{"company": "ACME"}]}
    source = {"experience": [{"company": "acme"}]}
    assert chain.check_for_fabrication(generated, source) == []


def test_check_for_fabrication_safe_with_missing_experience() -> None:
    """If neither side has experience, must not crash."""
    chain = ValidatorChain(MagicMock())
    assert chain.check_for_fabrication({}, {}) == []


def test_check_for_fabrication_skips_blank_company_entries() -> None:
    """Some LLM outputs include {"company": "", "title": "..."}.
    These must not be flagged as fabricated 'empty company'."""
    chain = ValidatorChain(MagicMock())
    generated = {"experience": [{"company": ""}, {"title": "Eng"}]}
    source = {"experience": [{"company": "Acme"}]}
    assert chain.check_for_fabrication(generated, source) == []
