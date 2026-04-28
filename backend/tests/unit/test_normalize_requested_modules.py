"""S4-F1 — Pin `_normalize_requested_modules` invariants.

The frontend posts module keys in camelCase (`coverLetter`,
`personalStatement`); internal Python helpers and DB rows often
spell them in snake_case (`cover_letter`). The `_jobs` endpoint
accepts either. The normalizer is the boundary that turns either
shape into the canonical camelCase set the runtime understands.

A drift here is the silent bug factory: a fresh job request with
`["cover_letter"]` would pass through, miss `_DEFAULT_REQUESTED_MODULES`
membership, get filtered out, and the job would generate nothing
visible in the cover-letter slot.
"""
from __future__ import annotations

from app.api.routes.generate.jobs import (
    _DEFAULT_REQUESTED_MODULES,
    _normalize_requested_modules,
)


def test_returns_full_default_when_input_is_empty() -> None:
    assert _normalize_requested_modules([]) == list(_DEFAULT_REQUESTED_MODULES)


def test_returns_full_default_when_input_is_none() -> None:
    assert _normalize_requested_modules(None) == list(_DEFAULT_REQUESTED_MODULES)


def test_returns_full_default_when_all_inputs_are_unknown() -> None:
    """Empty filtered output must fall back to the default set, never
    return [] — an empty requested-modules list at the runtime layer
    means "generate everything" downstream and that is the safer
    fallback than "generate nothing"."""
    assert _normalize_requested_modules(["bogus", "ghost"]) == list(_DEFAULT_REQUESTED_MODULES)


def test_snake_case_inputs_are_mapped_to_camel_case() -> None:
    out = _normalize_requested_modules(["cover_letter", "personal_statement", "learning_plan"])
    assert out == ["coverLetter", "personalStatement", "learningPlan"]


def test_camel_case_inputs_pass_through_unchanged() -> None:
    out = _normalize_requested_modules(["coverLetter", "personalStatement", "learningPlan"])
    assert out == ["coverLetter", "personalStatement", "learningPlan"]


def test_identity_keys_pass_through_unchanged() -> None:
    """Keys that are spelled the same in both shapes must stay put
    (benchmark, cv, resume, portfolio, scorecard, gaps)."""
    keys = ["benchmark", "cv", "resume", "portfolio", "scorecard", "gaps"]
    assert _normalize_requested_modules(keys) == keys


def test_gap_analysis_snake_normalizes_to_gaps() -> None:
    """`gap_analysis` (DB-friendly snake) must collapse to `gaps`
    (frontend / canonical), not duplicate."""
    out = _normalize_requested_modules(["gap_analysis", "gaps"])
    assert out == ["gaps"]


def test_dedups_repeated_inputs_preserving_first_occurrence() -> None:
    out = _normalize_requested_modules(
        ["cv", "cover_letter", "cv", "coverLetter", "cv"]
    )
    assert out == ["cv", "coverLetter"]


def test_unknown_keys_are_silently_dropped_alongside_known() -> None:
    """Mix of valid + bogus must yield only the valid subset, NOT
    fall back to default — the caller asked for something specific."""
    out = _normalize_requested_modules(["cv", "bogus", "coverLetter"])
    assert out == ["cv", "coverLetter"]


def test_preserves_caller_ordering() -> None:
    """Order matters because the runtime walks the list to schedule
    module-progress updates; reordering shifts which module shows
    activity first in the UI."""
    out = _normalize_requested_modules(["portfolio", "cv", "coverLetter"])
    assert out == ["portfolio", "cv", "coverLetter"]
