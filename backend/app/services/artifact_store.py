"""
ArtifactStore — durable persistence for typed agent artifacts.

Backs onto the `agent_artifacts` table created by
20260420100000_orchestration_foundation.sql. Used by the v4 runtime to:

  - Write every typed artifact produced by an agent (Pydantic model dump)
  - Track artifact lineage (parent_artifact_id) for replay / provenance
  - Query the latest artifact of a given type for an application
  - Support resume-from-artifact flows in the JobWatchdog

Design notes:
  - Every persistence operation is best-effort: failures are logged and
    swallowed so a DB hiccup never aborts a live pipeline. The runtime
    can keep moving with in-memory artifacts; persistence is for replay
    and the future Mission Control / debugger UI.
  - `put` returns the inserted row id (or empty string on failure) so
    downstream agents can register lineage.
  - `latest` returns the most recent artifact of a given type for an
    application — useful for resume scenarios.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import structlog

from ai_engine.agents.artifact_contracts import (
    ARTIFACT_TYPES,
    ArtifactBase,
    EvidenceTier,
)

logger = structlog.get_logger(__name__)


class ArtifactStore:
    """Persists typed artifacts to the agent_artifacts table."""

    def __init__(self, db: Any, tables: Dict[str, str]) -> None:
        self._db = db
        self._tables = tables

    @property
    def _table(self) -> str:
        return self._tables.get("agent_artifacts", "agent_artifacts")

    async def put(
        self,
        artifact: ArtifactBase,
        *,
        user_id: str,
        agent_name: Optional[str] = None,
        artifact_type: Optional[str] = None,
        parent_artifact_id: Optional[str] = None,
    ) -> str:
        """Persist an artifact. Returns the inserted row id, or "" on failure."""
        type_name = artifact_type or self._infer_type_name(artifact)
        if not type_name:
            logger.warning("artifact_store.unknown_type",
                           cls=type(artifact).__name__)
            return ""

        try:
            content = artifact.model_dump(mode="json")
        except Exception as dump_err:
            logger.warning("artifact_store.dump_failed",
                           type=type_name, error=str(dump_err)[:200])
            return ""

        # Compute evidence tier as plain string (DB column is TEXT).
        tier = artifact.evidence_tier
        if isinstance(tier, EvidenceTier):
            tier_value = tier.value
        else:
            tier_value = str(tier or EvidenceTier.UNKNOWN.value)

        row: Dict[str, Any] = {
            "user_id": user_id,
            "application_id": artifact.application_id,
            "agent_name": agent_name or artifact.created_by_agent or "unknown",
            "artifact_type": type_name,
            "version": artifact.version,
            "content": content,
            "confidence": float(artifact.confidence or 0.0),
            "evidence_tier": tier_value,
        }
        if parent_artifact_id:
            row["parent_artifact_id"] = parent_artifact_id

        try:
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._table).insert(row).execute()
            )
            data = resp.data or [{}]
            inserted_id = str(data[0].get("id") or "")
            if inserted_id:
                logger.info("artifact_store.persisted",
                            type=type_name,
                            agent=row["agent_name"],
                            application_id=artifact.application_id,
                            artifact_id=inserted_id)
            return inserted_id
        except Exception as ex:
            logger.warning("artifact_store.persist_failed",
                           type=type_name, error=str(ex)[:200])
            return ""

    async def latest(
        self,
        *,
        user_id: str,
        application_id: str,
        artifact_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent artifact row of a given type for an application."""
        try:
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._table)
                .select("*")
                .eq("user_id", user_id)
                .eq("application_id", application_id)
                .eq("artifact_type", artifact_type)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            return rows[0] if rows else None
        except Exception as ex:
            logger.warning("artifact_store.latest_failed",
                           type=artifact_type, error=str(ex)[:200])
            return None

    async def list_for_application(
        self,
        *,
        user_id: str,
        application_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List all artifacts for an application, newest first."""
        try:
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._table)
                .select("id,agent_name,artifact_type,version,confidence,evidence_tier,created_at,parent_artifact_id")
                .eq("user_id", user_id)
                .eq("application_id", application_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(resp.data or [])
        except Exception as ex:
            logger.warning("artifact_store.list_failed",
                           application_id=application_id, error=str(ex)[:200])
            return []

    @staticmethod
    def _infer_type_name(artifact: ArtifactBase) -> str:
        """Look up the canonical type name from ARTIFACT_TYPES by class identity."""
        for name, cls in ARTIFACT_TYPES.items():
            if type(artifact) is cls:
                return name
        # Fallback: try class name match.
        cls_name = type(artifact).__name__
        if cls_name in ARTIFACT_TYPES:
            return cls_name
        return ""
