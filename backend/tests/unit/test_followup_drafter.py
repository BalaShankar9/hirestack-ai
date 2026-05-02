"""A1.next — followup_drafter unit tests.

Drafter is a PURE function.  Tests cover:
  * each of the 4 templates × correct channel renders
  * email subjects render; linkedin subject is None
  * placeholders_missing reports each empty/None/whitespace field
  * defaults are substituted (no bare {placeholder} ever leaks)
  * determinism + immutability of inputs
  * unknown (template, channel) combo raises ValueError
  * voice guard: no banned filler phrases or exclamation marks
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.cadence_engine import FollowupBeat
from app.services.followup_drafter import (
    FollowupDraft,
    render_followup_draft,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _beat(template_key="first", channel="email", count=1):
    return FollowupBeat(
        template_key=template_key,
        channel=channel,
        scheduled_for=datetime(2026, 5, 5, 9, 30, tzinfo=timezone.utc),
        followup_count=count,
        reason="test",
    )


def _full_app(**overrides):
    base = {
        "company_name": "Acme",
        "role_title": "Senior Engineer",
        "contact_name": "Jordan",
        "user_first_name": "Sam",
    }
    base.update(overrides)
    return base


# ── Happy-path render per template ───────────────────────────────────


def test_first_email_renders_subject_and_body() -> None:
    draft = render_followup_draft(_beat("first", "email"), _full_app())
    assert isinstance(draft, FollowupDraft)
    assert draft.template_key == "first"
    assert draft.channel == "email"
    assert draft.subject == "Re: Senior Engineer — quick note"
    assert "Hi Jordan" in draft.body
    assert "Senior Engineer" in draft.body
    assert "Acme" in draft.body
    assert "Sam" in draft.body
    assert draft.placeholders_missing == ()


def test_linkedin_template_has_no_subject() -> None:
    draft = render_followup_draft(_beat("linkedin", "linkedin"), _full_app())
    assert draft.subject is None
    assert draft.channel == "linkedin"
    assert "Jordan" in draft.body
    assert "Senior Engineer" in draft.body
    assert "Acme" in draft.body


def test_second_email_renders() -> None:
    draft = render_followup_draft(
        _beat("second", "email", count=3), _full_app()
    )
    assert draft.subject == "Re: Senior Engineer — short follow-up"
    assert "circle back" in draft.body
    assert draft.template_key == "second"


def test_cold_reopen_email_renders() -> None:
    draft = render_followup_draft(
        _beat("cold_reopen", "email", count=4), _full_app()
    )
    assert draft.subject == "Re: Senior Engineer — last note from me"
    assert "Last note" in draft.body


# ── Placeholder fallback ─────────────────────────────────────────────


def test_missing_company_name_falls_back_to_default_and_reports() -> None:
    draft = render_followup_draft(
        _beat(), _full_app(company_name="")
    )
    assert "your team" in draft.body
    assert "company_name" in draft.placeholders_missing
    assert "{company_name}" not in draft.body
    assert "{company_name}" not in (draft.subject or "")


def test_none_value_treated_as_missing() -> None:
    draft = render_followup_draft(_beat(), _full_app(role_title=None))
    assert "the role" in (draft.subject or "")
    assert "role_title" in draft.placeholders_missing


def test_whitespace_only_treated_as_missing() -> None:
    draft = render_followup_draft(_beat(), _full_app(contact_name="   \t  "))
    # Default for contact_name is "there" → "Hi there,"
    assert "Hi there" in draft.body
    assert "contact_name" in draft.placeholders_missing


def test_all_fields_missing_lists_all() -> None:
    draft = render_followup_draft(
        _beat(),
        {"company_name": "", "role_title": "", "contact_name": "", "user_first_name": ""},
    )
    assert set(draft.placeholders_missing) == {
        "company_name", "role_title", "contact_name", "user_first_name",
    }
    # No bare placeholders leaked.
    for marker in ("{company_name}", "{role_title}", "{contact_name}", "{user_first_name}"):
        assert marker not in draft.body
        assert marker not in (draft.subject or "")


def test_empty_application_dict_renders_with_all_defaults() -> None:
    draft = render_followup_draft(_beat(), {})
    assert len(draft.placeholders_missing) == 4
    assert "your team" in draft.body
    assert "the role" in draft.body


def test_non_string_value_is_coerced() -> None:
    # E.g. an int slipped in from a Pydantic model.
    draft = render_followup_draft(_beat(), _full_app(role_title=42))
    assert "42" in (draft.subject or "")
    # Coerced value is non-empty → NOT reported as missing.
    assert "role_title" not in draft.placeholders_missing


# ── Determinism / immutability ───────────────────────────────────────


def test_render_is_deterministic() -> None:
    a = render_followup_draft(_beat(), _full_app())
    b = render_followup_draft(_beat(), _full_app())
    assert a == b


def test_render_does_not_mutate_application() -> None:
    app = _full_app()
    snapshot = dict(app)
    render_followup_draft(_beat(), app)
    assert app == snapshot


def test_render_does_not_mutate_beat() -> None:
    beat = _beat()
    render_followup_draft(beat, _full_app())
    # Frozen dataclass — assignment would raise.  Just confirm fields stable.
    assert beat.template_key == "first"
    assert beat.followup_count == 1


# ── Error cases ──────────────────────────────────────────────────────


def test_unknown_template_channel_combination_raises() -> None:
    bad = FollowupBeat(
        template_key="first",
        channel="form",  # 'form' has no template defined.
        scheduled_for=datetime(2026, 5, 5, 9, 30, tzinfo=timezone.utc),
        followup_count=1,
        reason="test",
    )
    with pytest.raises(ValueError, match="no template"):
        render_followup_draft(bad, _full_app())


def test_linkedin_template_paired_with_email_channel_raises() -> None:
    # We only ship linkedin/linkedin and email-only for the rest;
    # mismatched pair must fail loudly so we never render wrong wording.
    bad = FollowupBeat(
        template_key="linkedin",
        channel="email",
        scheduled_for=datetime(2026, 5, 5, 9, 30, tzinfo=timezone.utc),
        followup_count=2,
        reason="test",
    )
    with pytest.raises(ValueError):
        render_followup_draft(bad, _full_app())


# ── Voice guard ──────────────────────────────────────────────────────


_BANNED_PHRASES = (
    "i hope this finds you well",
    "just checking in",
    "amazing opportunity",
    "super excited",
    "i am thrilled",
    "i'm thrilled",
    "circle back to you when",
)


@pytest.mark.parametrize(
    "template_key,channel",
    [
        ("first", "email"),
        ("linkedin", "linkedin"),
        ("second", "email"),
        ("cold_reopen", "email"),
    ],
)
def test_no_banned_filler_phrases_in_any_template(template_key, channel) -> None:
    draft = render_followup_draft(_beat(template_key, channel), _full_app())
    haystack = (draft.body + " " + (draft.subject or "")).lower()
    for phrase in _BANNED_PHRASES:
        assert phrase not in haystack, f"{template_key}/{channel} contains banned phrase: {phrase!r}"


@pytest.mark.parametrize(
    "template_key,channel",
    [
        ("first", "email"),
        ("linkedin", "linkedin"),
        ("second", "email"),
        ("cold_reopen", "email"),
    ],
)
def test_no_exclamation_marks(template_key, channel) -> None:
    draft = render_followup_draft(_beat(template_key, channel), _full_app())
    assert "!" not in draft.body
    assert "!" not in (draft.subject or "")


@pytest.mark.parametrize(
    "template_key,channel",
    [
        ("first", "email"),
        ("second", "email"),
        ("cold_reopen", "email"),
    ],
)
def test_email_subjects_are_short(template_key, channel) -> None:
    draft = render_followup_draft(_beat(template_key, channel), _full_app())
    assert draft.subject is not None
    assert len(draft.subject.split()) <= 8


@pytest.mark.parametrize(
    "template_key,channel",
    [
        ("first", "email"),
        ("linkedin", "linkedin"),
        ("second", "email"),
        ("cold_reopen", "email"),
    ],
)
def test_bodies_are_under_120_words(template_key, channel) -> None:
    draft = render_followup_draft(_beat(template_key, channel), _full_app())
    assert len(draft.body.split()) <= 120
