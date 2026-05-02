"""A1.next — follow-up drafter.

PURE-FUNCTION template rendering for the beats produced by
``cadence_engine.next_followup_beat``.  No I/O, no LLM calls, no
network — deterministic so the worker can render a draft a few
minutes before ``scheduled_for`` and a human can edit before send.

Companion to ``cadence_engine``:
    * cadence_engine answers WHEN  (which template + when to fire)
    * followup_drafter answers WHAT (subject + body for that template)
    * the persister is responsible for the row write
    * the user is the only one who hits Send (HARD RULE §7.12 / §13)

Voice (V1 ``voice_guard`` ethos):
    * direct, concrete, ≤120 words
    * no sycophancy ("amazing opportunity", "super excited")
    * no filler ("I hope this finds you well", "just checking in")
    * subject lines ≤8 words, no clickbait, no exclamation marks

Each template tolerates missing context fields by substituting safe
defaults (``"the team"``, ``"your team"``, ``"your role"``).  The
caller learns which fields were missing via
``FollowupDraft.placeholders_missing`` so a UI can prompt the user to
fill them in before sending.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from app.services.cadence_engine import Channel, FollowupBeat, TemplateKey

# ── Public types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class FollowupDraft:
    """A rendered follow-up message ready for the user to review.

    ``subject`` is ``None`` when ``channel != 'email'`` (LinkedIn DMs
    have no subject line).  The persister stores this on the
    ``application_followups`` row and the worker flips status to
    ``'draft_ready'``.
    """
    template_key: TemplateKey
    channel: Channel
    subject: Optional[str]
    body: str
    placeholders_missing: tuple[str, ...]


# ── Defaults for missing context ──────────────────────────────────────

_DEFAULTS: Mapping[str, str] = {
    "company_name": "your team",
    "role_title":   "the role",
    "contact_name": "there",        # → "Hi there,"
    "user_first_name": "—",         # signature line; flagged if missing
}

# Tracked placeholders — each template renders some subset of these.
_TRACKED_FIELDS: tuple[str, ...] = (
    "company_name", "role_title", "contact_name", "user_first_name",
)


# ── Template strings ──────────────────────────────────────────────────
#
# Subjects use no exclamation, no emoji, no "Following up:" prefix
# (recruiters mute those).  Bodies are short and free of corporate
# filler so the user can edit a few words and send.

_TEMPLATES: dict[tuple[TemplateKey, Channel], dict[str, str]] = {
    ("first", "email"): {
        "subject": "Re: {role_title} — quick note",
        "body": (
            "Hi {contact_name},\n\n"
            "Following up on my application for {role_title} at {company_name}. "
            "Happy to share any additional context that would help — work samples, "
            "references, or a short call.\n\n"
            "Best,\n{user_first_name}"
        ),
    },
    ("linkedin", "linkedin"): {
        # No subject for LinkedIn DMs.
        "body": (
            "Hi {contact_name} — I applied for {role_title} at {company_name} "
            "and wanted to introduce myself directly. Open to a quick chat if "
            "useful. Thanks for the time."
        ),
    },
    ("second", "email"): {
        "subject": "Re: {role_title} — short follow-up",
        "body": (
            "Hi {contact_name},\n\n"
            "Wanted to circle back on the {role_title} role at {company_name}. "
            "If timing has shifted or the team is no longer hiring for this, "
            "a one-line reply is enough — I will not keep nudging.\n\n"
            "Best,\n{user_first_name}"
        ),
    },
    ("cold_reopen", "email"): {
        "subject": "Re: {role_title} — last note from me",
        "body": (
            "Hi {contact_name},\n\n"
            "Last note on the {role_title} role at {company_name}. If the "
            "search re-opens or a related role comes up, I would value a "
            "quick reply. Otherwise I will close the loop on my end.\n\n"
            "Best,\n{user_first_name}"
        ),
    },
}


# ── Render ────────────────────────────────────────────────────────────


def _resolve_field(application: Mapping[str, object], key: str) -> tuple[str, bool]:
    """Return (value_to_render, was_missing).

    Missing == empty string, None, or whitespace-only.  Missing fields
    fall back to ``_DEFAULTS[key]`` so the template never renders a
    bare ``{placeholder}``.
    """
    raw = application.get(key)
    if raw is None:
        return _DEFAULTS[key], True
    if not isinstance(raw, str):
        raw = str(raw)
    stripped = raw.strip()
    if not stripped:
        return _DEFAULTS[key], True
    return stripped, False


def render_followup_draft(
    beat: FollowupBeat,
    application: Mapping[str, object],
) -> FollowupDraft:
    """Render the draft for a single beat against an application.

    Pure function.  Same (beat, application) → same draft.  Does not
    mutate either input.

    Raises ``ValueError`` if ``(beat.template_key, beat.channel)`` is
    not a known combination — that should never happen because the
    cadence engine and the drafter share the same template set.
    """
    key = (beat.template_key, beat.channel)
    template = _TEMPLATES.get(key)
    if template is None:
        raise ValueError(
            f"no template for ({beat.template_key!r}, {beat.channel!r})"
        )

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for field in _TRACKED_FIELDS:
        value, was_missing = _resolve_field(application, field)
        resolved[field] = value
        if was_missing:
            missing.append(field)

    body = template["body"].format(**resolved)
    subject_tpl = template.get("subject")
    subject = subject_tpl.format(**resolved) if subject_tpl else None

    return FollowupDraft(
        template_key=beat.template_key,
        channel=beat.channel,
        subject=subject,
        body=body,
        placeholders_missing=tuple(missing),
    )


__all__ = [
    "FollowupDraft",
    "render_followup_draft",
]
