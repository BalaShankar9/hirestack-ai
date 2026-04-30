"""S13-F4: Pin the wiring between pipeline_runtime and the evidence graph.

Brief 3 ("Evidence Graph v1") ratifies that the validator/critic consume
contradiction signals end-to-end. Until S13-F4, pipeline_runtime
canonicalized evidence but never invoked ``detect_contradictions()``,
so the ``evidence_contradictions`` table never received production rows
and the evidence-strength score's contradiction penalty was always zero
in practice. This module pins the call so a future refactor cannot
silently drop it again.

We pin via AST inspection rather than a full runtime test: the runtime
path is async, large, and already covered for canonicalize/score by
``test_evidence_graph.py``. A static check is the cheapest signal that
the wiring is in place and stays in place.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


PIPELINE_RUNTIME_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "pipeline_runtime.py"
)


@pytest.fixture(scope="module")
def pipeline_runtime_tree() -> ast.AST:
    src = PIPELINE_RUNTIME_PATH.read_text(encoding="utf-8")
    return ast.parse(src, filename=str(PIPELINE_RUNTIME_PATH))


def _attribute_calls(tree: ast.AST, attr_name: str) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr_name
        ):
            calls.append(node)
    return calls


class TestPipelineEvidenceGraphWiring:
    def test_pipeline_runtime_canonicalizes_evidence(self, pipeline_runtime_tree):
        """Sanity: the canonicalize call must still be present."""
        assert _attribute_calls(pipeline_runtime_tree, "canonicalize"), (
            "pipeline_runtime no longer calls graph_builder.canonicalize() — "
            "Brief 3's evidence-graph path is broken."
        )

    def test_pipeline_runtime_detects_contradictions(self, pipeline_runtime_tree):
        """S13-F4 wiring: detect_contradictions() must be invoked so the
        ``evidence_contradictions`` table actually receives rows during
        normal pipeline execution. Without this call the contradiction
        penalty in compute_evidence_strength_score() is always zero in
        production, breaking Brief 3's planner feedback loop."""
        calls = _attribute_calls(pipeline_runtime_tree, "detect_contradictions")
        assert calls, (
            "pipeline_runtime must call graph_builder.detect_contradictions() "
            "after canonicalize so cross-job conflicts are persisted into "
            "evidence_contradictions and folded into the planner's risk_mode "
            "via the evidence-strength score. (S13-F4)"
        )

    def test_contradiction_count_is_logged(self, pipeline_runtime_tree):
        """The structured plan_artifact log line must surface the
        contradiction counters so SLO/observability dashboards can chart
        them. Pinned because silent regressions are otherwise invisible."""
        src = PIPELINE_RUNTIME_PATH.read_text(encoding="utf-8")
        assert "contradictions_total" in src, (
            "pipeline_runtime.plan_artifact log must include "
            "contradictions_total so observability can chart Brief 3 health."
        )
        assert "contradictions_unresolved" in src, (
            "pipeline_runtime.plan_artifact log must include "
            "contradictions_unresolved so observability can flag drift."
        )
