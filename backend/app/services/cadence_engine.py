"""A1 — cadence engine.

PURE-FUNCTION decision logic for follow-up scheduling. No I/O.

Given an application's current state (status, submitted_at,
response_received_at, …) and the existing follow-up history, returns
the NEXT beat that should be persisted into ``application_followups``,
or ``None`` when no further follow-up is appropriate.

Cadence policy (career-ops baseline, deliberately conservative):

  Beat 1  | template='first'       | +1 business day after submitted_at
  Beat 2  | template='linkedin'    | +3 business days after submitted_at
                                     ONLY when contact_linkedin is known
  Beat 3  | template='second'      | +7 business days after submitted_at
                                     ONLY when no response yet
  Beat 4  | template='cold_reopen' | +21 business days after submitted_at
                                     ONLY when status is still
                                     'submitted'/'active' (i.e. silence)

Stop conditions (no more beats produced):
  * status in {'rejected','offer','discarded','withdrawn','archived','skip'}
  * status == 'responded' AND last template was 'second' or later
  * 4 beats already produced

The engine is the single source of truth for WHAT/WHEN; the persister
is responsible for INSERT/UPDATE on the table; the worker is
responsible for generating drafts a few minutes before
``scheduled_for``.  Nothing in this module performs I/O or schedules
work — that separation is what makes the cadence policy
unit-testable in isolation.

HARD RULE referenced by §7.12 of the master plan: this engine NEVER
moves a beat to ``sent``.  It only schedules ``pending`` beats; the
user clicks Send themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Literal, Mapping, Optional

# ── Types ─────────────────────────────────────────────────────────────

TemplateKey = Literal["first", "linkedin", "second", "cold_reopen"]
Channel = Literal["email", "linkedin", "form"]

# Status values that mean "the application is closed; no more cadence".
_TERMINAL_STATUSES: frozenset[str] = frozenset({
    "rejected", "offer", "discarded", "withdrawn", "archived", "skip",
})

# Status values that count as "still in flight, awaiting reply".
_IN_FLIGHT_STATUSES: frozenset[str] = frozenset({
    "submitted", "active",
})

# Template ordering — index = beat number (0-based).
_TEMPLATE_SEQUENCE: tuple[TemplateKey, ...] = (
    "first", "linkedin", "second", "cold_reopen",
)

# Business-day offsets (in calendar days, weekends added on top by
# `_add_business_days`).  These mirror the policy comments above.
_OFFSETS_BUSINESS_DAYS: Mapping[TemplateKey, int] = {
    "first":       1,
    "linkedin":    3,
    "second":      7,
    "cold_reopen": 21,
}

# Default time-of-day for scheduled beats: 09:30 in the user's local
# timezone.  We store as UTC; caller can re-render in TZ for display.
# 09:30 chosen because "morning brief" inserts the day's beats at the
# top of the user's inbox.
_DEFAULT_BEAT_TIME = time(9, 30, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FollowupBeat:
    """The next scheduled follow-up beat for an application.

    Returned by ``next_followup_beat`` and persisted by the caller as
    a row in ``application_followups`` with status='pending'.
    """
    template_key: TemplateKey
    scheduled_for: datetime  # tz-aware UTC
    channel: Channel
    followup_count: int      # 1-based index of THIS beat
    reason: str              # human-readable trigger explanation

    def to_row(
        self,
        *,
        application_id: str,
        user_id: str,
        contact_email: Optional[str] = None,
        contact_linkedin: Optional[str] = None,
        contact_name: Optional[str] = None,
    ) -> dict:
        """Serialize to the column shape of ``application_followups``."""
        return {
            "application_id": application_id,
            "user_id": user_id,
            "scheduled_for": self.scheduled_for.isoformat(),
            "channel": self.channel,
            "template_key": self.template_key,
            "followup_count": self.followup_count,
            "status": "pending",
            "contact_name": contact_name,
            "contact_email": contact_email,
            "contact_linkedin": contact_linkedin,
        }


# ── Internals ─────────────────────────────────────────────────────────


def _add_business_days(start: datetime, days: int) -> datetime:
    """Add N business days (Mon–Fri) to a tz-aware datetime, then
    snap the time-of-day to ``_DEFAULT_BEAT_TIME``.  Saturdays/Sundays
    are skipped — a beat scheduled for "+1 business day" from a
    Friday lands on the following Monday."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if days <= 0:
        candidate = start
    else:
        candidate = start
        added = 0
        while added < days:
            candidate = candidate + timedelta(days=1)
            if candidate.weekday() < 5:  # Mon=0…Fri=4
                added += 1
    # Snap to default beat time (in UTC); preserve the date.
    return candidate.replace(
        hour=_DEFAULT_BEAT_TIME.hour,
        minute=_DEFAULT_BEAT_TIME.minute,
        second=0,
        microsecond=0,
        tzinfo=timezone.utc,
    )


def _coerce_dt(value) -> Optional[datetime]:
    """Accept datetime / ISO-string / None and return a tz-aware UTC
    datetime (or None)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            # fromisoformat handles "...+00:00" and naive strings;
            # Python 3.11+ also accepts trailing "Z".
            cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
            dt = datetime.fromisoformat(cleaned)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _last_template(history: Iterable[Mapping]) -> Optional[TemplateKey]:
    """Return the template_key of the most-recent beat in history,
    ignoring 'dismissed' / 'expired' entries."""
    last: Optional[TemplateKey] = None
    last_index = -1
    for h in history or []:
        tpl = h.get("template_key") if isinstance(h, Mapping) else None
        if tpl not in _TEMPLATE_SEQUENCE:
            continue
        status = (h.get("status") if isinstance(h, Mapping) else "") or ""
        if status in {"dismissed", "expired"}:
            continue
        idx = _TEMPLATE_SEQUENCE.index(tpl)  # type: ignore[arg-type]
        if idx > last_index:
            last_index = idx
            last = tpl  # type: ignore[assignment]
    return last


def _next_template(last: Optional[TemplateKey]) -> Optional[TemplateKey]:
    if last is None:
        return _TEMPLATE_SEQUENCE[0]
    try:
        i = _TEMPLATE_SEQUENCE.index(last)
    except ValueError:
        return _TEMPLATE_SEQUENCE[0]
    if i + 1 >= len(_TEMPLATE_SEQUENCE):
        return None
    return _TEMPLATE_SEQUENCE[i + 1]


# ── Public API ────────────────────────────────────────────────────────


def next_followup_beat(
    application: Mapping,
    *,
    history: Optional[Iterable[Mapping]] = None,
    now: Optional[datetime] = None,
) -> Optional[FollowupBeat]:
    """Compute the next follow-up beat for an application, or None
    when no further cadence is appropriate.

    Args:
        application: dict-shaped row from ``applications``. Must
            contain at minimum ``status`` and ``submitted_at``;
            optional ``response_received_at``, ``contact_linkedin``.
        history:    iterable of existing follow-up rows (may be empty).
        now:        injected for testability; defaults to wall-clock UTC.

    Returns:
        FollowupBeat or None.
    """
    if not isinstance(application, Mapping):
        return None

    status = (application.get("status") or "").lower().strip()
    if status in _TERMINAL_STATUSES:
        return None

    submitted_at = _coerce_dt(application.get("submitted_at"))
    if submitted_at is None:
        # No anchor → cadence cannot start. The engine deliberately
        # refuses to schedule from a draft application.
        return None

    response_at = _coerce_dt(application.get("response_received_at"))

    history_list = list(history or [])
    # Bound: at most 4 beats per application.
    active_count = sum(
        1 for h in history_list
        if isinstance(h, Mapping)
        and (h.get("status") or "") not in {"dismissed", "expired"}
        and h.get("template_key") in _TEMPLATE_SEQUENCE
    )
    if active_count >= len(_TEMPLATE_SEQUENCE):
        return None

    last_tpl = _last_template(history_list)
    next_tpl = _next_template(last_tpl)
    if next_tpl is None:
        return None

    # Skip 'linkedin' beat when no LinkedIn contact is known.
    if next_tpl == "linkedin" and not (application.get("contact_linkedin") or "").strip():
        next_tpl = _next_template("linkedin")  # → 'second'
        if next_tpl is None:
            return None

    # 'second' and 'cold_reopen' only fire when no response yet.
    if next_tpl in ("second", "cold_reopen") and response_at is not None:
        # Recruiter replied; skip silence-breaker beats. If status
        # advanced to interview/offer/etc. the terminal-status check
        # above already returned. If status == 'responded' we DO NOT
        # send a "still no reply" follow-up.
        return None

    offset = _OFFSETS_BUSINESS_DAYS[next_tpl]
    scheduled = _add_business_days(submitted_at, offset)

    # If the engine is invoked late and the computed time is already
    # in the past, snap to "next business day at 09:30 UTC" so the
    # worker doesn't try to back-date a draft.
    now_utc = now or datetime.now(timezone.utc)
    if scheduled < now_utc:
        scheduled = _add_business_days(now_utc, 1)

    channel: Channel = "linkedin" if next_tpl == "linkedin" else "email"

    reason_map = {
        "first":       "+1 business day after submission — first nudge",
        "linkedin":    "+3 business days after submission — LinkedIn touch",
        "second":      "+7 business days, still no response — second email",
        "cold_reopen": "+21 business days, role likely cold — gentle reopen",
    }

    return FollowupBeat(
        template_key=next_tpl,
        scheduled_for=scheduled,
        channel=channel,
        followup_count=active_count + 1,
        reason=reason_map[next_tpl],
    )


def beats_due(
    rows: Iterable[Mapping],
    *,
    now: Optional[datetime] = None,
) -> list[Mapping]:
    """Filter a batch of pending follow-up rows down to those whose
    ``scheduled_for`` <= now.  Used by the 15-min poll worker.

    Pure function — caller is responsible for the SQL query that
    fetched the candidate rows; this filter is the in-memory backstop
    that ensures we never wake a beat early due to clock skew or
    eager prefetching.
    """
    now_utc = now or datetime.now(timezone.utc)
    out: list[Mapping] = []
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        if (row.get("status") or "") != "pending":
            continue
        sched = _coerce_dt(row.get("scheduled_for"))
        if sched is None:
            continue
        if sched <= now_utc:
            out.append(row)
    return out
