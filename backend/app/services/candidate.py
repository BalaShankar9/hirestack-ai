"""
Candidate Service
Manages candidates for recruitment agencies — lifecycle, pipeline stages, bulk operations.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()

PIPELINE_STAGES = ["sourced", "screened", "submitted", "interviewing", "offered", "placed", "rejected"]


class CandidateService:
    """Service for candidate pipeline operations."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def create(self, org_id: str, data: Dict[str, Any], created_by: str) -> Dict[str, Any]:
        record = {
            "org_id": org_id,
            "name": data.get("name", ""),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "location": data.get("location"),
            "client_company": data.get("client_company"),
            "pipeline_stage": data.get("pipeline_stage", "sourced"),
            "tags": data.get("tags", []),
            "notes": data.get("notes"),
            "assigned_recruiter": data.get("assigned_recruiter"),
            "resume_text": data.get("resume_text"),
            "skills": data.get("skills", []),
            "created_by": created_by,
        }
        doc_id = await self.db.create(TABLES["candidates"], record)
        return await self.db.get(TABLES["candidates"], doc_id) or {**record, "id": doc_id}

    async def list(self, org_id: str, stage: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        filters = [("org_id", "==", org_id)]
        if stage and stage != "all":
            filters.append(("pipeline_stage", "==", stage))
        return await self.db.query(TABLES["candidates"], filters=filters, order_by="created_at", order_direction="DESCENDING", limit=limit)

    async def get(self, candidate_id: str, org_id: str) -> Optional[Dict[str, Any]]:
        c = await self.db.get(TABLES["candidates"], candidate_id)
        if c and c.get("org_id") == org_id:
            return c
        return None

    async def update(self, candidate_id: str, org_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        c = await self.get(candidate_id, org_id)
        if not c:
            return None
        safe = {k: v for k, v in data.items() if k in (
            "name", "email", "phone", "location", "client_company",
            "pipeline_stage", "tags", "notes", "assigned_recruiter",
            "resume_text", "skills", "status", "metadata",
        )}
        await self.db.update(TABLES["candidates"], candidate_id, safe)
        return await self.db.get(TABLES["candidates"], candidate_id)

    async def move_stage(self, candidate_id: str, org_id: str, new_stage: str) -> Optional[Dict[str, Any]]:
        if new_stage not in PIPELINE_STAGES:
            raise ValueError(f"Invalid stage: {new_stage}")
        return await self.update(candidate_id, org_id, {"pipeline_stage": new_stage})

    async def delete(self, candidate_id: str, org_id: str) -> bool:
        c = await self.get(candidate_id, org_id)
        if not c:
            return False
        return await self.db.delete(TABLES["candidates"], candidate_id)

    async def get_pipeline_stats(self, org_id: str) -> Dict[str, int]:
        all_candidates = await self.db.query(TABLES["candidates"], filters=[("org_id", "==", org_id)])
        stats: Dict[str, int] = {stage: 0 for stage in PIPELINE_STAGES}
        stats["total"] = len(all_candidates)
        for c in all_candidates:
            stage = c.get("pipeline_stage", "sourced")
            if stage in stats:
                stats[stage] += 1
        return stats
