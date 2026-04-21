"""Regression tests for _persist_application_patch resilience to PGRST204.

Production bug 2026-04-21: a resume_html column was added to the data
model but the matching migration only landed in database/migrations/,
not supabase/migrations/.  Production never got the column, so every
generation job's persistence step blew up with PGRST204 and the user
saw a raw {'code': 'PGRST204', ...} dict in the UI — losing the entire
generated CV/cover letter/benchmark for that run.

These tests pin two things:
  1. When PostgREST reports a missing column, persistence drops that
     column and retries instead of throwing the whole patch away.
  2. The user's other generated content (CV, cover letter, benchmark)
     is preserved.
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from app.api.routes.generate.jobs import _persist_application_patch


class _FakeBuilder:
    """Mimics supabase-py's chained builder API."""

    def __init__(self, fail_on: list[str] | None = None):
        self.fail_on = fail_on or []
        self.calls: list[Dict[str, Any]] = []
        self._pending_patch: Dict[str, Any] = {}

    def table(self, _name: str) -> "_FakeBuilder":
        return self

    def update(self, patch: Dict[str, Any]) -> "_FakeBuilder":
        self._pending_patch = dict(patch)
        return self

    def eq(self, _col: str, _val: str) -> "_FakeBuilder":
        return self

    def execute(self) -> Any:
        # Record what was actually attempted
        self.calls.append(dict(self._pending_patch))
        # Fail if any column in fail_on is in the patch
        for col in self.fail_on:
            if col in self._pending_patch:
                raise Exception(
                    f"{{'code': 'PGRST204', 'details': None, 'hint': None, "
                    f"'message': \"Could not find the '{col}' column of "
                    f"'applications' in the schema cache\"}}"
                )
        return MagicMock(data=[{"id": "app_1"}])


TABLES = {"applications": "applications"}


@pytest.mark.asyncio
async def test_persists_normally_when_no_column_missing():
    sb = _FakeBuilder()
    await _persist_application_patch(sb, TABLES, "app_1", {
        "cv_html": "<p>cv</p>",
        "cover_letter_html": "<p>cl</p>",
    })
    assert len(sb.calls) == 1
    assert sb.calls[0] == {"cv_html": "<p>cv</p>", "cover_letter_html": "<p>cl</p>"}


@pytest.mark.asyncio
async def test_drops_single_missing_column_and_retries():
    sb = _FakeBuilder(fail_on=["resume_html"])
    patch = {
        "cv_html": "<p>cv</p>",
        "cover_letter_html": "<p>cl</p>",
        "resume_html": "<p>resume</p>",
        "benchmark": {"score": 90},
    }
    await _persist_application_patch(sb, TABLES, "app_1", patch)
    # Two attempts: first failed, second succeeded without resume_html
    assert len(sb.calls) == 2
    assert "resume_html" in sb.calls[0]
    assert "resume_html" not in sb.calls[1]
    # Other fields preserved
    assert sb.calls[1]["cv_html"] == "<p>cv</p>"
    assert sb.calls[1]["cover_letter_html"] == "<p>cl</p>"
    assert sb.calls[1]["benchmark"] == {"score": 90}


@pytest.mark.asyncio
async def test_drops_multiple_missing_columns():
    sb = _FakeBuilder(fail_on=["resume_html", "validation"])
    patch = {
        "cv_html": "<p>cv</p>",
        "resume_html": "<p>r</p>",
        "validation": {"ok": True},
    }
    await _persist_application_patch(sb, TABLES, "app_1", patch)
    # Three attempts: original, drop resume_html, drop validation
    assert len(sb.calls) == 3
    assert sb.calls[-1] == {"cv_html": "<p>cv</p>"}


@pytest.mark.asyncio
async def test_no_op_when_patch_empty():
    sb = _FakeBuilder()
    await _persist_application_patch(sb, TABLES, "app_1", {})
    assert len(sb.calls) == 0


@pytest.mark.asyncio
async def test_returns_silently_when_all_columns_dropped():
    """If every column is missing, do not raise — just log and return.

    The user gets a 'modules error' UI but at least the runtime
    finishes cleanly instead of cascading failures.
    """
    sb = _FakeBuilder(fail_on=["resume_html"])
    await _persist_application_patch(sb, TABLES, "app_1", {"resume_html": "x"})
    # First call attempted with the column, second call would have been
    # empty so we early-return.
    assert len(sb.calls) == 1


@pytest.mark.asyncio
async def test_non_pgrst_errors_are_re_raised():
    """Connection errors, RLS denials, etc. must surface — only PGRST204
    triggers the drop-and-retry path."""
    class _ConnErrBuilder(_FakeBuilder):
        def execute(self) -> Any:
            raise Exception("Connection refused")

    sb = _ConnErrBuilder()
    with pytest.raises(Exception, match="Connection refused"):
        await _persist_application_patch(sb, TABLES, "app_1", {"cv_html": "x"})


@pytest.mark.asyncio
async def test_ignores_unknown_column_in_pgrst_message():
    """If PostgREST reports a missing column we never tried to set
    (impossible in practice, but defensive), re-raise rather than loop."""
    class _WeirdBuilder(_FakeBuilder):
        def execute(self) -> Any:
            self.calls.append(dict(self._pending_patch))
            raise Exception(
                "{'code': 'PGRST204', 'message': \"Could not find the "
                "'mystery_column' column of 'applications' in the schema cache\"}"
            )

    sb = _WeirdBuilder()
    with pytest.raises(Exception, match="PGRST204"):
        await _persist_application_patch(sb, TABLES, "app_1", {"cv_html": "x"})
    # Only one attempt — we don't loop forever
    assert len(sb.calls) == 1
