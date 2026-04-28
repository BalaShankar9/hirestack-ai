"""S4-F3 — Pin `_default_module_states` + `_merge_module_states` invariants.

Every application row carries a `modules` dict with one entry per
generation slot, holding `{state, updatedAt, ...}`. The frontend's
module-cards crash on missing keys, so the runtime MUST guarantee
all 9 slots are present in every persist.

`_merge_module_states` is the boundary that takes whatever the DB
row carries (may be sparse from older rows, may be `None` from a
just-created row) and returns the full 9-key dict, with caller-
provided values winning over defaults.
"""
from __future__ import annotations

from app.api.routes.generate.jobs import (
    _DEFAULT_REQUESTED_MODULES,
    _default_module_states,
    _merge_module_states,
)


# ── _default_module_states ────────────────────────────────────────────


def test_default_module_states_has_one_entry_per_default_module() -> None:
    """The default state dict must cover every module the runtime
    knows how to generate. If a new module is added to
    _DEFAULT_REQUESTED_MODULES without a default state, the frontend
    will render an undefined card on a fresh row."""
    states = _default_module_states()
    assert set(states.keys()) == set(_DEFAULT_REQUESTED_MODULES)


def test_default_module_states_all_idle() -> None:
    states = _default_module_states()
    for key, value in states.items():
        assert value == {"state": "idle"}, f"{key} must default to idle"


def test_default_module_states_returns_fresh_dict_each_call() -> None:
    """Mutating one caller's defaults must not leak to the next."""
    a = _default_module_states()
    a["cv"]["state"] = "ready"
    b = _default_module_states()
    assert b["cv"] == {"state": "idle"}


# ── _merge_module_states ──────────────────────────────────────────────


def test_merge_with_none_returns_full_default() -> None:
    merged = _merge_module_states(None)
    assert set(merged.keys()) == set(_DEFAULT_REQUESTED_MODULES)
    for value in merged.values():
        assert value == {"state": "idle"}


def test_merge_with_empty_dict_returns_full_default() -> None:
    merged = _merge_module_states({})
    assert set(merged.keys()) == set(_DEFAULT_REQUESTED_MODULES)


def test_merge_existing_overrides_defaults() -> None:
    existing = {
        "cv": {"state": "ready", "updatedAt": 12345},
        "coverLetter": {"state": "generating"},
    }
    merged = _merge_module_states(existing)
    # Existing wins
    assert merged["cv"] == {"state": "ready", "updatedAt": 12345}
    assert merged["coverLetter"] == {"state": "generating"}
    # Untouched keys still default to idle
    assert merged["resume"] == {"state": "idle"}
    assert merged["portfolio"] == {"state": "idle"}


def test_merge_preserves_all_default_slots_when_existing_is_sparse() -> None:
    """The legacy invariant: even if an old DB row only ever wrote
    `cv`, the merge must still expose the full 9-key surface so the
    frontend doesn't crash."""
    merged = _merge_module_states({"cv": {"state": "ready"}})
    assert set(merged.keys()) == set(_DEFAULT_REQUESTED_MODULES)


def test_merge_with_non_dict_existing_returns_full_default() -> None:
    """Defensive: a malformed row that put a list / None / str into
    `modules` must not crash the runtime."""
    assert _merge_module_states("not-a-dict") == _default_module_states()  # type: ignore[arg-type]
    assert _merge_module_states([]) == _default_module_states()  # type: ignore[arg-type]
    assert _merge_module_states(0) == _default_module_states()  # type: ignore[arg-type]


def test_merge_carries_unknown_keys_through_unchanged() -> None:
    """If a future column-rename leaves stale keys in the row, the
    merge must NOT silently drop them — that would be data loss.
    They survive untouched until something explicitly cleans up."""
    merged = _merge_module_states({"_legacy_module": {"state": "ready"}})
    assert merged["_legacy_module"] == {"state": "ready"}
    # All canonical defaults still present
    assert set(_DEFAULT_REQUESTED_MODULES).issubset(merged.keys())


def test_merge_does_not_mutate_caller_input() -> None:
    existing = {"cv": {"state": "ready"}}
    snapshot = {"cv": {"state": "ready"}}
    _merge_module_states(existing)
    # Caller's dict must not be mutated by the merge
    assert existing == snapshot
