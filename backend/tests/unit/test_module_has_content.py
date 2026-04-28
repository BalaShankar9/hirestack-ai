"""S4-F2 — Pin `_module_has_content` per-slot column mapping.

`_module_has_content(application_row, module_key)` decides whether
a given module slot is "already filled" — used by the retry endpoint
to skip modules that already have content. The mapping from module
key to which `applications.*` column to read is per-slot bespoke
(`cv` reads `cv_html`, `gaps` reads `gaps`, `learningPlan` reads the
snake-cased `learning_plan`, etc.). A wrong mapping means either:

  * **silent skip** — module looks "ready" because the wrong column
    has content, retry is a no-op, user sees the missing module.
  * **redundant generation** — module looks "empty" because the
    wrong column was checked, even though the right one had content.

These tests pin the per-slot mapping so a future contributor can't
accidentally point `cv` at `cover_letter_html`.
"""
from __future__ import annotations

import pytest

from app.api.routes.generate.jobs import _module_has_content


@pytest.mark.parametrize(
    "module_key, populated_column",
    [
        ("benchmark", "benchmark"),
        ("gaps", "gaps"),
        ("learningPlan", "learning_plan"),
        ("cv", "cv_html"),
        ("resume", "resume_html"),
        ("coverLetter", "cover_letter_html"),
        ("personalStatement", "personal_statement_html"),
        ("portfolio", "portfolio_html"),
    ],
)
def test_module_reports_content_when_its_column_is_populated(
    module_key: str, populated_column: str
) -> None:
    """Each module key reads from exactly its declared column."""
    row = {populated_column: "non-empty"}
    if "_html" in populated_column:
        row[populated_column] = "<p>ok</p>"
    assert _module_has_content(row, module_key) is True


@pytest.mark.parametrize(
    "module_key",
    ["benchmark", "gaps", "learningPlan", "cv", "resume",
     "coverLetter", "personalStatement", "portfolio"],
)
def test_module_reports_empty_when_no_columns_present(module_key: str) -> None:
    assert _module_has_content({}, module_key) is False


@pytest.mark.parametrize("module_key", ["cv", "resume", "coverLetter", "personalStatement", "portfolio"])
def test_html_modules_reject_whitespace_only(module_key: str) -> None:
    """An HTML column carrying only whitespace must be treated as empty —
    otherwise the retry endpoint skips re-generating real-empty modules."""
    column = {
        "cv": "cv_html",
        "resume": "resume_html",
        "coverLetter": "cover_letter_html",
        "personalStatement": "personal_statement_html",
        "portfolio": "portfolio_html",
    }[module_key]
    assert _module_has_content({column: "   \n  \t "}, module_key) is False
    assert _module_has_content({column: ""}, module_key) is False
    assert _module_has_content({column: None}, module_key) is False


def test_scorecard_reads_either_scorecard_or_scores() -> None:
    """scorecard accepts content from either the canonical `scorecard`
    column or the legacy `scores` column."""
    assert _module_has_content({"scorecard": {"a": 1}}, "scorecard") is True
    assert _module_has_content({"scores": {"b": 2}}, "scorecard") is True
    assert _module_has_content({}, "scorecard") is False
    assert _module_has_content({"scorecard": None, "scores": None}, "scorecard") is False


def test_unknown_module_key_returns_false() -> None:
    """Defensive: an unknown key must not crash; returns False so the
    caller treats it as 'needs generation' which is the safer default."""
    assert _module_has_content({"cv_html": "<p>ok</p>"}, "ghost-module") is False


def test_cross_column_isolation() -> None:
    """Populating cv_html must NOT cause the coverLetter module to
    report ready, and vice versa — this is the silent-bug pattern the
    test suite exists to defend against."""
    row = {"cv_html": "<p>cv</p>"}
    assert _module_has_content(row, "cv") is True
    assert _module_has_content(row, "coverLetter") is False
    assert _module_has_content(row, "personalStatement") is False
    assert _module_has_content(row, "portfolio") is False
    assert _module_has_content(row, "resume") is False
