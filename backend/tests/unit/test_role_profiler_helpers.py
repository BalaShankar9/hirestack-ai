"""S5-F1 — Pin RoleProfilerChain pure-helper invariants.

The chain wraps an LLM call but the helpers around it are pure
Python and govern resume parsing quality. Any one of them silently
drifting would degrade EVERY parsed resume in production.

These tests instantiate the chain with a stub `AIClient` so we can
exercise the helpers without making AI calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_engine.chains.role_profiler import RoleProfilerChain


@pytest.fixture
def chain() -> RoleProfilerChain:
    return RoleProfilerChain(MagicMock())


# ── _is_noise_line ─────────────────────────────────────────────────────


def test_is_noise_line_strips_page_markers(chain: RoleProfilerChain) -> None:
    assert chain._is_noise_line("Page 1 of 3") is True
    assert chain._is_noise_line("page 2") is True


def test_is_noise_line_strips_curriculum_vitae_header(chain: RoleProfilerChain) -> None:
    assert chain._is_noise_line("Curriculum Vitae") is True
    assert chain._is_noise_line("Resume of John Doe") is True


def test_is_noise_line_strips_confidential_and_references(chain: RoleProfilerChain) -> None:
    assert chain._is_noise_line("Confidential") is True
    assert chain._is_noise_line("References available upon request") is True
    assert chain._is_noise_line("References upon request") is True


def test_is_noise_line_strips_pure_page_numbers(chain: RoleProfilerChain) -> None:
    assert chain._is_noise_line("1") is True
    assert chain._is_noise_line("12") is True
    # 3-digit numbers are NOT page numbers (could be addresses, version no.)
    assert chain._is_noise_line("123") is False


def test_is_noise_line_strips_decorative_separators(chain: RoleProfilerChain) -> None:
    assert chain._is_noise_line("------") is True
    assert chain._is_noise_line("======") is True
    assert chain._is_noise_line("______") is True
    # 4 chars are NOT considered separators (could be section markers)
    assert chain._is_noise_line("---") is False


def test_is_noise_line_keeps_real_content(chain: RoleProfilerChain) -> None:
    assert chain._is_noise_line("Senior Software Engineer") is False
    assert chain._is_noise_line("john@example.com") is False
    assert chain._is_noise_line("") is False


# ── _clean_resume_text ────────────────────────────────────────────────


def test_clean_resume_text_handles_empty(chain: RoleProfilerChain) -> None:
    assert chain._clean_resume_text("") == ""
    assert chain._clean_resume_text(None) is None


def test_clean_resume_text_normalizes_bullets(chain: RoleProfilerChain) -> None:
    out = chain._clean_resume_text("• Built API\n● Shipped feature\n▪ Led team")
    # All bullets become "-"
    assert "•" not in out and "●" not in out and "▪" not in out
    assert out.count("-") >= 3


def test_clean_resume_text_collapses_excess_whitespace(chain: RoleProfilerChain) -> None:
    out = chain._clean_resume_text("a       b")
    # 3+ spaces collapse to 2
    assert "       " not in out


def test_clean_resume_text_repairs_mangled_linkedin(chain: RoleProfilerChain) -> None:
    out = chain._clean_resume_text("Profile: linkedin . com/in/jane")
    assert "linkedin.com" in out


def test_clean_resume_text_repairs_mangled_github(chain: RoleProfilerChain) -> None:
    out = chain._clean_resume_text("Code: github . com/jane")
    assert "github.com" in out


def test_clean_resume_text_drops_noise_lines(chain: RoleProfilerChain) -> None:
    out = chain._clean_resume_text("Page 1\nReal content\n------")
    assert "Page 1" not in out
    assert "Real content" in out


# ── _normalize_date ───────────────────────────────────────────────────


def test_normalize_date_returns_none_for_falsy(chain: RoleProfilerChain) -> None:
    assert chain._normalize_date(None) is None
    assert chain._normalize_date("") is None


def test_normalize_date_rejects_non_string(chain: RoleProfilerChain) -> None:
    """A future bug where a date column comes back as int / datetime
    object should not crash the parser."""
    assert chain._normalize_date(2024) is None  # type: ignore[arg-type]


def test_normalize_date_canonicalizes_present_synonyms(chain: RoleProfilerChain) -> None:
    for synonym in ("Present", "present", "current", "Now", "ongoing"):
        assert chain._normalize_date(synonym) == "Present"


def test_normalize_date_passes_through_normal_dates(chain: RoleProfilerChain) -> None:
    assert chain._normalize_date("Jan 2020") == "Jan 2020"
    assert chain._normalize_date("  Mar 2023  ") == "Mar 2023"


# ── _clean_skill ──────────────────────────────────────────────────────


def test_clean_skill_returns_unchanged_for_empty_name(chain: RoleProfilerChain) -> None:
    raw = {"name": "", "level": "expert"}
    out = chain._clean_skill(raw)
    assert out == raw


def test_clean_skill_defaults_invalid_level_to_intermediate(chain: RoleProfilerChain) -> None:
    out = chain._clean_skill({"name": "Python", "level": "godlike"})
    assert out["level"] == "intermediate"


def test_clean_skill_defaults_invalid_category_to_technical(chain: RoleProfilerChain) -> None:
    out = chain._clean_skill({"name": "Python", "category": "wizardry"})
    assert out["category"] == "technical"


def test_clean_skill_drops_negative_or_outlier_years(chain: RoleProfilerChain) -> None:
    """Years <= 0 or > 50 are nonsensical; reject so downstream UI
    doesn't render '-2 years experience'."""
    assert chain._clean_skill({"name": "X", "years": -1})["years"] is None
    assert chain._clean_skill({"name": "X", "years": 0})["years"] is None
    assert chain._clean_skill({"name": "X", "years": 99})["years"] is None
    assert chain._clean_skill({"name": "X", "years": 5.5})["years"] == 5.5


def test_clean_skill_handles_unparseable_years_string(chain: RoleProfilerChain) -> None:
    assert chain._clean_skill({"name": "X", "years": "lots"})["years"] is None


# ── _deduplicate_skills ───────────────────────────────────────────────


def test_deduplicate_skills_keeps_higher_level(chain: RoleProfilerChain) -> None:
    """If 'Python' appears twice with different levels, keep the
    higher-ranked entry."""
    skills = [
        {"name": "Python", "level": "beginner", "years": None, "category": "technical"},
        {"name": "Python", "level": "expert", "years": None, "category": "technical"},
    ]
    out = chain._deduplicate_skills(skills)
    assert len(out) == 1
    assert out[0]["level"] == "expert"


def test_deduplicate_skills_is_case_insensitive(chain: RoleProfilerChain) -> None:
    skills = [
        {"name": "Python", "level": "intermediate", "years": None, "category": "technical"},
        {"name": "python", "level": "advanced", "years": None, "category": "technical"},
    ]
    out = chain._deduplicate_skills(skills)
    assert len(out) == 1


def test_deduplicate_skills_keeps_longer_years(chain: RoleProfilerChain) -> None:
    """If two duplicate entries have years, keep the larger one (more
    experience claimed wins)."""
    skills = [
        {"name": "Go", "level": "advanced", "years": 2, "category": "technical"},
        {"name": "Go", "level": "advanced", "years": 5, "category": "technical"},
    ]
    out = chain._deduplicate_skills(skills)
    assert out[0]["years"] == 5


def test_deduplicate_skills_preserves_all_unique(chain: RoleProfilerChain) -> None:
    skills = [
        {"name": "Python", "level": "expert", "years": None, "category": "technical"},
        {"name": "Rust", "level": "intermediate", "years": None, "category": "technical"},
        {"name": "Go", "level": "advanced", "years": None, "category": "technical"},
    ]
    out = chain._deduplicate_skills(skills)
    assert len(out) == 3


# ── _compute_parse_confidence ─────────────────────────────────────────


def test_compute_parse_confidence_zero_when_empty(chain: RoleProfilerChain) -> None:
    assert chain._compute_parse_confidence({}) == 0.0


def test_compute_parse_confidence_capped_at_one(chain: RoleProfilerChain) -> None:
    """Highest possible signal must round to ≤1.0 — a confidence > 1
    would crash UI gauges."""
    full = {
        "name": "Jane Doe",
        "contact_info": {"email": "j@x.test", "phone": "+1555"},
        "skills": [{"name": f"S{i}"} for i in range(50)],
        "experience": [{"company": f"C{i}"} for i in range(20)],
        "education": [{"institution": "MIT"}],
    }
    score = chain._compute_parse_confidence(full)
    assert 0.0 <= score <= 1.0


def test_compute_parse_confidence_rewards_each_signal(chain: RoleProfilerChain) -> None:
    name_only = chain._compute_parse_confidence({"name": "Jane"})
    name_plus_email = chain._compute_parse_confidence(
        {"name": "Jane", "contact_info": {"email": "j@x.test"}}
    )
    assert name_plus_email > name_only


def test_compute_parse_confidence_handles_non_dict_contact(chain: RoleProfilerChain) -> None:
    """If contact_info comes back as a string from a model bug, the
    helper must not crash."""
    score = chain._compute_parse_confidence({"name": "Jane", "contact_info": "junk"})
    assert isinstance(score, float)


# ── _build_parse_warnings ─────────────────────────────────────────────


def test_build_parse_warnings_flags_missing_name(chain: RoleProfilerChain) -> None:
    warnings = chain._build_parse_warnings({})
    assert "Missing candidate name" in warnings


def test_build_parse_warnings_flags_missing_email(chain: RoleProfilerChain) -> None:
    warnings = chain._build_parse_warnings({"name": "Jane", "contact_info": {}})
    assert "Missing contact email" in warnings


def test_build_parse_warnings_flags_low_skill_density(chain: RoleProfilerChain) -> None:
    warnings = chain._build_parse_warnings({"name": "Jane", "skills": [{"name": "X"}]})
    assert "Low skill extraction density" in warnings


def test_build_parse_warnings_silent_on_strong_result(chain: RoleProfilerChain) -> None:
    full = {
        "name": "Jane",
        "contact_info": {"email": "j@x.test"},
        "skills": [{"name": f"S{i}"} for i in range(5)],
        "experience": [{"company": "X"}],
        "education": [{"institution": "MIT"}],
    }
    assert chain._build_parse_warnings(full) == []


# ── _sort_by_date ─────────────────────────────────────────────────────


def test_sort_by_date_puts_current_first(chain: RoleProfilerChain) -> None:
    exps = [
        {"company": "Old", "end_date": "Dec 2018", "is_current": False},
        {"company": "Now", "end_date": None, "is_current": True},
        {"company": "Mid", "end_date": "Mar 2022", "is_current": False},
    ]
    out = chain._sort_by_date(exps)
    assert out[0]["company"] == "Now"


def test_sort_by_date_treats_present_as_current(chain: RoleProfilerChain) -> None:
    exps = [
        {"company": "Old", "end_date": "Dec 2018"},
        {"company": "Now", "end_date": "Present"},
    ]
    out = chain._sort_by_date(exps)
    assert out[0]["company"] == "Now"


def test_sort_by_date_orders_past_roles_by_year_desc(chain: RoleProfilerChain) -> None:
    exps = [
        {"company": "2018", "end_date": "Dec 2018"},
        {"company": "2022", "end_date": "Mar 2022"},
        {"company": "2020", "end_date": "Jun 2020"},
    ]
    out = chain._sort_by_date(exps)
    assert [e["company"] for e in out] == ["2022", "2020", "2018"]
