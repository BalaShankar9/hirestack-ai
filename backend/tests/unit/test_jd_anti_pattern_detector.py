"""Tests for E3.core jd_anti_pattern_detector — pure-fn JD scanner.

Coverage map (mirrors insights_blockers test layout):

  TestEmptyAndNoise         — empty/whitespace/non-string boundary
  TestAgeist                — every regex in _AGEIST + miss cases
  TestGendered              — every regex in _GENDERED + miss cases
  TestVagueCompensation     — vague comp + unpaid cluster
  TestUnrealisticExperience — N+ years gating around UNREALISTIC_YEARS_THRESHOLD
  TestCultureRedFlag        — family/work-hard-play-hard cluster
  TestUrgency               — ASAP cluster
  TestSnippet               — char window, ellipses, multi-line collapse
  TestSorting               — critical-first, stable within-bucket
  TestCounts                — by_category + severity_counts integrity
  TestRealJDs               — long fixture with multiple categories
"""
from __future__ import annotations

import pytest

from app.services.jd_anti_pattern_detector import (
    AntiPatternReport,
    Finding,
    SNIPPET_RADIUS,
    UNREALISTIC_YEARS_THRESHOLD,
    detect_anti_patterns,
)


# ── boundary ─────────────────────────────────────────────────────────


class TestEmptyAndNoise:
    def test_empty_string_returns_empty_report(self):
        rep = detect_anti_patterns("")
        assert rep.findings == ()
        assert rep.total_count == 0
        assert rep.severity_counts == {"critical": 0, "warn": 0, "info": 0}
        assert all(v == 0 for v in rep.by_category.values())

    def test_whitespace_only_is_empty(self):
        rep = detect_anti_patterns("   \n\t   ")
        assert rep.total_count == 0

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            detect_anti_patterns(None)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            detect_anti_patterns(123)  # type: ignore[arg-type]

    def test_clean_jd_no_findings(self):
        text = (
            "We are hiring a Senior Backend Engineer. Salary: $180k–$220k. "
            "Stack: Python, PostgreSQL, AWS. Remote-friendly. "
            "5+ years engineering experience required."
        )
        rep = detect_anti_patterns(text)
        assert rep.total_count == 0


# ── ageist ───────────────────────────────────────────────────────────


class TestAgeist:
    def test_digital_native_critical(self):
        rep = detect_anti_patterns("Looking for digital natives only.")
        assert rep.total_count == 1
        f = rep.findings[0]
        assert f.category == "ageist"
        assert f.severity == "critical"
        assert f.term == "digital native"

    def test_young_dynamic_critical(self):
        rep = detect_anti_patterns("Join our young, dynamic team!")
        cats = [f.category for f in rep.findings]
        assert "ageist" in cats

    def test_young_team_critical(self):
        rep = detect_anti_patterns("We have a young team of engineers.")
        ageist = [f for f in rep.findings if f.category == "ageist"]
        assert ageist and ageist[0].term == "young team"

    def test_recent_grads_only(self):
        rep = detect_anti_patterns("Recent graduates only need apply.")
        ageist = [f for f in rep.findings if f.category == "ageist"]
        assert ageist and ageist[0].severity == "critical"

    def test_max_years_cap(self):
        rep = detect_anti_patterns("Maximum 5 years of experience.")
        ageist = [f for f in rep.findings if f.category == "ageist"]
        assert ageist and ageist[0].severity == "critical"

    def test_no_more_than(self):
        rep = detect_anti_patterns("No more than 3 years preferred.")
        ageist = [f for f in rep.findings if f.category == "ageist"]
        assert ageist

    def test_fresh_grad_warn(self):
        rep = detect_anti_patterns("We want fresh out of college applicants.")
        ageist = [f for f in rep.findings if f.category == "ageist"]
        assert ageist and ageist[0].severity == "warn"

    def test_innocent_young_no_match(self):
        # "young" alone (not paired) shouldn't trip the regex
        rep = detect_anti_patterns("The company is young, founded 2024.")
        assert not [f for f in rep.findings if f.category == "ageist"]


# ── gendered ─────────────────────────────────────────────────────────


class TestGendered:
    def test_rockstar_critical(self):
        rep = detect_anti_patterns("We need a rockstar engineer.")
        g = [f for f in rep.findings if f.category == "gendered"]
        assert g and g[0].term == "rockstar"
        assert g[0].severity == "critical"

    def test_ninja_critical(self):
        rep = detect_anti_patterns("Hiring a JavaScript ninja.")
        g = [f for f in rep.findings if f.category == "gendered"]
        assert g and g[0].term == "ninja"

    def test_ninja_turtle_excluded(self):
        rep = detect_anti_patterns("Mascot: ninja turtle. Looking for engineers.")
        assert not [f for f in rep.findings if f.category == "gendered" and f.term == "ninja"]

    def test_guru_critical(self):
        rep = detect_anti_patterns("Coding guru wanted.")
        assert any(f.term == "guru" for f in rep.findings)

    def test_wizard_warn(self):
        rep = detect_anti_patterns("Tech wizard required.")
        g = [f for f in rep.findings if f.term == "wizard"]
        assert g and g[0].severity == "warn"

    def test_salesman_critical(self):
        rep = detect_anti_patterns("Hiring a salesman for the West region.")
        assert any(f.term == "salesman" for f in rep.findings)

    def test_manpower_critical(self):
        rep = detect_anti_patterns("Need extra manpower for Q4.")
        assert any(f.term == "manpower" for f in rep.findings)

    def test_he_she(self):
        rep = detect_anti_patterns("The candidate must bring his/her own laptop.")
        assert any(f.term == "his/her" for f in rep.findings)

    def test_hey_guys_warn(self):
        rep = detect_anti_patterns("Hey guys, looking for a senior dev.")
        assert any(f.term == "guys (informal)" for f in rep.findings)

    def test_clean_text_no_gendered(self):
        rep = detect_anti_patterns("Senior engineer wanted. Strong communicator.")
        assert not [f for f in rep.findings if f.category == "gendered"]


# ── vague comp ───────────────────────────────────────────────────────


class TestVagueCompensation:
    def test_competitive_salary(self):
        rep = detect_anti_patterns("Offering a competitive salary.")
        v = [f for f in rep.findings if f.category == "vague_compensation"]
        assert v and v[0].term == "competitive (no number)"
        assert v[0].severity == "warn"

    def test_commensurate(self):
        rep = detect_anti_patterns("Salary commensurate with experience.")
        assert any(f.term == "salary commensurate" for f in rep.findings)

    def test_doe(self):
        rep = detect_anti_patterns("Salary: DOE.")
        assert any(f.term == "DOE (depending on experience)" for f in rep.findings)

    def test_doe_legal_citation_excluded(self):
        # Filing reference shouldn't match
        rep = detect_anti_patterns("See Doe v. Smith, 2020 case.")
        assert not [f for f in rep.findings if f.term.startswith("DOE")]

    def test_equity_in_lieu_critical(self):
        rep = detect_anti_patterns("We offer equity in lieu of salary for early hires.")
        v = [f for f in rep.findings if f.term == "equity in lieu of cash"]
        assert v and v[0].severity == "critical"

    def test_unpaid_critical(self):
        rep = detect_anti_patterns("Unpaid internship — great learning opportunity.")
        v = [f for f in rep.findings if f.term == "unpaid"]
        assert v and v[0].severity == "critical"

    def test_for_exposure(self):
        rep = detect_anti_patterns("Build your portfolio for exposure.")
        assert any(f.term == "for exposure" for f in rep.findings)

    def test_concrete_salary_not_flagged(self):
        rep = detect_anti_patterns("Salary: $150k base + 0.1% equity.")
        assert not [f for f in rep.findings if f.category == "vague_compensation"]


# ── unrealistic experience ──────────────────────────────────────────


class TestUnrealisticExperience:
    def test_below_threshold_not_flagged(self):
        rep = detect_anti_patterns("5+ years Python experience.")
        assert not [f for f in rep.findings if f.category == "unrealistic_experience"]

    def test_just_below_threshold_not_flagged(self):
        below = UNREALISTIC_YEARS_THRESHOLD - 1
        rep = detect_anti_patterns(f"{below}+ years required.")
        assert not [f for f in rep.findings if f.category == "unrealistic_experience"]

    def test_at_threshold_flagged(self):
        rep = detect_anti_patterns(f"{UNREALISTIC_YEARS_THRESHOLD}+ years Kubernetes.")
        u = [f for f in rep.findings if f.category == "unrealistic_experience"]
        assert u and u[0].severity == "warn"

    def test_above_threshold_flagged(self):
        rep = detect_anti_patterns("20+ years React experience required.")
        u = [f for f in rep.findings if f.category == "unrealistic_experience"]
        assert u

    def test_yrs_abbreviation(self):
        rep = detect_anti_patterns("25 yrs in microservices.")
        u = [f for f in rep.findings if f.category == "unrealistic_experience"]
        assert u

    def test_no_year_phrase(self):
        rep = detect_anti_patterns("Looking for senior engineers.")
        assert not [f for f in rep.findings if f.category == "unrealistic_experience"]


# ── culture red flag ────────────────────────────────────────────────


class TestCultureRedFlag:
    def test_were_a_family(self):
        rep = detect_anti_patterns("We're a family at Acme Corp.")
        c = [f for f in rep.findings if f.category == "culture_red_flag"]
        assert c and c[0].term == "we're a family"
        assert c[0].severity == "warn"

    def test_we_are_family(self):
        rep = detect_anti_patterns("We are a family of builders.")
        assert any(f.term == "we're a family" for f in rep.findings)

    def test_work_hard_play_hard(self):
        rep = detect_anti_patterns("We work hard, play hard.")
        assert any(f.term == "work hard, play hard" for f in rep.findings)

    def test_wear_many_hats_info(self):
        rep = detect_anti_patterns("You'll wear many hats here.")
        c = [f for f in rep.findings if f.term == "wear many hats"]
        assert c and c[0].severity == "info"

    def test_passionate_about(self):
        rep = detect_anti_patterns("Must be passionate about distributed systems.")
        assert any(f.term == "passionate about" for f in rep.findings)

    def test_fast_paced(self):
        rep = detect_anti_patterns("Thrive in a fast-paced environment.")
        assert any(f.term == "fast-paced environment" for f in rep.findings)

    def test_unlimited_pto(self):
        rep = detect_anti_patterns("Unlimited PTO and flexible hours.")
        c = [f for f in rep.findings if f.category == "culture_red_flag"]
        # both "unlimited pto" and "flexible hours" should match
        terms = {f.term for f in c}
        assert "unlimited PTO/hours" in terms


# ── urgency ─────────────────────────────────────────────────────────


class TestUrgency:
    def test_asap(self):
        rep = detect_anti_patterns("Need to fill ASAP.")
        u = [f for f in rep.findings if f.category == "urgency"]
        assert u and u[0].term == "ASAP"
        assert u[0].severity == "info"

    def test_immediate_start(self):
        rep = detect_anti_patterns("Immediate start required.")
        assert any(f.term == "immediate start" for f in rep.findings)

    def test_urgent_hire(self):
        rep = detect_anti_patterns("Urgently hiring 10 engineers.")
        assert any(f.term == "urgent hire" for f in rep.findings)

    def test_no_urgency_phrase(self):
        rep = detect_anti_patterns("We hire continuously throughout the year.")
        assert not [f for f in rep.findings if f.category == "urgency"]


# ── snippet ─────────────────────────────────────────────────────────


class TestSnippet:
    def test_snippet_includes_match(self):
        text = "We are looking for a rockstar engineer to join us."
        rep = detect_anti_patterns(text)
        assert rep.findings[0].snippet
        assert "rockstar" in rep.findings[0].snippet.lower()

    def test_snippet_collapses_whitespace(self):
        text = "We need a   rockstar\n\n\tengineer."
        rep = detect_anti_patterns(text)
        snip = rep.findings[0].snippet
        # No double spaces / no \n / no \t
        assert "  " not in snip
        assert "\n" not in snip
        assert "\t" not in snip

    def test_snippet_short_text_no_ellipses(self):
        text = "Hire a ninja."
        rep = detect_anti_patterns(text)
        snip = rep.findings[0].snippet
        assert not snip.startswith("…")
        assert not snip.endswith("…")

    def test_snippet_long_text_has_ellipses(self):
        # Place the term in the middle of a long blob
        prefix = "x " * 100
        suffix = " y" * 100
        text = f"{prefix}rockstar{suffix}"
        rep = detect_anti_patterns(text)
        snip = rep.findings[0].snippet
        assert snip.startswith("…")
        assert snip.endswith("…")

    def test_char_offsets_match_original_text(self):
        text = "Hello rockstar world"
        rep = detect_anti_patterns(text)
        f = rep.findings[0]
        assert text[f.char_start : f.char_end].lower() == "rockstar"


# ── sorting ─────────────────────────────────────────────────────────


class TestSorting:
    def test_critical_before_warn_before_info(self):
        text = (
            "ASAP hire. "                    # info (urgency)
            "Competitive salary. "           # warn (vague comp)
            "Looking for a rockstar."        # critical (gendered)
        )
        rep = detect_anti_patterns(text)
        sevs = [f.severity for f in rep.findings]
        # Sorted ascending by rank: critical(0), warn(1), info(2)
        assert sevs == sorted(sevs, key=lambda s: {"critical": 0, "warn": 1, "info": 2}[s])

    def test_within_severity_source_order_preserved(self):
        text = "rockstar at the start, then later a ninja appears."
        rep = detect_anti_patterns(text)
        gendered = [f for f in rep.findings if f.category == "gendered"]
        # Both critical → sorted by char_start
        assert [f.term for f in gendered] == ["rockstar", "ninja"]


# ── counts ──────────────────────────────────────────────────────────


class TestCounts:
    def test_by_category_sums_to_total(self):
        text = (
            "rockstar ninja salesman "          # 3 gendered
            "competitive salary DOE "           # 2 vague comp (DOE matches once)
            "ASAP "                             # 1 urgency
        )
        rep = detect_anti_patterns(text)
        assert sum(rep.by_category.values()) == rep.total_count

    def test_severity_counts_sum_to_total(self):
        text = "rockstar competitive salary ASAP."
        rep = detect_anti_patterns(text)
        assert sum(rep.severity_counts.values()) == rep.total_count

    def test_all_six_categories_present_in_dict(self):
        rep = detect_anti_patterns("")
        assert set(rep.by_category.keys()) == {
            "ageist", "gendered", "vague_compensation",
            "unrealistic_experience", "culture_red_flag", "urgency",
        }

    def test_severity_dict_always_has_three_keys(self):
        rep = detect_anti_patterns("")
        assert set(rep.severity_counts.keys()) == {"critical", "warn", "info"}


# ── real-world JD ──────────────────────────────────────────────────


class TestRealJDs:
    def test_textbook_bad_jd(self):
        text = """
        We're a family of digital natives looking for a young, dynamic
        rockstar engineer to join our fast-paced environment. 20+ years
        Kubernetes required. Competitive salary. Need to fill ASAP.
        Wear many hats and be passionate about software!
        """
        rep = detect_anti_patterns(text)

        # At minimum: ageist (digital native + young dynamic), gendered (rockstar),
        # vague comp (competitive), unrealistic exp (20+ years), culture (we're a family,
        # fast-paced, wear many hats, passionate about), urgency (ASAP)
        assert rep.by_category["ageist"] >= 2
        assert rep.by_category["gendered"] >= 1
        assert rep.by_category["vague_compensation"] >= 1
        assert rep.by_category["unrealistic_experience"] >= 1
        assert rep.by_category["culture_red_flag"] >= 3
        assert rep.by_category["urgency"] >= 1

        # Critical findings come first
        assert rep.findings[0].severity == "critical"

    def test_clean_modern_jd(self):
        text = """
        Senior Platform Engineer
        Compensation: $190k base + $40k bonus + 0.05% equity.
        Stack: Go, PostgreSQL, Kubernetes, AWS.
        5+ years building distributed systems.
        Remote within US/EU. We invest in deep work and avoid heroics.
        """
        rep = detect_anti_patterns(text)
        assert rep.severity_counts["critical"] == 0
        assert rep.severity_counts["warn"] == 0

    def test_idempotent(self):
        text = "Rockstar wanted. ASAP. Competitive salary."
        a = detect_anti_patterns(text)
        b = detect_anti_patterns(text)
        assert a == b


# ── invariants ─────────────────────────────────────────────────────


class TestInvariants:
    def test_findings_is_tuple(self):
        rep = detect_anti_patterns("rockstar")
        assert isinstance(rep.findings, tuple)

    def test_finding_is_frozen(self):
        rep = detect_anti_patterns("rockstar")
        f = rep.findings[0]
        with pytest.raises(Exception):
            f.term = "changed"  # type: ignore[misc]

    def test_report_is_frozen(self):
        rep = detect_anti_patterns("")
        with pytest.raises(Exception):
            rep.total_count = 99  # type: ignore[misc]

    def test_snippet_radius_constant_consistent(self):
        # ensure SNIPPET_RADIUS export matches the snippet sizing logic
        text = ("x " * SNIPPET_RADIUS) + "rockstar" + (" y" * SNIPPET_RADIUS)
        rep = detect_anti_patterns(text)
        # Should ellipse on both sides
        assert rep.findings[0].snippet.startswith("…")
        assert rep.findings[0].snippet.endswith("…")
