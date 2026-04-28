"""Route-consolidation contract tests.

Rank 3 of the 30-60-90 plan: pipeline_runtime.py is the authoritative execution
engine; jobs.py and worker.py are thin adapters.  These tests guard against
regression where someone accidentally re-routes a code path around the runtime.

Invariants:
  1. _run_generation_job (the compat shim) delegates to _run_generation_job_via_runtime
  2. worker.py imports and calls _run_generation_job_via_runtime (not the shim)
  3. The create-job route handler dispatches _run_generation_job_via_runtime as its task
  4. _run_generation_job_via_runtime is defined in jobs.py (not inline in the route)
  5. _run_generation_job_inner (legacy body) exists but is never called by the shim or route
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest


_JOBS_PY = Path(__file__).parents[2] / "app" / "api" / "routes" / "generate" / "jobs.py"
_WORKER_PY = Path(__file__).parents[2] / "app" / "worker.py"
_INIT_PY = Path(__file__).parents[2] / "app" / "api" / "routes" / "generate" / "__init__.py"


def _jobs_source() -> str:
    return _JOBS_PY.read_text()


def _worker_source() -> str:
    return _WORKER_PY.read_text() if _WORKER_PY.exists() else ""


class TestRunGenerationJobShim:
    """_run_generation_job must be a thin shim, not a parallel implementation."""

    def test_shim_is_short(self):
        """The shim body should be at most ~10 lines (thin adapter)."""
        import ast

        tree = ast.parse(_jobs_source())
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name == "_run_generation_job":
                    # Count statements in the body
                    num_statements = len(node.body)
                    assert num_statements <= 5, (
                        f"_run_generation_job has {num_statements} statements — "
                        "it must remain a thin shim (≤5 statements). "
                        "Move logic to _run_generation_job_via_runtime instead."
                    )
                    return
        pytest.fail("_run_generation_job not found in jobs.py")

    def test_shim_calls_runtime_entrypoint(self):
        """_run_generation_job body must call _run_generation_job_via_runtime."""
        source = _jobs_source()
        # Find the function definition and its immediate body
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name == "_run_generation_job":
                    body_src = ast.unparse(node)
                    assert "_run_generation_job_via_runtime" in body_src, (
                        "_run_generation_job must call _run_generation_job_via_runtime. "
                        "Do not add a parallel execution path to the shim."
                    )
                    return
        pytest.fail("_run_generation_job not found in jobs.py")

    def test_shim_does_not_call_inner_directly(self):
        """The shim must NOT call _run_generation_job_inner (legacy bypass)."""
        source = _jobs_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name == "_run_generation_job":
                    body_src = ast.unparse(node)
                    assert "_run_generation_job_inner" not in body_src, (
                        "_run_generation_job must NOT call _run_generation_job_inner. "
                        "The shim must route through the canonical runtime path."
                    )
                    return
        pytest.fail("_run_generation_job not found in jobs.py")


class TestWorkerRouting:
    """worker.py must import and call the canonical runtime entrypoint."""

    def test_worker_imports_via_runtime(self):
        src = _worker_source()
        if not src:
            pytest.skip("worker.py not found — skipping worker routing contract")
        assert "_run_generation_job_via_runtime" in src, (
            "worker.py must import _run_generation_job_via_runtime. "
            "Do not call the legacy shim from the worker process."
        )

    def test_worker_does_not_call_legacy_shim(self):
        src = _worker_source()
        if not src:
            pytest.skip("worker.py not found")
        # The worker should import the runtime, not the shim
        # Find all calls to _run_generation_job (without the _via_runtime suffix)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "_run_generation_job":
                    pytest.fail(
                        "worker.py calls the legacy shim _run_generation_job. "
                        "It must call _run_generation_job_via_runtime directly."
                    )


class TestCreateJobRouteDispatch:
    """The create-job POST handler must dispatch to the canonical runtime."""

    def test_create_job_dispatches_runtime(self):
        """asyncio.create_task in jobs.py must pass _run_generation_job_via_runtime."""
        source = _jobs_source()
        assert "_run_generation_job_via_runtime" in source, (
            "_run_generation_job_via_runtime must exist in jobs.py"
        )
        # The only create_task call in the production path should reference the runtime
        import re

        create_task_calls = re.findall(
            r"asyncio\.create_task\(([^)]+)\)", source
        )
        for call in create_task_calls:
            if "_run_generation_job" in call and "_via_runtime" not in call:
                pytest.fail(
                    f"asyncio.create_task dispatches legacy shim: create_task({call}). "
                    "Route handler must dispatch _run_generation_job_via_runtime."
                )


class TestExportsAreConsistent:
    """__init__.py exports must stay in sync with the authoritative functions."""

    def test_via_runtime_exported(self):
        """_run_generation_job_via_runtime must be exported from the generate package."""
        init_src = _INIT_PY.read_text()
        assert "_run_generation_job_via_runtime" in init_src, (
            "_run_generation_job_via_runtime must be exported from "
            "app.api.routes.generate.__init__ so worker.py can import it cleanly."
        )
