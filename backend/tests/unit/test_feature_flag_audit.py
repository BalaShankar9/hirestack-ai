"""Tests for P1-9 / m12-pr09 feature flag audit service."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ─── Fakes ──────────────────────────────────────────────────────────────


class _FakeQuery:
    """Tiny fluent stub mirroring the supabase-py builder we use."""

    def __init__(self, parent: "_FakeSupabase") -> None:
        self._parent = parent
        self._filters: List[tuple] = []
        self._order_desc = False
        self._limit_n: Optional[int] = None

    def select(self, *_args, **_kwargs) -> "_FakeQuery":
        return self

    def eq(self, key: str, value: Any) -> "_FakeQuery":
        self._filters.append((key, value, "eq"))
        return self

    def is_(self, key: str, value: Any) -> "_FakeQuery":
        self._filters.append((key, value, "is"))
        return self

    def order(self, _key: str, *, desc: bool = False) -> "_FakeQuery":
        self._order_desc = desc
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit_n = n
        return self

    def insert(self, row: Dict[str, Any]) -> "_FakeQuery":
        self._parent.inserted.append(row)
        return self

    def execute(self) -> MagicMock:
        # SELECT path: return latest matching row(s) from `rows`.
        matched = []
        for row in self._parent.rows:
            ok = True
            for k, v, kind in self._filters:
                if kind == "is":
                    if v == "null":
                        if row.get(k) is not None:
                            ok = False
                            break
                else:
                    if row.get(k) != v:
                        ok = False
                        break
            if ok:
                matched.append(row)
        if self._order_desc:
            matched.sort(key=lambda r: r.get("recorded_at", ""), reverse=True)
        if self._limit_n is not None:
            matched = matched[: self._limit_n]
        return MagicMock(data=matched)


class _FakeSupabase:
    """Fake supabase client recording inserts and serving fixed rows."""

    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self.rows = list(rows or [])
        self.inserted: List[Dict[str, Any]] = []

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self)


@pytest.fixture(autouse=True)
def _reset_singleton():
    from backend.app.services.feature_flag_audit import _reset_for_tests
    _reset_for_tests()
    yield
    _reset_for_tests()


def _svc(rows: Optional[List[Dict[str, Any]]] = None):
    from backend.app.services.feature_flag_audit import FeatureFlagAuditService
    sb = _FakeSupabase(rows)
    return FeatureFlagAuditService(client=sb), sb


# ─── _normalize_value ───────────────────────────────────────────────────


def test_normalize_bool_true():
    from backend.app.services.feature_flag_audit import _normalize_value
    assert _normalize_value(True) == "true"
    assert _normalize_value(False) == "false"


def test_normalize_none_to_empty():
    from backend.app.services.feature_flag_audit import _normalize_value
    assert _normalize_value(None) == ""


def test_normalize_passthrough_string():
    from backend.app.services.feature_flag_audit import _normalize_value
    assert _normalize_value("on") == "on"
    assert _normalize_value(42) == "42"


# ─── record_change ──────────────────────────────────────────────────────


def test_record_change_writes_when_no_prior_entry():
    svc, sb = _svc()
    written = asyncio.run(svc.record_change("ff_billing", True, actor="ops", reason="enable"))
    assert written is True
    assert len(sb.inserted) == 1
    row = sb.inserted[0]
    assert row["flag_name"] == "ff_billing"
    assert row["new_value"] == "true"
    assert row["old_value"] is None
    assert row["scope"] == "global"
    assert row["tenant_id"] is None
    assert row["actor"] == "ops"
    assert row["reason"] == "enable"


def test_record_change_skips_when_value_unchanged():
    svc, sb = _svc(rows=[{
        "flag_name": "ff_billing", "scope": "global", "tenant_id": None,
        "old_value": None, "new_value": "true",
        "actor": "ops", "reason": "enable", "recorded_at": "2026-06-25T00:00:00Z",
    }])
    written = asyncio.run(svc.record_change("ff_billing", True))
    assert written is False
    assert sb.inserted == []


def test_record_change_writes_diff_with_old_value():
    svc, sb = _svc(rows=[{
        "flag_name": "ff_billing", "scope": "global", "tenant_id": None,
        "old_value": None, "new_value": "false",
        "actor": "system", "reason": None, "recorded_at": "2026-06-25T00:00:00Z",
    }])
    written = asyncio.run(svc.record_change("ff_billing", True, actor="admin"))
    assert written is True
    row = sb.inserted[0]
    assert row["old_value"] == "false"
    assert row["new_value"] == "true"
    assert row["actor"] == "admin"


def test_record_change_force_writes_even_when_unchanged():
    svc, sb = _svc(rows=[{
        "flag_name": "ff_billing", "scope": "global", "tenant_id": None,
        "old_value": None, "new_value": "true",
        "actor": "ops", "reason": None, "recorded_at": "2026-06-25T00:00:00Z",
    }])
    written = asyncio.run(svc.record_change("ff_billing", True, force=True))
    assert written is True
    # force skips diff lookup → old_value stays None on the new row.
    assert sb.inserted[0]["old_value"] is None


def test_record_change_tenant_scope_requires_tenant_id():
    svc, sb = _svc()
    written = asyncio.run(svc.record_change("ff_x", True, scope="tenant"))
    assert written is False
    assert sb.inserted == []


def test_record_change_global_scope_rejects_tenant_id():
    svc, sb = _svc()
    written = asyncio.run(
        svc.record_change("ff_x", True, scope="global", tenant_id="t-1")
    )
    assert written is False


def test_record_change_invalid_scope():
    svc, sb = _svc()
    written = asyncio.run(svc.record_change("ff_x", True, scope="weird"))
    assert written is False


def test_record_change_empty_flag_name_noop():
    svc, sb = _svc()
    written = asyncio.run(svc.record_change("", True))
    assert written is False


def test_record_change_tenant_scope_writes_when_tenant_id_supplied():
    svc, sb = _svc()
    written = asyncio.run(
        svc.record_change("ff_x", "on", scope="tenant", tenant_id="t-1")
    )
    assert written is True
    row = sb.inserted[0]
    assert row["scope"] == "tenant"
    assert row["tenant_id"] == "t-1"
    assert row["new_value"] == "on"


def test_record_change_no_supabase_returns_false():
    from backend.app.services.feature_flag_audit import FeatureFlagAuditService
    svc = FeatureFlagAuditService(client=None)
    with patch.object(svc, "_supabase", return_value=None):
        written = asyncio.run(svc.record_change("ff_x", True))
    assert written is False


def test_record_change_insert_failure_returns_false():
    from backend.app.services.feature_flag_audit import FeatureFlagAuditService

    class _Boom:
        def table(self, _):
            return self
        def select(self, *_a, **_k):
            return self
        def eq(self, *_a, **_k):
            return self
        def is_(self, *_a, **_k):
            return self
        def order(self, *_a, **_k):
            return self
        def limit(self, *_a, **_k):
            return self
        def insert(self, _row):
            return self
        def execute(self):
            raise RuntimeError("db down")

    svc = FeatureFlagAuditService(client=_Boom())
    written = asyncio.run(svc.record_change("ff_x", True))
    assert written is False


# ─── get_latest / get_history ──────────────────────────────────────────


def test_get_latest_returns_none_when_empty():
    svc, _ = _svc()
    res = asyncio.run(svc.get_latest("ff_missing"))
    assert res is None


def test_get_latest_filters_by_scope_and_tenant():
    svc, _ = _svc(rows=[
        {"flag_name": "ff_x", "scope": "global", "tenant_id": None,
         "new_value": "true", "old_value": None, "actor": "s",
         "reason": None, "recorded_at": "2026-06-25T00:00:00Z"},
        {"flag_name": "ff_x", "scope": "tenant", "tenant_id": "t-1",
         "new_value": "false", "old_value": None, "actor": "s",
         "reason": None, "recorded_at": "2026-06-25T01:00:00Z"},
    ])
    g = asyncio.run(svc.get_latest("ff_x", scope="global"))
    t = asyncio.run(svc.get_latest("ff_x", scope="tenant", tenant_id="t-1"))
    assert g["new_value"] == "true"
    assert t["new_value"] == "false"


def test_get_history_returns_newest_first():
    svc, _ = _svc(rows=[
        {"flag_name": "ff_x", "scope": "global", "tenant_id": None,
         "new_value": "false", "old_value": None, "actor": "s",
         "reason": None, "recorded_at": "2026-06-25T00:00:00Z"},
        {"flag_name": "ff_x", "scope": "global", "tenant_id": None,
         "new_value": "true", "old_value": "false", "actor": "ops",
         "reason": "enable", "recorded_at": "2026-06-26T00:00:00Z"},
    ])
    rows = asyncio.run(svc.get_history("ff_x"))
    assert len(rows) == 2
    assert rows[0]["new_value"] == "true"
    assert rows[1]["new_value"] == "false"


# ─── record_snapshot_from_registry ──────────────────────────────────────


def test_snapshot_baselines_unset_flags(tmp_path, monkeypatch):
    reg = tmp_path / "feature_flags.yaml"
    reg.write_text(
        "flags:\n"
        "  ff_alpha:\n"
        "    owner: x\n"
        "    created: 2026-01-01\n"
        "    sunset: 2026-12-31\n"
        "    default: false\n"
        "    purpose: test\n"
    )
    monkeypatch.delenv("FF_ALPHA", raising=False)
    svc, sb = _svc()
    counts = asyncio.run(svc.record_snapshot_from_registry(registry_path=reg))
    assert counts["written"] == 1
    assert counts["missing_env"] == 1
    assert sb.inserted[0]["new_value"] == ""


def test_snapshot_writes_env_value(tmp_path, monkeypatch):
    reg = tmp_path / "feature_flags.yaml"
    reg.write_text(
        "flags:\n"
        "  ff_beta:\n"
        "    owner: x\n"
        "    created: 2026-01-01\n"
        "    sunset: 2026-12-31\n"
        "    default: false\n"
        "    purpose: test\n"
    )
    monkeypatch.setenv("FF_BETA", "true")
    svc, sb = _svc()
    counts = asyncio.run(svc.record_snapshot_from_registry(registry_path=reg))
    assert counts["written"] == 1
    assert counts["missing_env"] == 0
    assert sb.inserted[0]["new_value"] == "true"
    assert sb.inserted[0]["actor"] == "deploy-snapshot"


def test_snapshot_skips_when_value_unchanged(tmp_path, monkeypatch):
    reg = tmp_path / "feature_flags.yaml"
    reg.write_text(
        "flags:\n"
        "  ff_gamma:\n"
        "    owner: x\n"
        "    created: 2026-01-01\n"
        "    sunset: 2026-12-31\n"
        "    default: false\n"
        "    purpose: test\n"
    )
    monkeypatch.setenv("FF_GAMMA", "true")
    svc, sb = _svc(rows=[{
        "flag_name": "ff_gamma", "scope": "global", "tenant_id": None,
        "old_value": None, "new_value": "true",
        "actor": "deploy-snapshot", "reason": None,
        "recorded_at": "2026-06-25T00:00:00Z",
    }])
    counts = asyncio.run(svc.record_snapshot_from_registry(registry_path=reg))
    assert counts["written"] == 0
    assert counts["skipped"] == 1
    assert sb.inserted == []


def test_snapshot_missing_registry_returns_zero_counts(tmp_path):
    svc, _ = _svc()
    counts = asyncio.run(
        svc.record_snapshot_from_registry(registry_path=tmp_path / "nope.yaml")
    )
    assert counts == {"written": 0, "skipped": 0, "missing_env": 0}


# ─── singleton ──────────────────────────────────────────────────────────


def test_singleton_returns_same_instance():
    from backend.app.services.feature_flag_audit import (
        get_feature_flag_audit_service,
    )
    a = get_feature_flag_audit_service()
    b = get_feature_flag_audit_service()
    assert a is b
