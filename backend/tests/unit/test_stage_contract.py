"""S14-F1: pin the canonical agent stage contract.

If this test fails, three places have drifted:
  1. ``ai_engine/agents/stage_contract.py`` (source of truth)
  2. ``ai_engine/agents/orchestrator.py::AgentPipeline._execute_pipeline_stages``
  3. ``backend/app/api/routes/generate/helpers.py::_STAGE_ORDER``
  4. ``frontend/src/components/workspace/agent-timeline-rail.tsx::STAGE_ORDER``

The frontend mirror is verified by reading the .tsx file as text — keeping
the literal in JS lets the bundle stay self-contained but means we have to
guard against silent drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_engine.agents.stage_contract import (
    DOCUMENT_STAGE_ORDER,
    RUNTIME_PHASE_ORDER,
)


# Treat the tuple as a public wire contract.  Renaming or reordering is a
# breaking change to the SSE ``agent_status`` event and the resume-point
# logic in ``backend/app/api/routes/generate/jobs.py``.
EXPECTED_DOC_ORDER = (
    "researcher",
    "drafter",
    "critic",
    "optimizer",
    "fact_checker",
    "optimizer_final_analysis",
    "validator",
)

EXPECTED_PHASE_ORDER = (
    "recon", "atlas", "cipher", "quill", "forge", "sentinel", "nova",
)


def test_document_stage_order_is_pinned() -> None:
    assert DOCUMENT_STAGE_ORDER == EXPECTED_DOC_ORDER


def test_runtime_phase_order_is_pinned() -> None:
    assert RUNTIME_PHASE_ORDER == EXPECTED_PHASE_ORDER


def test_helpers_stage_order_consumes_canonical_tuple() -> None:
    """The helpers module must source from the contract, not redeclare."""
    from backend.app.api.routes.generate.helpers import _STAGE_ORDER

    assert _STAGE_ORDER == list(DOCUMENT_STAGE_ORDER), (
        "helpers._STAGE_ORDER drifted from canonical contract — "
        "fix by importing from ai_engine.agents.stage_contract"
    )


def test_frontend_timeline_rail_mirrors_contract() -> None:
    """Frontend rail keeps a literal tuple for bundle self-containment.

    This test reads the .tsx file as text and asserts every canonical
    stage name appears in the same order. If the file moves, update
    REPO_ROOT.
    """
    repo_root = Path(__file__).resolve().parents[3]
    rail = repo_root / "frontend" / "src" / "components" / "workspace" / "agent-timeline-rail.tsx"
    if not rail.exists():
        pytest.skip(f"frontend rail not present at {rail}")

    text = rail.read_text(encoding="utf-8")
    # Look for the STAGE_ORDER literal block.
    start = text.find("const STAGE_ORDER")
    assert start >= 0, "agent-timeline-rail.tsx no longer exports STAGE_ORDER"
    block_end = text.find("];", start)
    assert block_end > start
    block = text[start:block_end]

    for stage in DOCUMENT_STAGE_ORDER:
        assert f'"{stage}"' in block, (
            f"frontend STAGE_ORDER missing canonical stage {stage!r}"
        )

    # Order check: each successive stage must appear after the previous.
    last = -1
    for stage in DOCUMENT_STAGE_ORDER:
        idx = block.find(f'"{stage}"')
        assert idx > last, (
            f"frontend STAGE_ORDER has {stage!r} out of canonical order"
        )
        last = idx
