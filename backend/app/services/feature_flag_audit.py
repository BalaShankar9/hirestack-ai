"""Feature flag audit service.

P1-9 / m12-pr09. Append-only history of feature flag value changes.

Two write paths today:

* :meth:`record_change` — explicit flip via admin API or ops tooling.
* :meth:`record_snapshot_from_registry` — boot-time / ops sweep that
  reads the YAML registry + current env values and persists one row
  per flag whose value differs from the most recent recorded entry.

Reads (last value, history) are kept here too so admin UIs and ops
scripts have a single import surface.

Idempotency: writers compare against the latest row for the
``(flag_name, scope, tenant_id)`` triple and skip the insert when the
new value matches. This keeps per-deploy snapshot calls cheap and
avoids polluting the table with duplicate rows.

All writes are best-effort: a Supabase outage logs and returns False;
no exception propagates. The audit log must never become a
side-channel that breaks the request path.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.database import get_supabase

logger = logging.getLogger(__name__)


_TABLE = "feature_flag_audit"
_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "feature_flags.yaml"
)


def _normalize_value(value: Any) -> str:
    """Coerce flag values to the canonical text representation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


class FeatureFlagAuditService:
    """Read/write surface for ``public.feature_flag_audit``.

    Stateless; one process-wide singleton via
    :func:`get_feature_flag_audit_service`.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self._client = client

    def _supabase(self) -> Optional[Any]:
        if self._client is not None:
            return self._client
        try:
            return get_supabase()
        except Exception as exc:
            logger.debug("feature_flag_audit_supabase_unavailable: %s", exc)
            return None

    async def get_latest(
        self,
        flag_name: str,
        *,
        scope: str = "global",
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent audit entry for the given key, or None."""
        sb = self._supabase()
        if sb is None:
            return None
        try:
            q = (
                sb.table(_TABLE)
                .select("flag_name,scope,tenant_id,old_value,new_value,actor,reason,recorded_at")
                .eq("flag_name", flag_name)
                .eq("scope", scope)
                .order("recorded_at", desc=True)
                .limit(1)
            )
            if scope == "tenant":
                if not tenant_id:
                    return None
                q = q.eq("tenant_id", tenant_id)
            else:
                q = q.is_("tenant_id", "null")
            res = q.execute()
            rows = res.data or []
        except Exception as exc:
            logger.warning(
                "feature_flag_audit_get_latest_failed: flag=%s err=%s",
                flag_name, str(exc)[:200],
            )
            return None
        return rows[0] if rows else None

    async def get_history(
        self,
        flag_name: str,
        *,
        scope: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return audit history, newest first."""
        sb = self._supabase()
        if sb is None:
            return []
        try:
            q = (
                sb.table(_TABLE)
                .select("flag_name,scope,tenant_id,old_value,new_value,actor,reason,recorded_at")
                .eq("flag_name", flag_name)
                .order("recorded_at", desc=True)
                .limit(max(1, limit))
            )
            if scope is not None:
                q = q.eq("scope", scope)
            if tenant_id is not None:
                q = q.eq("tenant_id", tenant_id)
            res = q.execute()
            return res.data or []
        except Exception as exc:
            logger.warning(
                "feature_flag_audit_get_history_failed: flag=%s err=%s",
                flag_name, str(exc)[:200],
            )
            return []

    async def record_change(
        self,
        flag_name: str,
        new_value: Any,
        *,
        scope: str = "global",
        tenant_id: Optional[str] = None,
        actor: str = "system",
        reason: Optional[str] = None,
        force: bool = False,
    ) -> bool:
        """Insert one audit row when ``new_value`` differs from the latest.

        Returns True when a row was written, False when skipped (no diff,
        no Supabase, or insert failed). Writes are best-effort; nothing
        raises into the caller.

        ``force=True`` writes the row even when the value is unchanged
        (use sparingly — e.g. forced re-baselining of the audit trail).
        """
        if not flag_name:
            return False
        if scope not in ("global", "tenant"):
            logger.warning("feature_flag_audit_invalid_scope: %s", scope)
            return False
        if scope == "tenant" and not tenant_id:
            logger.warning("feature_flag_audit_missing_tenant_id: flag=%s", flag_name)
            return False
        if scope == "global" and tenant_id is not None:
            logger.warning("feature_flag_audit_unexpected_tenant_id: flag=%s", flag_name)
            return False

        sb = self._supabase()
        if sb is None:
            return False

        new_norm = _normalize_value(new_value)

        old_value: Optional[str] = None
        if not force:
            latest = await self.get_latest(
                flag_name, scope=scope, tenant_id=tenant_id,
            )
            if latest is not None:
                old_value = latest.get("new_value")
                if old_value == new_norm:
                    return False

        row: Dict[str, Any] = {
            "flag_name": flag_name,
            "scope": scope,
            "tenant_id": tenant_id,
            "old_value": old_value,
            "new_value": new_norm,
            "actor": actor or "system",
            "reason": reason,
        }
        try:
            sb.table(_TABLE).insert(row).execute()
            return True
        except Exception as exc:
            logger.warning(
                "feature_flag_audit_insert_failed: flag=%s err=%s",
                flag_name, str(exc)[:200],
            )
            return False

    async def record_snapshot_from_registry(
        self,
        *,
        actor: str = "deploy-snapshot",
        reason: Optional[str] = None,
        registry_path: Optional[Path] = None,
    ) -> Dict[str, int]:
        """Walk the YAML registry, write a row per flag whose env value
        differs from the latest audit entry.

        Returns a counter dict ``{"written": N, "skipped": M, "missing_env": K}``.

        Each flag's current value is read from the env var matching its
        name (uppercased — pydantic-settings convention). Flags with no
        corresponding env var are recorded as ``""`` (i.e. "default")
        only when the latest audit row carries a different value.
        """
        try:
            import yaml  # type: ignore
        except ImportError:
            logger.warning("feature_flag_audit_yaml_missing")
            return {"written": 0, "skipped": 0, "missing_env": 0}

        path = registry_path or _REGISTRY_PATH
        if not path.exists():
            logger.warning("feature_flag_audit_registry_missing: %s", path)
            return {"written": 0, "skipped": 0, "missing_env": 0}

        try:
            registry = yaml.safe_load(path.read_text()) or {}
        except Exception as exc:
            logger.warning("feature_flag_audit_registry_parse_failed: %s", exc)
            return {"written": 0, "skipped": 0, "missing_env": 0}

        flags = registry.get("flags") or {}
        counters = {"written": 0, "skipped": 0, "missing_env": 0}

        for name in sorted(flags.keys()):
            env_key = name.upper()
            raw = os.getenv(env_key)
            if raw is None:
                counters["missing_env"] += 1
                # Only audit a "default" entry on first sight — once
                # baselined the snapshot becomes a no-op.
                latest = await self.get_latest(name)
                if latest is None:
                    written = await self.record_change(
                        name, "",
                        actor=actor,
                        reason=reason or "registry baseline (no env override)",
                    )
                    if written:
                        counters["written"] += 1
                    else:
                        counters["skipped"] += 1
                else:
                    counters["skipped"] += 1
                continue

            written = await self.record_change(
                name, raw,
                actor=actor,
                reason=reason or "deploy snapshot",
            )
            if written:
                counters["written"] += 1
            else:
                counters["skipped"] += 1

        return counters


_SINGLETON: Optional[FeatureFlagAuditService] = None


def get_feature_flag_audit_service() -> FeatureFlagAuditService:
    """Return a process-wide singleton."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = FeatureFlagAuditService()
    return _SINGLETON


def _reset_for_tests() -> None:
    """Test helper: drop the singleton."""
    global _SINGLETON
    _SINGLETON = None
