"""Wave 2 tests — Intelligence & quality.

Covers:
- app.services.quality_scorer: score_document, score_bundle, aggregate_score
- MetricsCollector.record_doc_quality / get_doc_quality_stats
- /metrics exposes hirestack_doc_quality_* gauges
"""
from __future__ import annotations

import inspect


from app.services import quality_scorer as qs
from app.core.metrics import MetricsCollector


# ── score_document ────────────────────────────────────────────────────

def test_score_document_empty_returns_zero_with_issue():
    res = qs.score_document("", doc_type="cv")
    assert res["score"] == 0
    assert "empty document" in res["issues"]


def test_score_document_too_short_marks_length_not_ok():
    res = qs.score_document("<h1>hi</h1><p>tiny</p>", doc_type="cv")
    assert res["length_ok"] is False
    assert any("too short" in i for i in res["issues"])
    # but structure_ok should still be true
    assert res["structure_ok"] is True


def test_score_document_well_formed_cv_high_score():
    body = (
        "<h1>Jane Doe — Senior Engineer</h1>"
        + "<p>Summary paragraph " + ("with substantial body. " * 60) + "</p>"
        + "<h2>Experience</h2>"
        + "<ul>" + "<li>Built things with Python and FastAPI.</li>" * 8 + "</ul>"
    )
    res = qs.score_document(body, doc_type="cv", jd_keywords=["python", "fastapi"])
    assert res["score"] >= 80, res
    assert res["length_ok"] is True
    assert res["structure_ok"] is True
    assert res["ats_ok"] is True
    assert res["keyword_coverage"] == 1.0
    assert res["keyword_hits"] == 2


def test_score_document_ats_hostile_loses_points():
    body = (
        "<h1>Jane</h1>"
        + "<p>" + "x" * 1600 + "</p>"
        + '<img src="logo.png">'
        + '<p style="color:red">styled</p>'
    )
    res = qs.score_document(body, doc_type="cv")
    assert res["ats_ok"] is False
    assert any("ATS issue" in i for i in res["issues"])


def test_score_document_unknown_doc_type_uses_default_band():
    res = qs.score_document(
        "<h1>x</h1><p>" + ("lorem " * 200) + "</p>",
        doc_type="some_new_doc_type",
        jd_keywords=["lorem"],
    )
    # default band is generous; should pass length
    assert res["length_ok"] is True
    assert res["structure_ok"] is True


def test_score_document_keyword_coverage_low_warns():
    body = "<h1>x</h1><p>" + ("filler " * 200) + "</p>"
    res = qs.score_document(body, doc_type="cv",
                            jd_keywords=["python", "kubernetes", "rust", "elixir", "haskell"])
    assert res["keyword_hits"] == 0
    assert res["keyword_coverage"] == 0.0
    assert any("low JD-keyword coverage" in i for i in res["issues"])


# ── score_bundle / aggregate_score ───────────────────────────────────

def test_score_bundle_skips_empty_docs():
    bundle = {
        "cv": "<h1>x</h1><p>" + ("body " * 400) + "</p>",
        "resume": "",
        "cover_letter": None,  # type: ignore[dict-item]
    }
    res = qs.score_bundle(bundle, jd_keywords=["body"])
    assert "cv" in res
    assert "resume" not in res
    assert "cover_letter" not in res


def test_aggregate_score_handles_empty_and_normal():
    assert qs.aggregate_score({}) == 0
    res = qs.score_bundle({
        "cv": "<h1>x</h1><p>" + ("python " * 400) + "</p>",
        "resume": "<h1>x</h1><p>" + ("python " * 200) + "</p>",
    }, jd_keywords=["python"])
    agg = qs.aggregate_score(res)
    assert 0 < agg <= 100


# ── MetricsCollector quality recording ───────────────────────────────

def test_metrics_collector_records_doc_quality():
    MetricsCollector.reset()
    mc = MetricsCollector.get()
    mc.record_doc_quality("cv", 85)
    mc.record_doc_quality("cv", 90)
    mc.record_doc_quality("cv", 75)
    mc.record_doc_quality("resume", 60)
    stats = mc.get_doc_quality_stats()
    assert stats["cv"]["count"] == 3
    assert stats["cv"]["mean"] == round((85 + 90 + 75) / 3, 1)
    assert stats["cv"]["min"] == 75
    assert stats["cv"]["last"] == 75
    assert stats["resume"]["count"] == 1


def test_metrics_collector_record_doc_quality_clamps_invalid():
    MetricsCollector.reset()
    mc = MetricsCollector.get()
    mc.record_doc_quality("cv", -5)
    mc.record_doc_quality("cv", 500)
    mc.record_doc_quality("cv", "not_a_number")  # type: ignore[arg-type]
    stats = mc.get_doc_quality_stats()
    assert stats["cv"]["count"] == 2  # third was rejected
    assert stats["cv"]["min"] == 0
    assert stats["cv"]["last"] == 100


# ── /metrics anchor: gauge presence ───────────────────────────────────

def test_metrics_endpoint_exposes_doc_quality_gauges():
    import backend.main as backend_main  # type: ignore
    src = inspect.getsource(backend_main)
    for marker in (
        "hirestack_doc_quality_mean",
        "hirestack_doc_quality_p50",
        "hirestack_doc_quality_p95",
        "hirestack_doc_quality_min",
        "get_doc_quality_stats",
    ):
        assert marker in src, f"missing /metrics marker: {marker}"


# ── pipeline_runtime anchor: scorer is wired into Sentinel ────────────

def test_sentinel_wires_quality_scorer():
    from app.services import pipeline_runtime as pr_module
    src = inspect.getsource(pr_module)
    # The deterministic scorer must be invoked in the Sentinel block.
    assert "from app.services.quality_scorer import score_bundle" in src
    assert "self._per_doc_quality" in src
    assert "record_doc_quality" in src
    assert 'event_type="warning", phase="sentinel"' in src
