"""Pure-fn validation/normalization for tracked_companies inputs.

Mirrors the DB CHECK constraints in
``supabase/migrations/20260507000000_tracked_companies.sql`` so the API
layer rejects bad input before it reaches Postgres. The DB constraints
remain the source-of-truth — this layer is a friendlier first line.

NO I/O, NO DB calls, NO httpx. Pure functions only so the CRUD route
can compose them into a fast-path validator without test fixtures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.services.portal_scanner import PROVIDERS, Provider, TrackedCompany

# Keep the module re-exporting PROVIDERS so callers don't need two imports.
__all__ = [
    "PROVIDERS",
    "TrackedCompanyInput",
    "ValidationError",
    "normalize_slug",
    "normalize_workday_tenant",
    "validate_provider",
    "build_tracked_company",
]


# Slugs from real ATS portals are URL path segments — alnum + hyphen,
# lowercase. We DO NOT allow underscores (no provider uses them in the
# canonical company segment), nor leading/trailing hyphens. Length cap
# 80 covers every observed real slug with headroom; rejects log-bombs.
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")

# Workday tenants look like ``acme.wd5`` — alnum + dot + hyphen,
# lowercase. ``.`` is required by Workday's URL scheme, so we don't
# accept bare ``acme``. Length cap 64 — Workday's own tenant ids are
# well under this.
_WORKDAY_TENANT_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$"
)


class ValidationError(ValueError):
    """Raised when an input fails a pure-fn validation rule.

    The route layer maps this to HTTP 422 so callers see exactly which
    field tripped which rule.
    """

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


@dataclass(frozen=True)
class TrackedCompanyInput:
    """Raw input shape from the API request body.

    Mirrors the route's Pydantic model but kept dataclass-pure so this
    module has zero Pydantic dependency (and so unit tests don't need
    the FastAPI app context).
    """

    provider: str
    company_slug: str
    display_name: str
    workday_tenant: Optional[str] = None
    careers_url: Optional[str] = None


def validate_provider(value: str) -> Provider:
    """Coerce ``value`` to a known ``Provider`` literal or raise.

    Lowercases first so the API is forgiving of case (the DB CHECK
    requires exact lowercase). Cross-imports ``PROVIDERS`` from
    ``portal_scanner`` so this list cannot drift from the parser set.
    """
    if not isinstance(value, str):
        raise ValidationError("provider", "must be a string")
    lowered = value.strip().lower()
    if lowered not in PROVIDERS:
        raise ValidationError(
            "provider",
            f"must be one of {sorted(PROVIDERS)}",
        )
    # mypy: Literal narrowing
    return lowered  # type: ignore[return-value]


def normalize_slug(value: str) -> str:
    """Lowercase + strip whitespace + validate a company slug.

    Rejects empty, oversized, or non-canonical slugs. We do NOT
    auto-strip e.g. trailing slashes — callers should pass the bare
    ``stripe`` / ``acme-corp`` segment. Better to error loudly than
    silently rewrite somebody's typo into a valid-looking row.
    """
    if not isinstance(value, str):
        raise ValidationError("company_slug", "must be a string")
    candidate = value.strip().lower()
    if not candidate:
        raise ValidationError("company_slug", "must not be empty")
    if not _SLUG_RE.match(candidate):
        raise ValidationError(
            "company_slug",
            "must be lowercase alnum + hyphen, 1-80 chars, "
            "no leading/trailing hyphen",
        )
    return candidate


def normalize_workday_tenant(
    provider: Provider, value: Optional[str]
) -> Optional[str]:
    """Apply the workday-tenant-required-iff-workday rule.

    Mirrors the DB conditional CHECK. For non-workday rows we accept
    None or coerce empty/whitespace to None (a friendlier API). For
    workday rows we require a syntactically valid tenant.
    """
    cleaned: Optional[str] = None
    if isinstance(value, str):
        stripped = value.strip().lower()
        cleaned = stripped or None

    if provider == "workday":
        if cleaned is None:
            raise ValidationError(
                "workday_tenant",
                "is required when provider='workday'",
            )
        if not _WORKDAY_TENANT_RE.match(cleaned):
            raise ValidationError(
                "workday_tenant",
                "must look like 'acme.wd5' (alnum/hyphen segments "
                "joined by a dot, lowercase)",
            )
        return cleaned

    if cleaned is not None:
        raise ValidationError(
            "workday_tenant",
            "must be null when provider is not 'workday'",
        )
    return None


def _normalize_display_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("display_name", "must be a string")
    candidate = " ".join(value.split())  # collapse whitespace
    if not candidate:
        raise ValidationError("display_name", "must not be empty")
    if len(candidate) > 200:
        raise ValidationError("display_name", "must be ≤ 200 chars")
    return candidate


def _normalize_careers_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("careers_url", "must be a string or null")
    candidate = value.strip()
    if not candidate:
        return None
    # Cheap structural check; route may add httpx-side HEAD probe later.
    if not (candidate.startswith("http://") or candidate.startswith("https://")):
        raise ValidationError(
            "careers_url",
            "must start with http:// or https://",
        )
    if len(candidate) > 2048:
        raise ValidationError("careers_url", "must be ≤ 2048 chars")
    return candidate


def build_tracked_company(
    raw: TrackedCompanyInput,
) -> tuple[TrackedCompany, dict[str, object]]:
    """Validate + normalize ``raw`` into the worker dataclass + DB row.

    Returns a tuple of:
      * ``TrackedCompany`` — the dataclass the worker consumes from
        ``portal_scanner.plan_fetches``.
      * ``dict`` — the column subset the API layer can hand to
        ``db.create("tracked_companies", row)``. Excludes ``id``,
        ``user_id``, ``org_id``, ``created_at``, ``updated_at`` —
        callers add those at insert time.

    Raises ``ValidationError`` on the first rule a field fails.
    """
    provider = validate_provider(raw.provider)
    slug = normalize_slug(raw.company_slug)
    tenant = normalize_workday_tenant(provider, raw.workday_tenant)
    display_name = _normalize_display_name(raw.display_name)
    careers_url = _normalize_careers_url(raw.careers_url)

    company = TrackedCompany(
        provider=provider,
        company_slug=slug,
        workday_tenant=tenant,
    )
    row: dict[str, object] = {
        "provider": provider,
        "company_slug": slug,
        "workday_tenant": tenant,
        "display_name": display_name,
        "careers_url": careers_url,
    }
    return company, row
