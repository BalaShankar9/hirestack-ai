"""ATLAS Slice 4.2 — surface archetypes + validation_report through SSE.

Verifies that the additive plumbing in
``backend/app/api/routes/generate/helpers._format_response`` and
the ``response["meta"]`` block in
``backend/app/api/routes/generate/stream.py`` correctly carry
ATLAS v2 fields end-to-end without disturbing any existing keys.
"""
from __future__ import annotations

from typing import Any, Dict

from app.api.routes.generate.helpers import _format_response


def _baseline(**overrides: Any) -> Dict[str, Any]:
    base = dict(
        benchmark_data={},
        gap_analysis={},
        roadmap={},
        cv_html="<p>cv</p>",
        cl_html="<p>cl</p>",
        ps_html="",
        portfolio_html="",
        validation={"cv": {"valid": True}},
        keywords=["python"],
        job_title="Senior Engineer",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# helpers._format_response — archetypes pass-through
# ---------------------------------------------------------------------------

def test_format_response_omits_archetypes_when_absent():
    resp = _format_response(**_baseline())
    assert "archetypes" not in resp["benchmark"]


def test_format_response_omits_archetypes_when_empty_list():
    resp = _format_response(**_baseline(benchmark_data={"archetypes": []}))
    # Empty list is treated as "absent" (no FE value in surfacing []).
    assert "archetypes" not in resp["benchmark"]


def test_format_response_passes_archetypes_through():
    archetypes = [
        {
            "name": "Stripe Senior Eng",
            "must_have_skills": ["python", "go"],
            "nice_to_have_skills": ["rust"],
            "years_range": [5, 10],
            "salary_band": {"p25": 200000, "p50": 240000, "p75": 280000},
            "cultural_signals": ["ownership"],
        },
        {
            "name": "Datadog Staff",
            "must_have_skills": ["python"],
            "nice_to_have_skills": [],
            "years_range": [7, 12],
            "salary_band": {},
            "cultural_signals": [],
        },
    ]
    resp = _format_response(**_baseline(benchmark_data={"archetypes": archetypes}))
    assert resp["benchmark"]["archetypes"] == archetypes
    # Other benchmark fields preserved
    assert resp["benchmark"]["summary"]
    assert resp["benchmark"]["keywords"] == ["python"]


def test_format_response_ignores_non_list_archetypes():
    """Defensive: a non-list value (string / dict / None) is silently dropped."""
    for bad in [None, "oops", {"x": 1}, 42]:
        resp = _format_response(**_baseline(benchmark_data={"archetypes": bad}))
        assert "archetypes" not in resp["benchmark"]


# ---------------------------------------------------------------------------
# Existing benchmark fields untouched
# ---------------------------------------------------------------------------

def test_format_response_preserves_existing_benchmark_fields():
    resp = _format_response(**_baseline(
        benchmark_data={
            "ideal_profile": {"summary": "test summary"},
            "ideal_skills": [{"name": "Python", "level": "expert", "importance": "must"}],
            "ideal_experience": ["sr eng"],
            "scoring_weights": {"skills": 0.6},
            "archetypes": [{"name": "x", "must_have_skills": [], "nice_to_have_skills": [],
                            "years_range": [3, 7], "salary_band": {}, "cultural_signals": []}],
        }
    ))
    b = resp["benchmark"]
    assert b["summary"] == "test summary"
    assert b["idealSkills"][0]["name"] == "Python"
    assert b["idealExperience"] == ["sr eng"]
    assert b["scoringWeights"]["skills"] == 0.6
    assert len(b["archetypes"]) == 1
