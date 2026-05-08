"""A3 — morning brief composer unit tests.

Composer is PURE.  Coverage:
  * subject uses concrete counts, not vibes
  * empty inputs → is_empty() True (caller skips send)
  * each section renders only when populated
  * MAX_PER_SECTION cap with "and N more" overflow line
  * nudge priority: beats > stale > jobs > wins > none
  * voice guard: no exclamation, no banned filler
  * HTML escaping for hostile company/role names
  * determinism + input immutability
  * ≤200-word body, ≤9-word subject
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.morning_brief import (
    BeatItem,
    JobItem,
    MorningBrief,
    MorningBriefInputs,
    ReadyItem,
    StaleItem,
    WinItem,
    compose_morning_brief,
)


# ── Helpers ───────────────────────────────────────────────────────────


_TODAY = date(2026, 5, 4)  # Monday


def _inputs(**overrides) -> MorningBriefInputs:
    base = dict(
        user_first_name="Sam",
        brief_date=_TODAY,
        ready_to_apply=(),
        beats_today=(),
        new_jobs=(),
        stale_applications=(),
        wins_yesterday=(),
    )
    base.update(overrides)
    return MorningBriefInputs(**base)


def _beat(company="Acme", role="Senior Engineer", template="first", aid="a1") -> BeatItem:
    return BeatItem(company_name=company, role_title=role,
                    template_key=template, application_id=aid)


def _ready(company="Acme", role="Senior Engineer", aid="a-ready") -> ReadyItem:
    return ReadyItem(company_name=company, role_title=role, application_id=aid)


def _job(company="Globex", role="Staff Eng", url="https://x/j/1", days=2) -> JobItem:
    return JobItem(company_name=company, role_title=role, url=url,
                   posted_within_days=days)


def _stale(company="Initech", role="Eng", days=21, aid="a9") -> StaleItem:
    return StaleItem(company_name=company, role_title=role,
                     days_silent=days, application_id=aid)


def _win(company="Hooli", role="Senior Eng", kind="response") -> WinItem:
    return WinItem(company_name=company, role_title=role, kind=kind)


# ── Empty / quiet day ────────────────────────────────────────────────


def test_empty_inputs_produces_is_empty_brief() -> None:
    brief = compose_morning_brief(_inputs())
    assert brief.is_empty() is True
    assert brief.section_counts == {"ready": 0, "beats": 0, "jobs": 0, "stale": 0, "wins": 0}
    assert brief.nudge is None
    # Greeting only — still safe to NOT send.
    assert "Morning, Sam." in brief.body_text


def test_brief_returns_dataclass_with_all_fields() -> None:
    brief = compose_morning_brief(_inputs(beats_today=(_beat(),)))
    assert isinstance(brief, MorningBrief)
    assert isinstance(brief.subject, str)
    assert isinstance(brief.body_text, str)
    assert isinstance(brief.body_html, str)
    assert brief.body_html.startswith("<p>")


# ── Subject ──────────────────────────────────────────────────────────


def test_subject_uses_concrete_counts_when_populated() -> None:
    brief = compose_morning_brief(_inputs(
        ready_to_apply=(_ready(),),
        beats_today=(_beat(), _beat()),
        new_jobs=(_job(),),
        wins_yesterday=(_win(),),
    ))
    assert brief.subject == "2026-05-04: 1 ready + 2 follow-ups + 1 new + 1 win"


def test_subject_singularises_when_count_is_one() -> None:
    brief = compose_morning_brief(_inputs(beats_today=(_beat(),)))
    assert "1 follow-up" in brief.subject
    assert "1 follow-ups" not in brief.subject


def test_subject_falls_back_to_date_when_no_signals() -> None:
    brief = compose_morning_brief(_inputs())
    assert brief.subject == "Brief for 2026-05-04"


def test_subject_is_under_nine_words() -> None:
    brief = compose_morning_brief(_inputs(
        beats_today=tuple(_beat() for _ in range(9)),
        new_jobs=tuple(_job() for _ in range(9)),
        wins_yesterday=tuple(_win() for _ in range(9)),
    ))
    assert len(brief.subject.split()) <= 9


# ── Section presence ────────────────────────────────────────────────


def test_only_populated_sections_render_in_text() -> None:
    brief = compose_morning_brief(_inputs(beats_today=(_beat(),)))
    assert "Today's follow-ups" in brief.body_text
    assert "Ready to apply" not in brief.body_text
    assert "New jobs" not in brief.body_text
    assert "Stale" not in brief.body_text
    assert "Wins yesterday" not in brief.body_text


def test_only_populated_sections_render_in_html() -> None:
    brief = compose_morning_brief(_inputs(wins_yesterday=(_win(),)))
    assert "<h3>Wins yesterday</h3>" in brief.body_html
    assert "Today's follow-ups" not in brief.body_html


def test_all_sections_render_when_all_populated() -> None:
    brief = compose_morning_brief(_inputs(
        ready_to_apply=(_ready(),),
        beats_today=(_beat(),), new_jobs=(_job(),),
        stale_applications=(_stale(),), wins_yesterday=(_win(),),
    ))
    for label in ("Ready to apply", "Today's follow-ups", "New jobs", "Stale", "Wins yesterday"):
        assert label in brief.body_text


def test_template_key_renders_human_label() -> None:
    brief = compose_morning_brief(_inputs(
        beats_today=(_beat(template="cold_reopen"),),
    ))
    assert "cold reopen" in brief.body_text
    assert "cold_reopen" not in brief.body_text


def test_unknown_template_key_falls_through_to_raw() -> None:
    brief = compose_morning_brief(_inputs(
        beats_today=(_beat(template="weird"),),
    ))
    assert "weird" in brief.body_text  # no crash, raw value used


# ── Section caps ─────────────────────────────────────────────────────


def test_section_capped_at_five_with_overflow_line() -> None:
    items = tuple(_beat(company=f"Co{i}") for i in range(8))
    brief = compose_morning_brief(_inputs(beats_today=items))
    # Cap = 5, so overflow line says "and 3 more".
    assert "and 3 more" in brief.body_text
    # Co5..Co7 should NOT be enumerated.
    assert "Co0" in brief.body_text
    assert "Co5" not in brief.body_text


def test_exactly_five_items_no_overflow_line() -> None:
    items = tuple(_beat(company=f"Co{i}") for i in range(5))
    brief = compose_morning_brief(_inputs(beats_today=items))
    assert "more" not in brief.body_text


# ── Nudge priority ──────────────────────────────────────────────────


def test_nudge_priority_beats_first() -> None:
    brief = compose_morning_brief(_inputs(
        ready_to_apply=(_ready(),),
        beats_today=(_beat(),),
        stale_applications=(_stale(),),
        new_jobs=(_job(),),
        wins_yesterday=(_win(),),
    ))
    assert brief.nudge is not None
    assert "follow-up" in brief.nudge


def test_nudge_priority_ready_when_no_beats() -> None:
    brief = compose_morning_brief(_inputs(
        ready_to_apply=(_ready(company="Acme", role="Platform Engineer"),),
        new_jobs=(_job(),),
        wins_yesterday=(_win(),),
    ))
    assert brief.nudge is not None
    assert "ready drafts" in brief.nudge


def test_nudge_priority_stale_when_no_beats() -> None:
    brief = compose_morning_brief(_inputs(
        stale_applications=(_stale(company="Initech", days=30),),
        new_jobs=(_job(),),
        wins_yesterday=(_win(),),
    ))
    assert brief.nudge is not None
    assert "Initech" in brief.nudge
    assert "30 days" in brief.nudge


def test_nudge_priority_jobs_when_no_beats_or_stale() -> None:
    brief = compose_morning_brief(_inputs(new_jobs=(_job(),)))
    assert brief.nudge is not None
    assert "Triage" in brief.nudge


def test_nudge_priority_wins_when_only_wins() -> None:
    brief = compose_morning_brief(_inputs(wins_yesterday=(_win(),)))
    assert brief.nudge is not None
    assert "momentum" in brief.nudge


def test_no_nudge_when_truly_empty() -> None:
    brief = compose_morning_brief(_inputs())
    assert brief.nudge is None


def test_stale_nudge_picks_oldest_application() -> None:
    brief = compose_morning_brief(_inputs(stale_applications=(
        _stale(company="A", days=15),
        _stale(company="B", days=42),
        _stale(company="C", days=21),
    )))
    assert "B" in brief.nudge
    assert "42 days" in brief.nudge


# ── Voice guard ─────────────────────────────────────────────────────


_BANNED = (
    "amazing opportunity", "super excited", "i am thrilled", "i'm thrilled",
    "i hope this finds you well", "just checking in",
)


def test_no_exclamation_marks_anywhere() -> None:
    brief = compose_morning_brief(_inputs(
        beats_today=(_beat(),), new_jobs=(_job(),),
        stale_applications=(_stale(),), wins_yesterday=(_win(),),
    ))
    assert "!" not in brief.subject
    assert "!" not in brief.body_text
    assert "!" not in brief.body_html


def test_no_banned_filler_phrases() -> None:
    brief = compose_morning_brief(_inputs(
        beats_today=(_beat(),), new_jobs=(_job(),),
        stale_applications=(_stale(),), wins_yesterday=(_win(),),
    ))
    haystack = (brief.subject + " " + brief.body_text).lower()
    for phrase in _BANNED:
        assert phrase not in haystack


def test_body_under_two_hundred_words() -> None:
    brief = compose_morning_brief(_inputs(
        beats_today=tuple(_beat(company=f"Co{i}") for i in range(5)),
        new_jobs=tuple(_job(company=f"J{i}") for i in range(5)),
        stale_applications=tuple(_stale(company=f"S{i}") for i in range(5)),
        wins_yesterday=tuple(_win(company=f"W{i}") for i in range(5)),
    ))
    assert len(brief.body_text.split()) <= 200


# ── HTML safety ─────────────────────────────────────────────────────


def test_html_escapes_hostile_company_name() -> None:
    brief = compose_morning_brief(_inputs(
        beats_today=(_beat(company="<script>x</script>"),),
    ))
    assert "<script>x</script>" not in brief.body_html
    assert "&lt;script&gt;" in brief.body_html


def test_html_escapes_ampersand_and_quote() -> None:
    brief = compose_morning_brief(_inputs(
        new_jobs=(_job(company='A&B "Co"'),),
    ))
    assert 'A&amp;B &quot;Co&quot;' in brief.body_html
    # Plain text body stays raw — only HTML is escaped.
    assert 'A&B "Co"' in brief.body_text


# ── Determinism / immutability ──────────────────────────────────────


def test_compose_is_deterministic() -> None:
    inp = _inputs(beats_today=(_beat(),), new_jobs=(_job(),))
    a = compose_morning_brief(inp)
    b = compose_morning_brief(inp)
    assert a == b


def test_compose_does_not_mutate_inputs() -> None:
    beats = (_beat(), _beat())
    jobs = (_job(),)
    inp = _inputs(beats_today=beats, new_jobs=jobs)
    snap_beats = tuple(beats)
    snap_jobs = tuple(jobs)
    compose_morning_brief(inp)
    assert beats == snap_beats
    assert jobs == snap_jobs


# ── is_empty ────────────────────────────────────────────────────────


def test_is_empty_true_when_no_sections_and_no_nudge() -> None:
    brief = compose_morning_brief(_inputs())
    assert brief.is_empty() is True


def test_is_empty_false_when_any_section_populated() -> None:
    for kwargs in (
        {"ready_to_apply": (_ready(),)},
        {"beats_today": (_beat(),)},
        {"new_jobs": (_job(),)},
        {"stale_applications": (_stale(),)},
        {"wins_yesterday": (_win(),)},
    ):
        brief = compose_morning_brief(_inputs(**kwargs))
        assert brief.is_empty() is False


# ── Greeting ────────────────────────────────────────────────────────


def test_greeting_uses_user_first_name() -> None:
    brief = compose_morning_brief(_inputs(user_first_name="Alex"))
    assert "Morning, Alex." in brief.body_text
    assert "Morning, Alex." in brief.body_html
