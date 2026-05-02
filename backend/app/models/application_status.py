"""
Application status — canonical enum + alias map.

Single source of truth for the values allowed in
``public.applications.status`` after migration
``20260503000000_application_status_taxonomy.sql``.

Vocabulary:
    draft       — local/incomplete; not yet a real application
    active      — application in active workflow (legacy bucket;
                  prefer the more specific values below)
    submitted   — user submitted (legacy ≈ "applied")
    responded   — recruiter replied; no interview yet
                  (career-ops vocab; unblocks 1d/3d cadence rule)
    interview   — interview scheduled or in progress
    offer       — offer extended
    rejected    — company rejected the candidate
    discarded   — user closed for non-rejection reasons
                  (career-ops vocab; distinct from withdrawn)
    skip        — evaluated but never applied (ghost / score<4)
    withdrawn   — legacy alias for discarded (still valid)
    archived    — soft-archived from view (any prior state)

Aliases accepted on writes; canonicalized on read paths that need
analytics-quality vocab (pattern insights, cadence engine).
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping


class ApplicationStatus(str, Enum):
    """Canonical application status values."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUBMITTED = "submitted"
    RESPONDED = "responded"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    DISCARDED = "discarded"
    SKIP = "skip"
    WITHDRAWN = "withdrawn"
    ARCHIVED = "archived"


# All values currently allowed by the DB CHECK constraint.
ALLOWED_STATUSES: frozenset[str] = frozenset(s.value for s in ApplicationStatus)


# Aliases accepted on write; mapped to canonical values on read where
# analytics need normalized vocab. Keep additive — never remove an
# alias without a data migration.
STATUS_ALIASES: Mapping[str, str] = {
    # Career-ops Spanish + English aliases:
    "evaluada": ApplicationStatus.ACTIVE.value,
    "evaluated": ApplicationStatus.ACTIVE.value,
    "aplicado": ApplicationStatus.SUBMITTED.value,
    "aplicada": ApplicationStatus.SUBMITTED.value,
    "applied": ApplicationStatus.SUBMITTED.value,
    "sent": ApplicationStatus.SUBMITTED.value,
    "respondido": ApplicationStatus.RESPONDED.value,
    "entrevista": ApplicationStatus.INTERVIEW.value,
    "oferta": ApplicationStatus.OFFER.value,
    "rechazado": ApplicationStatus.REJECTED.value,
    "rechazada": ApplicationStatus.REJECTED.value,
    "descartado": ApplicationStatus.DISCARDED.value,
    "descartada": ApplicationStatus.DISCARDED.value,
    # Legacy HireStack aliases — soft-mapped to new vocab for analytics.
    # NOTE: writes still accept "withdrawn" (CHECK passes); only analytics
    # views should normalize via canonicalize_for_analytics().
}


# For analytics, group legacy + new values into stable buckets so that
# pattern insights / funnel computations don't double-count.
ANALYTICS_BUCKETS: Mapping[str, str] = {
    ApplicationStatus.DRAFT.value: "draft",
    ApplicationStatus.ACTIVE.value: "active",
    ApplicationStatus.SUBMITTED.value: "applied",
    ApplicationStatus.RESPONDED.value: "responded",
    ApplicationStatus.INTERVIEW.value: "interview",
    ApplicationStatus.OFFER.value: "offer",
    ApplicationStatus.REJECTED.value: "rejected",
    ApplicationStatus.DISCARDED.value: "discarded",
    ApplicationStatus.SKIP.value: "skip",
    # Legacy → analytics bucket
    ApplicationStatus.WITHDRAWN.value: "discarded",
    ApplicationStatus.ARCHIVED.value: "archived",
}


# Statuses that count as "open" in the user's pipeline (not closed-out).
OPEN_STATUSES: frozenset[str] = frozenset({
    ApplicationStatus.DRAFT.value,
    ApplicationStatus.ACTIVE.value,
    ApplicationStatus.SUBMITTED.value,
    ApplicationStatus.RESPONDED.value,
    ApplicationStatus.INTERVIEW.value,
    ApplicationStatus.OFFER.value,
})


# Statuses that indicate the candidate is engaged with the company
# (drives the cadence rules in backend/app/services/cadence.py).
ENGAGED_STATUSES: frozenset[str] = frozenset({
    ApplicationStatus.SUBMITTED.value,
    ApplicationStatus.RESPONDED.value,
    ApplicationStatus.INTERVIEW.value,
    ApplicationStatus.OFFER.value,
})


# Terminal statuses — no further follow-up cadence applies.
TERMINAL_STATUSES: frozenset[str] = frozenset({
    ApplicationStatus.REJECTED.value,
    ApplicationStatus.DISCARDED.value,
    ApplicationStatus.WITHDRAWN.value,
    ApplicationStatus.ARCHIVED.value,
    ApplicationStatus.SKIP.value,
})


def normalize_status(value: str | None) -> str | None:
    """Map alias → canonical; pass through canonical values; ``None`` → ``None``.

    Does NOT validate against ALLOWED_STATUSES — use is_valid_status() for that.
    Lower-cases and strips on the way in.
    """
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    return STATUS_ALIASES.get(cleaned, cleaned)


def is_valid_status(value: str | None) -> bool:
    """True iff the value (or its alias) maps to an allowed canonical status."""
    normalized = normalize_status(value)
    return normalized is not None and normalized in ALLOWED_STATUSES


def canonicalize_for_analytics(value: str | None) -> str | None:
    """Normalize for analytics bucketing (collapses legacy → new vocab)."""
    normalized = normalize_status(value)
    if normalized is None:
        return None
    return ANALYTICS_BUCKETS.get(normalized, normalized)


__all__ = [
    "ApplicationStatus",
    "ALLOWED_STATUSES",
    "STATUS_ALIASES",
    "ANALYTICS_BUCKETS",
    "OPEN_STATUSES",
    "ENGAGED_STATUSES",
    "TERMINAL_STATUSES",
    "normalize_status",
    "is_valid_status",
    "canonicalize_for_analytics",
]
