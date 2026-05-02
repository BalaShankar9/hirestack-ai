"""Tests for backend/app/models/application_status.py.

Covers:
- Canonical enum membership + DB-allowed set parity
- Alias normalization (English + Spanish)
- Analytics bucketing (legacy → new vocab collapse)
- Open / engaged / terminal partition correctness
- is_valid_status validation
"""

from __future__ import annotations

import pytest

from app.models.application_status import (
    ALLOWED_STATUSES,
    ANALYTICS_BUCKETS,
    ENGAGED_STATUSES,
    OPEN_STATUSES,
    STATUS_ALIASES,
    TERMINAL_STATUSES,
    ApplicationStatus,
    canonicalize_for_analytics,
    is_valid_status,
    normalize_status,
)


# Mirrors migration 20260503000000_application_status_taxonomy.sql.
DB_CHECK_VALUES: frozenset[str] = frozenset({
    "draft",
    "active",
    "submitted",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
    "archived",
    "responded",
    "discarded",
    "skip",
})


class TestEnumParity:
    def test_allowed_statuses_match_db_check_constraint(self) -> None:
        assert ALLOWED_STATUSES == DB_CHECK_VALUES, (
            "ApplicationStatus enum and migration CHECK constraint diverged. "
            "Update both together."
        )

    def test_every_enum_value_is_lowercase(self) -> None:
        for s in ApplicationStatus:
            assert s.value == s.value.lower()


class TestNormalize:
    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("applied", "submitted"),
            ("APPLIED", "submitted"),
            ("  Applied ", "submitted"),
            ("aplicado", "submitted"),
            ("aplicada", "submitted"),
            ("sent", "submitted"),
            ("respondido", "responded"),
            ("evaluated", "active"),
            ("evaluada", "active"),
            ("descartado", "discarded"),
            ("rechazado", "rejected"),
            ("rechazada", "rejected"),
            ("entrevista", "interview"),
            ("oferta", "offer"),
        ],
    )
    def test_aliases_resolve(self, alias: str, expected: str) -> None:
        assert normalize_status(alias) == expected

    @pytest.mark.parametrize("canonical", sorted(DB_CHECK_VALUES))
    def test_canonical_values_pass_through(self, canonical: str) -> None:
        assert normalize_status(canonical) == canonical

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_returns_none(self, empty: str | None) -> None:
        assert normalize_status(empty) is None


class TestIsValid:
    @pytest.mark.parametrize("v", sorted(DB_CHECK_VALUES))
    def test_canonical_valid(self, v: str) -> None:
        assert is_valid_status(v) is True

    @pytest.mark.parametrize("v", ["applied", "sent", "respondido"])
    def test_aliases_valid(self, v: str) -> None:
        assert is_valid_status(v) is True

    @pytest.mark.parametrize("v", [None, "", "garbage", "deleted", "ghosted"])
    def test_invalid(self, v: str | None) -> None:
        assert is_valid_status(v) is False


class TestAnalyticsBucketing:
    def test_every_canonical_status_has_bucket(self) -> None:
        missing = ALLOWED_STATUSES - set(ANALYTICS_BUCKETS.keys())
        assert not missing, f"Missing analytics bucket for: {missing}"

    def test_withdrawn_collapses_to_discarded(self) -> None:
        assert canonicalize_for_analytics("withdrawn") == "discarded"

    def test_submitted_collapses_to_applied(self) -> None:
        assert canonicalize_for_analytics("submitted") == "applied"

    def test_aliases_canonicalize(self) -> None:
        assert canonicalize_for_analytics("aplicado") == "applied"
        assert canonicalize_for_analytics("evaluated") == "active"

    def test_none_returns_none(self) -> None:
        assert canonicalize_for_analytics(None) is None
        assert canonicalize_for_analytics("") is None


class TestPartitions:
    def test_open_engaged_terminal_disjoint_or_overlap_intentional(self) -> None:
        # Engaged is a strict subset of Open.
        assert ENGAGED_STATUSES.issubset(OPEN_STATUSES)
        # Terminal does not overlap Open.
        assert OPEN_STATUSES.isdisjoint(TERMINAL_STATUSES)

    def test_every_canonical_status_classified(self) -> None:
        # draft + active are open-but-not-engaged. Everything else
        # must be in one of the three sets.
        classified = OPEN_STATUSES | TERMINAL_STATUSES
        assert ALLOWED_STATUSES == classified, (
            f"Unclassified statuses: {ALLOWED_STATUSES - classified}"
        )


class TestAliasMapIntegrity:
    def test_every_alias_target_is_canonical(self) -> None:
        for alias, target in STATUS_ALIASES.items():
            assert target in ALLOWED_STATUSES, (
                f"Alias {alias!r} → {target!r} but {target!r} is not canonical"
            )

    def test_no_alias_shadows_canonical(self) -> None:
        shadowed = set(STATUS_ALIASES.keys()) & ALLOWED_STATUSES
        assert not shadowed, (
            f"Aliases shadow canonical values: {shadowed}"
        )
