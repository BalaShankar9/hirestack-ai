"""Tests for the empty-by-design RESOLVERS allowlist (ADR-0033)."""

from __future__ import annotations

import pytest

from ai_engine.registry.resolvers import RESOLVERS, UnknownCodeRef, resolve


def test_resolvers_empty_by_design() -> None:
    # The empty-but-strict map IS the AP-4 governance hook. If anyone
    # adds a real entry, they MUST also justify it in the PR — otherwise
    # the registry stops working in dispatch surface tests.
    assert RESOLVERS == {}


def test_resolve_unknown_raises() -> None:
    with pytest.raises(UnknownCodeRef, match="ai_engine.agents.tools:does_not_exist"):
        resolve("ai_engine.agents.tools:does_not_exist")


def test_resolve_empty_string_raises() -> None:
    with pytest.raises(UnknownCodeRef):
        resolve("")
