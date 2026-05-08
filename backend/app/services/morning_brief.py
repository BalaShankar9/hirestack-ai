"""A3 — morning brief composer.

PURE-FUNCTION assembly of the daily 7am brief.  No I/O, no SMTP, no
template engine — just deterministic plain-text + minimal HTML
generation from pre-fetched bundles.  The Celery cron, Postmark/Resend
transport, and user-timezone scheduling are separate slices that
collect the inputs and call this composer.

A morning brief is the user's daily reactivation channel.  It has
six sections, all skipped when empty:

    1. Ready to apply          — drafted workspaces with review-ready docs
                                                                waiting for the user's morning pass
    2. Today's beats           — pending follow-ups due today
                                (from cadence_engine / application_followups)
    3. New jobs                — fresh hits from portal scanners
                                (from portal_scanner / job_scan_history)
    4. Stale applications      — applications silent ≥14 days, not closed
    5. Wins yesterday          — responses received, interviews scheduled
    6. One nudge               — single short prompt the user can act on

Voice (V1 voice_guard ethos enforced by tests):
  * direct, concrete, ≤200 words total body
  * no exclamation marks
  * no banned filler ("amazing opportunity", "super excited", etc.)
  * subject ≤9 words; uses concrete count when possible
                       ("3 follow-ups + 2 new") not vibes
                       ("Your morning is here").

If ALL five sections are empty the composer returns
``MorningBrief.is_empty()`` = True and the cron should NOT send the
email.  Quiet days don't deserve noise.

HARD RULE: this composer NEVER renders a Send/Submit button or any
auto-action link.  The brief is a digest; the user opens the app to
act (mirrors §7.12 / §13 user-clicks-Send rule for cadence).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Mapping, Optional, Sequence

# ── Public types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class BeatItem:
    """A single follow-up due today."""
    company_name: str
    role_title: str
    template_key: str           # 'first' | 'linkedin' | 'second' | 'cold_reopen'
    application_id: str


@dataclass(frozen=True)
class ReadyItem:
    """A draft workspace that is ready for user review."""

    company_name: str
    role_title: str
    application_id: str


@dataclass(frozen=True)
class JobItem:
    """A single new job hit from a portal scanner."""
    company_name: str
    role_title: str
    url: str
    posted_within_days: Optional[int] = None  # None → unknown


@dataclass(frozen=True)
class StaleItem:
    """An application that has been silent for ≥14 days."""
    company_name: str
    role_title: str
    days_silent: int
    application_id: str


@dataclass(frozen=True)
class WinItem:
    """A response/interview received yesterday."""
    company_name: str
    role_title: str
    kind: str  # 'response' | 'interview' | 'offer'


@dataclass(frozen=True)
class MorningBriefInputs:
    """The pre-fetched data the composer turns into a brief.

    The caller (cron / orchestrator) builds this; the composer is
    pure with respect to it.
    """
    user_first_name: str
    brief_date: date
    ready_to_apply: Sequence[ReadyItem] = field(default_factory=tuple)
    beats_today: Sequence[BeatItem] = field(default_factory=tuple)
    new_jobs: Sequence[JobItem] = field(default_factory=tuple)
    stale_applications: Sequence[StaleItem] = field(default_factory=tuple)
    wins_yesterday: Sequence[WinItem] = field(default_factory=tuple)


@dataclass(frozen=True)
class MorningBrief:
    """Composer output: subject + plain-text + html body + summary counts."""
    subject: str
    body_text: str
    body_html: str
    section_counts: Mapping[str, int]   # {'ready':N,'beats':N,'jobs':N,'stale':N,'wins':N}
    nudge: Optional[str]                # single one-liner or None

    def is_empty(self) -> bool:
        """True when no section had any content — caller should skip send."""
        return all(v == 0 for v in self.section_counts.values()) and self.nudge is None


# ── Constants ─────────────────────────────────────────────────────────


_MAX_PER_SECTION = 5  # cap each section to keep brief skimmable
_BODY_WORD_CAP = 200
_SUBJECT_WORD_CAP = 9


# ── Subject ───────────────────────────────────────────────────────────


def _build_subject(inputs: MorningBriefInputs, counts: Mapping[str, int]) -> str:
    """Concrete-count subject; never vibes-only."""
    ready = counts["ready"]
    beats = counts["beats"]
    jobs = counts["jobs"]
    wins = counts["wins"]

    parts: list[str] = []
    if ready:
        parts.append(f"{ready} ready")
    if beats:
        parts.append(f"{beats} follow-up{'s' if beats != 1 else ''}")
    if jobs:
        parts.append(f"{jobs} new")
    if wins:
        parts.append(f"{wins} win{'s' if wins != 1 else ''}")

    if not parts:
        # Empty-ish brief fallback (caller usually skips send entirely).
        return f"Brief for {inputs.brief_date.isoformat()}"

    return f"{inputs.brief_date.isoformat()}: " + " + ".join(parts)


# ── Section renderers (text) ──────────────────────────────────────────


_TEMPLATE_LABEL: Mapping[str, str] = {
    "first":       "first follow-up",
    "linkedin":    "LinkedIn intro",
    "second":      "second follow-up",
    "cold_reopen": "cold reopen",
}


def _render_beats_text(items: Sequence[BeatItem]) -> str:
    if not items:
        return ""
    lines = ["Today's follow-ups:"]
    for b in items[:_MAX_PER_SECTION]:
        label = _TEMPLATE_LABEL.get(b.template_key, b.template_key)
        lines.append(f"  - {b.company_name} — {b.role_title} ({label})")
    if len(items) > _MAX_PER_SECTION:
        lines.append(f"  - and {len(items) - _MAX_PER_SECTION} more")
    return "\n".join(lines)


def _render_ready_text(items: Sequence[ReadyItem]) -> str:
    if not items:
        return ""
    lines = ["Ready to apply:"]
    for item in items[:_MAX_PER_SECTION]:
        lines.append(f"  - {item.company_name} — {item.role_title}")
    if len(items) > _MAX_PER_SECTION:
        lines.append(f"  - and {len(items) - _MAX_PER_SECTION} more")
    return "\n".join(lines)


def _render_jobs_text(items: Sequence[JobItem]) -> str:
    if not items:
        return ""
    lines = ["New jobs:"]
    for j in items[:_MAX_PER_SECTION]:
        age = f" ({j.posted_within_days}d ago)" if j.posted_within_days is not None else ""
        lines.append(f"  - {j.company_name} — {j.role_title}{age}")
    if len(items) > _MAX_PER_SECTION:
        lines.append(f"  - and {len(items) - _MAX_PER_SECTION} more")
    return "\n".join(lines)


def _render_stale_text(items: Sequence[StaleItem]) -> str:
    if not items:
        return ""
    lines = ["Stale applications (silent 14+ days):"]
    for s in items[:_MAX_PER_SECTION]:
        lines.append(f"  - {s.company_name} — {s.role_title} ({s.days_silent}d)")
    if len(items) > _MAX_PER_SECTION:
        lines.append(f"  - and {len(items) - _MAX_PER_SECTION} more")
    return "\n".join(lines)


def _render_wins_text(items: Sequence[WinItem]) -> str:
    if not items:
        return ""
    lines = ["Wins yesterday:"]
    for w in items[:_MAX_PER_SECTION]:
        lines.append(f"  - {w.company_name} — {w.role_title} ({w.kind})")
    if len(items) > _MAX_PER_SECTION:
        lines.append(f"  - and {len(items) - _MAX_PER_SECTION} more")
    return "\n".join(lines)


# ── Section renderers (html) ──────────────────────────────────────────


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def _render_section_html(title: str, lines: Sequence[str]) -> str:
    if not lines:
        return ""
    items = "".join(f"<li>{_esc(line)}</li>" for line in lines)
    return f"<h3>{_esc(title)}</h3><ul>{items}</ul>"


def _beat_lines(items: Sequence[BeatItem]) -> list[str]:
    out: list[str] = []
    for b in items[:_MAX_PER_SECTION]:
        label = _TEMPLATE_LABEL.get(b.template_key, b.template_key)
        out.append(f"{b.company_name} — {b.role_title} ({label})")
    if len(items) > _MAX_PER_SECTION:
        out.append(f"and {len(items) - _MAX_PER_SECTION} more")
    return out


def _ready_lines(items: Sequence[ReadyItem]) -> list[str]:
    out: list[str] = []
    for item in items[:_MAX_PER_SECTION]:
        out.append(f"{item.company_name} — {item.role_title}")
    if len(items) > _MAX_PER_SECTION:
        out.append(f"and {len(items) - _MAX_PER_SECTION} more")
    return out


def _job_lines(items: Sequence[JobItem]) -> list[str]:
    out: list[str] = []
    for j in items[:_MAX_PER_SECTION]:
        age = f" ({j.posted_within_days}d ago)" if j.posted_within_days is not None else ""
        out.append(f"{j.company_name} — {j.role_title}{age}")
    if len(items) > _MAX_PER_SECTION:
        out.append(f"and {len(items) - _MAX_PER_SECTION} more")
    return out


def _stale_lines(items: Sequence[StaleItem]) -> list[str]:
    out: list[str] = []
    for s in items[:_MAX_PER_SECTION]:
        out.append(f"{s.company_name} — {s.role_title} ({s.days_silent}d)")
    if len(items) > _MAX_PER_SECTION:
        out.append(f"and {len(items) - _MAX_PER_SECTION} more")
    return out


def _win_lines(items: Sequence[WinItem]) -> list[str]:
    out: list[str] = []
    for w in items[:_MAX_PER_SECTION]:
        out.append(f"{w.company_name} — {w.role_title} ({w.kind})")
    if len(items) > _MAX_PER_SECTION:
        out.append(f"and {len(items) - _MAX_PER_SECTION} more")
    return out


# ── Nudge ─────────────────────────────────────────────────────────────


def _pick_nudge(inputs: MorningBriefInputs, counts: Mapping[str, int]) -> Optional[str]:
    """Pick at most ONE concrete nudge.  Highest-priority signal wins."""
    if counts["beats"]:
        return f"Send the first follow-up before lunch — it gets the highest reply rate."
    if counts["ready"]:
        return "Review the ready drafts before you open new tabs — they are already close to sendable."
    if counts["stale"]:
        oldest = max(inputs.stale_applications, key=lambda s: s.days_silent)
        return (
            f"Decide on {oldest.company_name} — {oldest.days_silent} days silent. "
            f"A short cold-reopen or a clean withdraw both unblock you."
        )
    if counts["jobs"]:
        return "Triage the new jobs while context is fresh; bookmark or skip."
    if counts["wins"]:
        return "Reply within the day — momentum compounds."
    return None


# ── Composer ──────────────────────────────────────────────────────────


def compose_morning_brief(inputs: MorningBriefInputs) -> MorningBrief:
    """Compose the daily brief.  Pure function.

    Same inputs → identical output (subject, bodies, counts, nudge).
    Does not mutate ``inputs`` or any of its sequences.
    """
    counts = {
        "ready": len(inputs.ready_to_apply),
        "beats": len(inputs.beats_today),
        "jobs":  len(inputs.new_jobs),
        "stale": len(inputs.stale_applications),
        "wins":  len(inputs.wins_yesterday),
    }

    nudge = _pick_nudge(inputs, counts)

    # ── Plain text body ──
    text_sections: list[str] = []
    greeting = f"Morning, {inputs.user_first_name}."
    text_sections.append(greeting)
    for renderer, items in (
        (_render_ready_text, inputs.ready_to_apply),
        (_render_wins_text,  inputs.wins_yesterday),
        (_render_beats_text, inputs.beats_today),
        (_render_jobs_text,  inputs.new_jobs),
        (_render_stale_text, inputs.stale_applications),
    ):
        chunk = renderer(items)
        if chunk:
            text_sections.append(chunk)
    if nudge:
        text_sections.append(f"Today: {nudge}")
    body_text = "\n\n".join(text_sections)

    # ── HTML body ──
    html_parts: list[str] = [f"<p>{_esc(greeting)}</p>"]
    for title, lines in (
        ("Ready to apply",                      _ready_lines(inputs.ready_to_apply)),
        ("Wins yesterday",                       _win_lines(inputs.wins_yesterday)),
        ("Today's follow-ups",                   _beat_lines(inputs.beats_today)),
        ("New jobs",                             _job_lines(inputs.new_jobs)),
        ("Stale applications (silent 14+ days)", _stale_lines(inputs.stale_applications)),
    ):
        html_parts.append(_render_section_html(title, lines))
    if nudge:
        html_parts.append(f"<p><strong>Today:</strong> {_esc(nudge)}</p>")
    body_html = "".join(p for p in html_parts if p)

    subject = _build_subject(inputs, counts)

    return MorningBrief(
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        section_counts=counts,
        nudge=nudge,
    )


__all__ = [
    "BeatItem",
    "ReadyItem",
    "JobItem",
    "StaleItem",
    "WinItem",
    "MorningBriefInputs",
    "MorningBrief",
    "compose_morning_brief",
]
