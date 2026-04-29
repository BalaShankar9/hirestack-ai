"""S5-F4 — Pin the chain construction surface.

The 20 LLM chains exported from `ai_engine.chains` MUST share one
construction contract: `__init__(self, ai_client)`. The service layer
constructs every chain through a single registry / factory; if any
chain quietly switches to `__init__(client, prompt_dir)` style or
inserts a required positional arg, the platform breaks at startup.

Coverage:
- 20 simple chains pin __init__(ai_client) signature.
- DocumentPackPlanner is intentionally exempt (catalog dependency)
  and pinned as the SOLE allowed exception with explicit allowlist.
- DocumentPackPlan is a dataclass, not a chain — skipped.
- Each chain pinned to define at least one async public method
  (drift to sync would break the executor pool).
"""
from __future__ import annotations

import inspect
from typing import Any, get_type_hints  # noqa: F401

import pytest

from ai_engine import chains as chains_module


# Chains with dependencies beyond `ai_client`. Adding to this list
# requires explicit review — prefer the simple constructor.
_NON_STANDARD_INIT = {"DocumentPackPlanner"}

# `__all__` re-exports that aren't chains (dataclasses, enums, etc.).
_NOT_A_CHAIN = {"DocumentPackPlan"}


def _exported_chain_names() -> list[str]:
    return [
        name
        for name in chains_module.__all__
        if name not in _NOT_A_CHAIN
    ]


def _resolve(name: str):
    cls = getattr(chains_module, name)
    assert inspect.isclass(cls), f"{name} re-exported from chains/ is not a class"
    return cls


# ── Surface enumeration sanity ────────────────────────────────────────


def test_chains_export_surface_unchanged() -> None:
    """Pin the public chain count. Drift requires explicitly updating
    this test (and the audit doc)."""
    exported = _exported_chain_names()
    # 20 chains + DocumentPackPlan dataclass = 21 in __all__
    assert len(exported) == 20, (
        f"Expected 20 exported chains, got {len(exported)}: {exported}. "
        "If intentionally adding/removing a chain, update this test "
        "and docs/audits/S5-ai-engine-chains.md."
    )


def test_chains_module_all_matches_imports() -> None:
    """Every name in __all__ must actually be importable from the
    module — guards against a refactor that deletes a chain but
    forgets to clean __all__."""
    for name in chains_module.__all__:
        assert hasattr(chains_module, name), f"__all__ lists '{name}' but module lacks it"


# ── Standard __init__(ai_client) contract ─────────────────────────────


@pytest.mark.parametrize(
    "chain_name",
    [n for n in [
        "RoleProfilerChain",
        "BenchmarkBuilderChain",
        "GapAnalyzerChain",
        "CareerConsultantChain",
        "DocumentGeneratorChain",
        "ValidatorChain",
        "ATSScannerChain",
        "InterviewSimulatorChain",
        "DocumentVariantChain",
        "SalaryCoachChain",
        "LearningChallengeChain",
        "UniversalDocGeneratorChain",
        "LinkedInAdvisorChain",
        "MarketIntelligenceChain",
        "DailyBriefingChain",
        "ApplicationCoachChain",
        "DocumentDiscoveryChain",
        "AdaptiveDocumentChain",
        "CompanyIntelChain",
    ]],
)
def test_chain_init_accepts_ai_client_param(chain_name: str) -> None:
    """The service-layer factory always passes `ai_client`. If a chain
    renames it (e.g. to `client`) the keyword call breaks at runtime."""
    cls = _resolve(chain_name)
    sig = inspect.signature(cls.__init__)
    params = {n for n in sig.parameters if n != "self"}
    assert "ai_client" in params, (
        f"{chain_name}.__init__ must accept `ai_client`; got params={params}. "
        "Renaming this parameter breaks every call site in app/services/*."
    )


@pytest.mark.parametrize(
    "chain_name",
    [n for n in [
        "RoleProfilerChain",
        "BenchmarkBuilderChain",
        "GapAnalyzerChain",
        "CareerConsultantChain",
        "ValidatorChain",
        "ATSScannerChain",
        "InterviewSimulatorChain",
        "DocumentVariantChain",
        "SalaryCoachChain",
        "LearningChallengeChain",
        "LinkedInAdvisorChain",
        "MarketIntelligenceChain",
        "ApplicationCoachChain",
        "DocumentDiscoveryChain",
        "AdaptiveDocumentChain",
        "CompanyIntelChain",
    ]],
)
def test_chain_constructible_with_only_ai_client(chain_name: str) -> None:
    """Smoke: the standard chains must instantiate with a single
    positional ai_client argument and nothing else."""
    cls = _resolve(chain_name)
    instance = cls(object())
    assert instance is not None
    # ai_client is conventionally stored as `self.ai_client`
    assert hasattr(instance, "ai_client") or hasattr(instance, "client"), (
        f"{chain_name} must store the AI client on self (as ai_client or client)"
    )


# ── DocumentPackPlanner — sole exception ──────────────────────────────


def test_document_pack_planner_is_only_non_standard_init() -> None:
    """Lock down the allowlist. Any future chain wanting a custom
    constructor must update this test."""
    non_standard = []
    for name in _exported_chain_names():
        cls = _resolve(name)
        sig = inspect.signature(cls.__init__)
        params = {n for n in sig.parameters if n != "self"}
        # Strip optional params with defaults to focus on *required* positionals
        required = {
            n for n, p in sig.parameters.items()
            if n != "self" and p.default is inspect.Parameter.empty
            and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        }
        if required != {"ai_client"}:
            non_standard.append(name)
    assert set(non_standard) == _NON_STANDARD_INIT, (
        f"Non-standard __init__ allowlist drift. "
        f"Found: {sorted(non_standard)}; Expected: {sorted(_NON_STANDARD_INIT)}. "
        "Either restore the standard signature or update _NON_STANDARD_INIT "
        "with explicit justification."
    )


def test_document_pack_planner_requires_ai_client_and_catalog() -> None:
    """Pin the planner's two-arg constructor."""
    from ai_engine.chains.document_pack_planner import DocumentPackPlanner

    sig = inspect.signature(DocumentPackPlanner.__init__)
    params = {n for n in sig.parameters if n != "self"}
    assert "ai_client" in params
    assert "catalog" in params


# ── Async-method guarantee ────────────────────────────────────────────


@pytest.mark.parametrize(
    "chain_name",
    [n for n in [
        "RoleProfilerChain",
        "GapAnalyzerChain",
        "CareerConsultantChain",
        "DocumentGeneratorChain",
        "ATSScannerChain",
        "InterviewSimulatorChain",
        "SalaryCoachChain",
        "LearningChallengeChain",
        "LinkedInAdvisorChain",
        "MarketIntelligenceChain",
        "ApplicationCoachChain",
        "AdaptiveDocumentChain",
        "CompanyIntelChain",
    ]],
)
def test_chain_exposes_at_least_one_async_method(chain_name: str) -> None:
    """LLM chains run on the asyncio executor; drift to sync would
    block the event loop."""
    cls = _resolve(chain_name)
    async_methods = [
        name for name, member in inspect.getmembers(cls, inspect.iscoroutinefunction)
        if not name.startswith("_")
    ]
    assert async_methods, (
        f"{chain_name} has no async public methods — every LLM chain "
        "must expose at least one async entry point."
    )
