"""
Behavior tests for `PipelineRuntime._persist_to_document_library`.

This is the function that fans out generated artifacts to the
`document_library` table, the durable canonical store for every
tailored & benchmark document the pipeline produces. The tests pin
contracts critical to the document-library UI:

  1. Resume is a first-class doc type — both `resume_html` (tailored)
     and `benchmark_resume_html` (benchmark) get their own upsert row
     when content is present, with doc_type="resume".
  2. Empty/whitespace-only HTML for a canonical doc type triggers an
     "error" row instead of being silently dropped — the UI surfaces
     a retry chip rather than a stale "planned" badge.
  3. The function NEVER RAISES — failures from the
     DocumentLibraryService are caught and downgraded to warnings.
  4. Missing application_id → no-op (early return).
  5. Missing "document_library" key in tables config → no-op.
  6. `generated_docs` and `benchmark_docs` extras are persisted with
     a humanized label and the correct category.

The DocumentLibraryService is monkeypatched at its module-level import
location because `_persist_to_document_library` re-imports it inside
the function body.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.services.pipeline_runtime import (
    CollectorSink,
    ExecutionMode,
    PipelineRuntime,
    RuntimeConfig,
)


# ── Helpers ───────────────────────────────────────────────────────────


class _FakeService:
    """Records every upsert_application_document call without touching DB."""

    def __init__(self, sb: Any, tables: Dict[str, str]) -> None:
        self.sb = sb
        self.tables = tables
        # Each entry is a dict of all kwargs passed to the upsert.
        self.calls: List[Dict[str, Any]] = []
        # If non-None, the next upsert raises this.
        self.raise_on: List[BaseException] = []

    async def upsert_application_document(self, **kwargs: Any) -> Dict[str, Any]:
        if self.raise_on:
            err = self.raise_on.pop(0)
            raise err
        self.calls.append(kwargs)
        return {"id": f"row-{len(self.calls)}", **kwargs}


def _patch_service(monkeypatch, service: _FakeService) -> None:
    """Patch DocumentLibraryService so the gate uses our recorder."""
    import app.services.document_library as dl

    def _factory(sb: Any, tables: Dict[str, str]) -> _FakeService:
        # Reuse the same recorder so tests can inspect calls afterwards.
        service.sb = sb
        service.tables = tables
        return service

    monkeypatch.setattr(dl, "DocumentLibraryService", _factory)


def _runtime(application_id: str = "app-123") -> PipelineRuntime:
    cfg = RuntimeConfig(
        mode=ExecutionMode.SYNC,
        user_id="u-test",
        application_id=application_id,
    )
    return PipelineRuntime(config=cfg, event_sink=CollectorSink())


def _tables() -> Dict[str, str]:
    return {"document_library": "document_library"}


def _by_category(calls: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    return [c for c in calls if c.get("doc_category") == category]


def _find(calls: List[Dict[str, Any]], *, category: str, doc_type: str) -> List[Dict[str, Any]]:
    return [
        c for c in calls
        if c.get("doc_category") == category and c.get("doc_type") == doc_type
    ]


async def _persist(
    rt: PipelineRuntime,
    *,
    cv_html: str = "",
    cl_html: str = "",
    ps_html: str = "",
    portfolio_html: str = "",
    benchmark_cv_html: str = "",
    generated_docs: Dict[str, str] | None = None,
    benchmark_docs: Dict[str, str] | None = None,
    resume_html: str = "",
    benchmark_resume_html: str = "",
    tables: Dict[str, str] | None = None,
) -> None:
    await rt._persist_to_document_library(
        sb=object(),
        tables=tables if tables is not None else _tables(),
        user_id="u-test",
        cv_html=cv_html,
        cl_html=cl_html,
        ps_html=ps_html,
        portfolio_html=portfolio_html,
        benchmark_cv_html=benchmark_cv_html,
        generated_docs=generated_docs or {},
        benchmark_docs=benchmark_docs or {},
        resume_html=resume_html,
        benchmark_resume_html=benchmark_resume_html,
    )


# ── Resume first-class persistence ────────────────────────────────────


class TestResumePersisted:
    async def test_tailored_resume_html_writes_resume_row(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, resume_html="<p>my resume</p>")

        ready = [c for c in svc.calls if c.get("status") == "ready"]
        rows = _find(ready, category="tailored", doc_type="resume")
        assert len(rows) == 1
        assert rows[0]["html_content"] == "<p>my resume</p>"
        assert rows[0]["label"] == "Tailored Résumé"
        assert rows[0]["source"] == "planner"

    async def test_benchmark_resume_html_writes_benchmark_resume_row(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, benchmark_resume_html="<p>bench resume</p>")

        ready = [c for c in svc.calls if c.get("status") == "ready"]
        rows = _find(ready, category="benchmark", doc_type="resume")
        assert len(rows) == 1
        assert rows[0]["html_content"] == "<p>bench resume</p>"
        assert rows[0]["label"] == "Benchmark Résumé"

    async def test_empty_resume_marks_error_row(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, resume_html="")

        error_rows = [c for c in svc.calls if c.get("status") == "error"]
        resume_errors = _find(error_rows, category="tailored", doc_type="resume")
        assert len(resume_errors) == 1
        assert resume_errors[0]["error_message"]

    async def test_whitespace_resume_marks_error_row(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, resume_html="   \n\t  ")

        error_rows = [c for c in svc.calls if c.get("status") == "error"]
        assert _find(error_rows, category="tailored", doc_type="resume")

    async def test_empty_benchmark_resume_marks_error_row(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, benchmark_resume_html="")

        error_rows = [c for c in svc.calls if c.get("status") == "error"]
        assert _find(error_rows, category="benchmark", doc_type="resume")

    async def test_present_resume_does_not_emit_error_row(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, resume_html="<p>real content</p>")

        error_rows = [c for c in svc.calls if c.get("status") == "error"]
        # No 'error' row for tailored/resume since the ready row was written
        assert not _find(error_rows, category="tailored", doc_type="resume")


# ── All canonical tailored/benchmark slots ────────────────────────────


class TestCanonicalSlots:
    async def test_all_tailored_canonicals_written_when_present(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(
            rt,
            cv_html="<cv/>",
            resume_html="<resume/>",
            cl_html="<cl/>",
            ps_html="<ps/>",
            portfolio_html="<port/>",
        )

        ready = [c for c in svc.calls if c.get("status") == "ready"]
        tailored = _by_category(ready, "tailored")
        types = {r["doc_type"] for r in tailored}
        assert {"cv", "resume", "cover_letter", "personal_statement", "portfolio"} <= types

    async def test_missing_canonical_emits_error_for_each(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        # Only resume present — every other canonical should error
        await _persist(rt, resume_html="<resume/>")

        errors = [c for c in svc.calls if c.get("status") == "error"]
        tailored_errors = _by_category(errors, "tailored")
        types = {r["doc_type"] for r in tailored_errors}
        # cv, cover_letter, personal_statement, portfolio should error
        assert {"cv", "cover_letter", "personal_statement", "portfolio"} <= types
        # resume should NOT error
        assert "resume" not in types

    async def test_benchmark_canonicals_error_when_missing(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        # Nothing benchmark-side
        await _persist(rt)

        errors = [c for c in svc.calls if c.get("status") == "error"]
        benchmark_errors = _by_category(errors, "benchmark")
        types = {r["doc_type"] for r in benchmark_errors}
        # All six benchmark canonicals (cv, resume, cover_letter, personal_statement, portfolio, learning_plan) should be in error
        assert {"cv", "resume", "cover_letter", "personal_statement", "portfolio", "learning_plan"} <= types


# ── Extras (generated_docs / benchmark_docs) ──────────────────────────


class TestExtraDocs:
    async def test_generated_docs_persisted_as_tailored(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, generated_docs={"learning_plan": "<lp/>"})

        ready = [c for c in svc.calls if c.get("status") == "ready"]
        rows = _find(ready, category="tailored", doc_type="learning_plan")
        assert len(rows) == 1
        # Label is humanized: snake_case -> Title Case
        assert rows[0]["label"] == "Learning Plan"
        assert rows[0]["html_content"] == "<lp/>"

    async def test_benchmark_docs_persisted_as_benchmark(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, benchmark_docs={"cover_letter": "<bcl/>"})

        ready = [c for c in svc.calls if c.get("status") == "ready"]
        rows = _find(ready, category="benchmark", doc_type="cover_letter")
        assert len(rows) == 1
        assert rows[0]["html_content"] == "<bcl/>"
        assert "Benchmark" in rows[0]["label"]

    async def test_empty_extra_docs_skipped(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, generated_docs={"learning_plan": ""})

        ready = [c for c in svc.calls if c.get("status") == "ready"]
        # No ready row for the empty extra
        assert not _find(ready, category="tailored", doc_type="learning_plan")


# ── Early-return contracts ────────────────────────────────────────────


class TestEarlyReturn:
    async def test_no_application_id_skips_persist(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime(application_id="")
        await _persist(rt, resume_html="<r/>")
        assert svc.calls == []

    async def test_missing_table_config_skips_persist(self, monkeypatch):
        svc = _FakeService(None, {})
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        await _persist(rt, resume_html="<r/>", tables={})
        assert svc.calls == []


# ── Never-raises contract ─────────────────────────────────────────────


class TestNeverRaises:
    async def test_service_constructor_failure_does_not_propagate(self, monkeypatch):
        import app.services.document_library as dl

        def _bad_factory(sb, tables):
            raise RuntimeError("svc init failed")

        monkeypatch.setattr(dl, "DocumentLibraryService", _bad_factory)
        rt = _runtime()
        # Must not raise
        await _persist(rt, resume_html="<r/>")

    async def test_partial_upsert_failures_swallowed(self, monkeypatch):
        svc = _FakeService(None, {})
        # First upsert raises (CV, since it's queued first), the rest succeed
        svc.raise_on = [RuntimeError("db oops")]
        _patch_service(monkeypatch, svc)
        rt = _runtime()
        # Must not raise
        await _persist(rt, resume_html="<r/>", cv_html="<cv/>")
        # Sibling upserts should still be recorded — gather() collects the
        # exception via return_exceptions=True instead of cancelling siblings.
        assert any(
            c.get("doc_type") == "resume" and c.get("status") == "ready"
            for c in svc.calls
        )
