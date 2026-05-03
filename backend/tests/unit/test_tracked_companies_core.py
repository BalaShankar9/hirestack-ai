"""Unit tests for ``app.services.tracked_companies_core``.

These pin the validation/normalization rules that mirror the DB CHECK
constraints from
``supabase/migrations/20260507000000_tracked_companies.sql``. Pure-fn,
no fixtures, no DB.
"""

from __future__ import annotations

import pytest

from app.services.portal_scanner import PROVIDERS, TrackedCompany
from app.services.tracked_companies_core import (
    TrackedCompanyInput,
    ValidationError,
    build_tracked_company,
    normalize_slug,
    normalize_workday_tenant,
    validate_provider,
)


# ── validate_provider ────────────────────────────────────────────────


class TestValidateProvider:
    @pytest.mark.parametrize("p", PROVIDERS)
    def test_accepts_each_known_provider(self, p: str) -> None:
        assert validate_provider(p) == p

    def test_lowercases_input(self) -> None:
        assert validate_provider("GreenHouse") == "greenhouse"

    def test_strips_whitespace(self) -> None:
        assert validate_provider("  lever  ") == "lever"

    def test_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_provider("bamboohr")
        assert exc.value.field == "provider"

    def test_rejects_non_string(self) -> None:
        with pytest.raises(ValidationError):
            validate_provider(7)  # type: ignore[arg-type]

    def test_locked_to_portal_scanner_PROVIDERS(self) -> None:
        # If portal_scanner adds a parser, this test will pass for the
        # new value automatically — they cross-import. The test exists
        # to make that intent explicit.
        for p in PROVIDERS:
            assert validate_provider(p) == p


# ── normalize_slug ───────────────────────────────────────────────────


class TestNormalizeSlug:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("stripe", "stripe"),
            ("Acme-Corp", "acme-corp"),
            ("  github  ", "github"),
            ("a", "a"),  # one char OK
            ("a" * 80, "a" * 80),  # max length OK
            ("a-b-c-d", "a-b-c-d"),
        ],
    )
    def test_accepts_valid(self, raw: str, expected: str) -> None:
        assert normalize_slug(raw) == expected

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "-leading",
            "trailing-",
            "has_underscore",
            "has space",
            "has/slash",
            "a" * 81,  # over cap
            "café",  # non-ascii
        ],
    )
    def test_rejects_invalid(self, bad: str) -> None:
        with pytest.raises(ValidationError) as exc:
            normalize_slug(bad)
        assert exc.value.field == "company_slug"

    def test_rejects_non_string(self) -> None:
        with pytest.raises(ValidationError):
            normalize_slug(None)  # type: ignore[arg-type]


# ── normalize_workday_tenant ─────────────────────────────────────────


class TestNormalizeWorkdayTenant:
    def test_workday_requires_tenant(self) -> None:
        with pytest.raises(ValidationError) as exc:
            normalize_workday_tenant("workday", None)
        assert exc.value.field == "workday_tenant"

    def test_workday_rejects_blank(self) -> None:
        with pytest.raises(ValidationError):
            normalize_workday_tenant("workday", "   ")

    def test_workday_accepts_valid_tenant(self) -> None:
        assert (
            normalize_workday_tenant("workday", "acme.wd5")
            == "acme.wd5"
        )

    def test_workday_lowercases_and_strips(self) -> None:
        assert (
            normalize_workday_tenant("workday", "  Acme.WD5  ")
            == "acme.wd5"
        )

    def test_workday_rejects_no_dot(self) -> None:
        with pytest.raises(ValidationError):
            normalize_workday_tenant("workday", "acmewd5")

    def test_workday_rejects_bad_chars(self) -> None:
        with pytest.raises(ValidationError):
            normalize_workday_tenant("workday", "acme_corp.wd5")

    @pytest.mark.parametrize(
        "p", [p for p in PROVIDERS if p != "workday"]
    )
    def test_non_workday_must_be_null(self, p: str) -> None:
        # Mirrors the DB CHECK: workday_tenant must be NULL for
        # non-workday rows.
        with pytest.raises(ValidationError) as exc:
            normalize_workday_tenant(p, "anything.x")  # type: ignore[arg-type]
        assert exc.value.field == "workday_tenant"

    @pytest.mark.parametrize(
        "p", [p for p in PROVIDERS if p != "workday"]
    )
    def test_non_workday_accepts_none(self, p: str) -> None:
        assert normalize_workday_tenant(p, None) is None  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "p", [p for p in PROVIDERS if p != "workday"]
    )
    def test_non_workday_coerces_blank_to_none(self, p: str) -> None:
        # A friendlier API: empty string from a form is treated as
        # "user didn't fill it in" rather than a CHECK violation.
        assert normalize_workday_tenant(p, "   ") is None  # type: ignore[arg-type]


# ── build_tracked_company end-to-end ─────────────────────────────────


class TestBuildTrackedCompany:
    def test_happy_path_greenhouse(self) -> None:
        company, row = build_tracked_company(
            TrackedCompanyInput(
                provider="greenhouse",
                company_slug="stripe",
                display_name="Stripe",
            )
        )
        assert isinstance(company, TrackedCompany)
        assert company.provider == "greenhouse"
        assert company.company_slug == "stripe"
        assert company.workday_tenant is None
        assert row == {
            "provider": "greenhouse",
            "company_slug": "stripe",
            "workday_tenant": None,
            "display_name": "Stripe",
            "careers_url": None,
        }

    def test_happy_path_workday(self) -> None:
        company, row = build_tracked_company(
            TrackedCompanyInput(
                provider="workday",
                company_slug="acme",
                display_name="Acme Inc.",
                workday_tenant="acme.wd5",
                careers_url="https://acme.wd5.myworkdayjobs.com/careers",
            )
        )
        assert company.workday_tenant == "acme.wd5"
        assert row["careers_url"] == (
            "https://acme.wd5.myworkdayjobs.com/careers"
        )

    def test_normalizes_inputs(self) -> None:
        company, row = build_tracked_company(
            TrackedCompanyInput(
                provider="GREENHOUSE",
                company_slug="  Acme-Corp  ",
                display_name="  Acme   Corp  ",
            )
        )
        assert company.provider == "greenhouse"
        assert company.company_slug == "acme-corp"
        assert row["display_name"] == "Acme Corp"  # whitespace collapsed

    def test_row_excludes_db_managed_columns(self) -> None:
        # The route adds id/user_id/org_id/created_at/updated_at — the
        # core layer must not return them so a typo can't shadow the
        # caller's value.
        _, row = build_tracked_company(
            TrackedCompanyInput(
                provider="lever",
                company_slug="github",
                display_name="GitHub",
            )
        )
        for forbidden in (
            "id",
            "user_id",
            "org_id",
            "created_at",
            "updated_at",
        ):
            assert forbidden not in row

    def test_rejects_blank_display_name(self) -> None:
        with pytest.raises(ValidationError) as exc:
            build_tracked_company(
                TrackedCompanyInput(
                    provider="lever",
                    company_slug="github",
                    display_name="   ",
                )
            )
        assert exc.value.field == "display_name"

    def test_rejects_oversized_display_name(self) -> None:
        with pytest.raises(ValidationError):
            build_tracked_company(
                TrackedCompanyInput(
                    provider="lever",
                    company_slug="github",
                    display_name="x" * 201,
                )
            )

    def test_rejects_careers_url_without_scheme(self) -> None:
        with pytest.raises(ValidationError) as exc:
            build_tracked_company(
                TrackedCompanyInput(
                    provider="lever",
                    company_slug="github",
                    display_name="GitHub",
                    careers_url="github.com/careers",
                )
            )
        assert exc.value.field == "careers_url"

    def test_rejects_oversized_careers_url(self) -> None:
        with pytest.raises(ValidationError):
            build_tracked_company(
                TrackedCompanyInput(
                    provider="lever",
                    company_slug="github",
                    display_name="GitHub",
                    careers_url="https://" + ("a" * 2050),
                )
            )

    def test_blank_careers_url_becomes_none(self) -> None:
        _, row = build_tracked_company(
            TrackedCompanyInput(
                provider="lever",
                company_slug="github",
                display_name="GitHub",
                careers_url="   ",
            )
        )
        assert row["careers_url"] is None

    def test_workday_without_tenant_raises(self) -> None:
        # Mirrors DB conditional CHECK end-to-end through the builder.
        with pytest.raises(ValidationError) as exc:
            build_tracked_company(
                TrackedCompanyInput(
                    provider="workday",
                    company_slug="acme",
                    display_name="Acme",
                )
            )
        assert exc.value.field == "workday_tenant"

    def test_non_workday_with_tenant_raises(self) -> None:
        # Mirrors DB conditional CHECK end-to-end through the builder.
        with pytest.raises(ValidationError) as exc:
            build_tracked_company(
                TrackedCompanyInput(
                    provider="lever",
                    company_slug="github",
                    display_name="GitHub",
                    workday_tenant="github.wd5",
                )
            )
        assert exc.value.field == "workday_tenant"

    def test_unknown_provider_raises_first(self) -> None:
        # Provider validates before slug, so the error surfaces the
        # most-actionable field first.
        with pytest.raises(ValidationError) as exc:
            build_tracked_company(
                TrackedCompanyInput(
                    provider="bamboohr",
                    company_slug="!!!invalid!!!",
                    display_name="",
                )
            )
        assert exc.value.field == "provider"

    def test_dataclass_is_hashable_and_frozen(self) -> None:
        # Worker plan_fetches takes Sequence[TrackedCompany] and uses
        # them in sets/dicts when deduplicating. Catching a regression
        # to mutable dataclass here saves a confusing worker bug.
        company, _ = build_tracked_company(
            TrackedCompanyInput(
                provider="lever",
                company_slug="github",
                display_name="GitHub",
            )
        )
        assert hash(company)  # raises if not hashable
        with pytest.raises((AttributeError, Exception)):
            company.company_slug = "changed"  # type: ignore[misc]
