"""
Behavior tests for `PipelineRuntime._run_critic_gate`.

The critic gate is the soft validation step that emits a phase-scoped
`validation_passed` / `validation_failed` event without blocking
pipeline progress. It exists because we want to ship the user's
application even when the critic raises a warning — but we want every
warning surfaced via the event sink so the UI can downgrade the job's
final status (see `finalize_job_status_payload`).

Five contracts this test pins:

  1. NEVER RAISES. Any exception from the critic, the artifact store,
     or the orchestration bus is swallowed and the gate returns None.

  2. Each `review` branch dispatches to the correct ValidationCritic
     method (benchmark, gap_map, documents, final_pack, plan).
     Unknown reviews return None and emit nothing.

  3. The emitted event uses `validation_passed`/`validation_failed`,
     `progress_pass`/`progress_fail`, and `message_pass`/`message_fail`
     according to `report_passed(report)`.

  4. The returned summary surfaces overall_score, docs_passed,
     docs_failed, error_count, warning_count, finding_count, and a
     truncated findings_summary (max 20 entries).

  5. `event.status` is "completed" on pass and "warning" on fail —
     this is what the SSE downgrade machinery keys off of.

These tests monkeypatch ValidationCritic at its module-level import
location because `_run_critic_gate` re-imports it inside the function
body (lazy import — keeps cold-start cost off the critical path).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from ai_engine.agents.artifact_contracts import ValidationFinding, ValidationReport
from app.services.pipeline_runtime import (
    CollectorSink,
    ExecutionMode,
    PipelineRuntime,
    RuntimeConfig,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _make_report(
    *,
    overall_score: float = 100.0,
    findings: Optional[List[ValidationFinding]] = None,
    docs_passed: Optional[List[str]] = None,
    docs_failed: Optional[List[str]] = None,
) -> ValidationReport:
    return ValidationReport(
        overall_score=overall_score,
        findings=list(findings or []),
        docs_passed=list(docs_passed or []),
        docs_failed=list(docs_failed or []),
    )


def _runtime() -> PipelineRuntime:
    cfg = RuntimeConfig(mode=ExecutionMode.SYNC, user_id="u-test")
    return PipelineRuntime(config=cfg, event_sink=CollectorSink())


def _fake_critic_class(
    *,
    benchmark_report: Optional[ValidationReport] = None,
    gap_map_report: Optional[ValidationReport] = None,
    documents_report: Optional[ValidationReport] = None,
    final_pack_report: Optional[ValidationReport] = None,
    plan_report: Optional[ValidationReport] = None,
    raises: Optional[BaseException] = None,
):
    """Build a stand-in ValidationCritic class with controllable returns."""
    calls: Dict[str, Any] = {"calls": []}

    class _FakeCritic:
        def __init__(self) -> None:  # noqa: D401 - matches real ctor
            if raises is not None:
                raise raises
            calls["calls"].append(("__init__", None))

        def review_benchmark(self, artifact: Any) -> ValidationReport:
            calls["calls"].append(("review_benchmark", artifact))
            return benchmark_report or _make_report()

        def review_gap_map(self, artifact: Any) -> ValidationReport:
            calls["calls"].append(("review_gap_map", artifact))
            return gap_map_report or _make_report()

        def review_documents(
            self, artifact: Any, required_modules: Optional[List[str]] = None
        ) -> ValidationReport:
            calls["calls"].append(("review_documents", artifact, required_modules))
            return documents_report or _make_report()

        def review_final_pack(self, artifact: Any) -> ValidationReport:
            calls["calls"].append(("review_final_pack", artifact))
            return final_pack_report or _make_report()

        def review_plan(self, artifact: Any) -> ValidationReport:
            calls["calls"].append(("review_plan", artifact))
            return plan_report or _make_report()

    _FakeCritic._calls = calls  # type: ignore[attr-defined]
    return _FakeCritic


def _patch_critic(monkeypatch, critic_cls, *, report_passed=None) -> None:
    import ai_engine.agents.validation_critic as vc

    monkeypatch.setattr(vc, "ValidationCritic", critic_cls)
    if report_passed is not None:
        monkeypatch.setattr(vc, "report_passed", report_passed)


async def _run_gate(
    rt: PipelineRuntime,
    *,
    review: str,
    artifact: Any = None,
    phase: str = "sentinel",
    required_modules: Optional[List[str]] = None,
    progress_pass: int = 90,
    progress_fail: int = 80,
    message_pass: str = "OK",
    message_fail: str = "FAIL",
):
    return await rt._run_critic_gate(
        phase=phase,
        artifact=artifact,
        review=review,
        user_id="u-test",
        required_modules=required_modules,
        progress_pass=progress_pass,
        progress_fail=progress_fail,
        message_pass=message_pass,
        message_fail=message_fail,
    )


# ── Unknown review type ───────────────────────────────────────────────


class TestUnknownReview:
    async def test_unknown_review_returns_none(self, monkeypatch):
        _patch_critic(monkeypatch, _fake_critic_class())
        rt = _runtime()
        result = await _run_gate(rt, review="not_a_real_review")
        assert result is None

    async def test_unknown_review_emits_no_events(self, monkeypatch):
        _patch_critic(monkeypatch, _fake_critic_class())
        rt = _runtime()
        await _run_gate(rt, review="not_a_real_review")
        assert rt.sink.events == []


# ── Review dispatch ───────────────────────────────────────────────────


class TestReviewDispatch:
    @pytest.mark.parametrize(
        ("review", "expected_method"),
        [
            ("benchmark", "review_benchmark"),
            ("gap_map", "review_gap_map"),
            ("documents", "review_documents"),
            ("final_pack", "review_final_pack"),
            ("plan", "review_plan"),
        ],
    )
    async def test_review_dispatches_to_correct_method(
        self, monkeypatch, review, expected_method
    ):
        cls = _fake_critic_class()
        _patch_critic(monkeypatch, cls)
        rt = _runtime()
        await _run_gate(rt, review=review, artifact={"key": "val"})
        method_calls = [c[0] for c in cls._calls["calls"] if c[0] != "__init__"]
        assert expected_method in method_calls

    async def test_documents_review_forwards_required_modules(self, monkeypatch):
        cls = _fake_critic_class()
        _patch_critic(monkeypatch, cls)
        rt = _runtime()
        await _run_gate(
            rt,
            review="documents",
            required_modules=["cv", "coverLetter"],
        )
        # find the review_documents call tuple
        for call in cls._calls["calls"]:
            if call[0] == "review_documents":
                assert call[2] == ["cv", "coverLetter"]
                return
        pytest.fail("review_documents was never called")


# ── Pass / fail event emission ────────────────────────────────────────


class TestPassFailEmission:
    async def test_passed_emits_validation_passed_event(self, monkeypatch):
        rep = _make_report()  # no findings → passed
        _patch_critic(monkeypatch, _fake_critic_class(benchmark_report=rep))
        rt = _runtime()
        await _run_gate(rt, review="benchmark", progress_pass=95, message_pass="all good")

        assert len(rt.sink.events) == 1
        ev = rt.sink.events[0]
        assert ev.event_type == "validation_passed"
        assert ev.progress == 95
        assert ev.message == "all good"
        assert ev.status == "completed"
        assert ev.phase == "sentinel"

    async def test_failed_emits_validation_failed_event(self, monkeypatch):
        rep = _make_report(
            findings=[ValidationFinding(severity="error", rule="r1", message="m1")]
        )
        _patch_critic(monkeypatch, _fake_critic_class(benchmark_report=rep))
        rt = _runtime()
        await _run_gate(
            rt,
            review="benchmark",
            progress_fail=70,
            message_fail="found problems",
        )

        assert len(rt.sink.events) == 1
        ev = rt.sink.events[0]
        assert ev.event_type == "validation_failed"
        assert ev.progress == 70
        assert ev.message == "found problems"
        assert ev.status == "warning"

    async def test_phase_propagates_to_event(self, monkeypatch):
        _patch_critic(monkeypatch, _fake_critic_class())
        rt = _runtime()
        await _run_gate(rt, review="benchmark", phase="atlas")
        assert rt.sink.events[0].phase == "atlas"


# ── Returned summary ──────────────────────────────────────────────────


class TestReturnedSummary:
    async def test_passed_summary_has_passed_true(self, monkeypatch):
        _patch_critic(monkeypatch, _fake_critic_class())
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is not None
        assert result["passed"] is True

    async def test_failed_summary_has_passed_false(self, monkeypatch):
        rep = _make_report(
            findings=[ValidationFinding(severity="error", rule="r1", message="m1")]
        )
        _patch_critic(monkeypatch, _fake_critic_class(benchmark_report=rep))
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is not None
        assert result["passed"] is False

    async def test_summary_surfaces_counts(self, monkeypatch):
        rep = _make_report(
            findings=[
                ValidationFinding(severity="error", rule="e1", message="x"),
                ValidationFinding(severity="error", rule="e2", message="x"),
                ValidationFinding(severity="warning", rule="w1", message="x"),
            ],
            docs_passed=["cv"],
            docs_failed=["coverLetter"],
            overall_score=42.0,
        )
        _patch_critic(monkeypatch, _fake_critic_class(benchmark_report=rep))
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is not None
        assert result["error_count"] == 2
        assert result["warning_count"] == 1
        assert result["finding_count"] == 3
        assert result["docs_passed"] == ["cv"]
        assert result["docs_failed"] == ["coverLetter"]
        assert result["overall_score"] == 42.0

    async def test_findings_summary_truncated_to_20(self, monkeypatch):
        many = [
            ValidationFinding(severity="warning", rule=f"r{i}", message=f"m{i}")
            for i in range(50)
        ]
        rep = _make_report(findings=many)
        _patch_critic(monkeypatch, _fake_critic_class(benchmark_report=rep))
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is not None
        assert len(result["findings_summary"]) == 20

    async def test_findings_summary_entry_shape(self, monkeypatch):
        rep = _make_report(
            findings=[
                ValidationFinding(
                    severity="error",
                    rule="my.rule",
                    message="boom",
                    target_doc_type="cv",
                )
            ]
        )
        _patch_critic(monkeypatch, _fake_critic_class(benchmark_report=rep))
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is not None
        entry = result["findings_summary"][0]
        assert entry["code"] == "my.rule"
        assert entry["severity"] == "error"
        assert entry["message"] == "boom"
        assert entry["doc_type"] == "cv"


# ── Event data payload ────────────────────────────────────────────────


class TestEventData:
    async def test_event_data_carries_summary_subset(self, monkeypatch):
        rep = _make_report(
            findings=[
                ValidationFinding(severity="warning", rule="r1", message="m1"),
            ],
            docs_passed=["cv"],
            docs_failed=[],
            overall_score=87.5,
        )
        _patch_critic(monkeypatch, _fake_critic_class(benchmark_report=rep))
        rt = _runtime()
        await _run_gate(rt, review="benchmark")
        ev = rt.sink.events[0]
        assert ev.data["overall_score"] == 87.5
        assert ev.data["docs_passed"] == ["cv"]
        assert ev.data["error_count"] == 0
        assert ev.data["warning_count"] == 1
        assert ev.data["finding_count"] == 1


# ── Never-raises contract ─────────────────────────────────────────────


class TestNeverRaises:
    async def test_critic_constructor_raising_returns_none(self, monkeypatch):
        cls = _fake_critic_class(raises=RuntimeError("boom"))
        _patch_critic(monkeypatch, cls)
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is None
        # No event emitted because the gate exited early
        assert rt.sink.events == []

    async def test_critic_review_raising_returns_none(self, monkeypatch):
        class _ExplodingCritic:
            def __init__(self) -> None: ...
            def review_benchmark(self, artifact: Any) -> ValidationReport:
                raise ValueError("bad artifact")

        import ai_engine.agents.validation_critic as vc
        monkeypatch.setattr(vc, "ValidationCritic", _ExplodingCritic)
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is None

    async def test_artifact_store_failure_does_not_break_gate(self, monkeypatch):
        _patch_critic(monkeypatch, _fake_critic_class())
        rt = _runtime()

        class _BadStore:
            async def put(self, *args, **kwargs):
                raise RuntimeError("store down")

        rt._artifact_store = _BadStore()
        result = await _run_gate(rt, review="benchmark")
        # Gate still returns a summary even when the store fails
        assert result is not None
        assert result["passed"] is True
        # Event still emitted
        assert len(rt.sink.events) == 1

    async def test_orchestration_bus_failure_does_not_break_gate(self, monkeypatch):
        _patch_critic(monkeypatch, _fake_critic_class())
        rt = _runtime()

        class _BadBus:
            async def publish(self, *args, **kwargs):
                raise RuntimeError("bus down")

        rt._orchestration_bus = _BadBus()
        result = await _run_gate(rt, review="benchmark")
        assert result is not None
        assert result["passed"] is True
        assert len(rt.sink.events) == 1


# ── report_passed integration ─────────────────────────────────────────


class TestReportPassedHonored:
    async def test_overridden_report_passed_true_yields_passed_event(self, monkeypatch):
        # Build a report that *would* normally fail (has an error finding)
        # but stub `report_passed` to True — the gate must respect the helper.
        rep = _make_report(
            findings=[ValidationFinding(severity="error", rule="r", message="m")]
        )
        _patch_critic(
            monkeypatch,
            _fake_critic_class(benchmark_report=rep),
            report_passed=lambda _r: True,
        )
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is not None
        assert result["passed"] is True
        assert rt.sink.events[0].event_type == "validation_passed"

    async def test_overridden_report_passed_false_yields_failed_event(self, monkeypatch):
        rep = _make_report()  # no findings → would normally pass
        _patch_critic(
            monkeypatch,
            _fake_critic_class(benchmark_report=rep),
            report_passed=lambda _r: False,
        )
        rt = _runtime()
        result = await _run_gate(rt, review="benchmark")
        assert result is not None
        assert result["passed"] is False
        assert rt.sink.events[0].event_type == "validation_failed"
