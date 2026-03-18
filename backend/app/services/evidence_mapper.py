"""
Evidence Mapper Service
AI-powered mapping of evidence items to skill gaps (Supabase)
"""
from typing import Optional, Dict, Any, List
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from ai_engine.client import get_ai_client
from ai_engine.chains.evidence_mapper import EvidenceMapperChain

logger = structlog.get_logger()


class EvidenceMapperService:
    """Service for mapping evidence to skill gaps."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.ai_client = get_ai_client()

    async def auto_map(
        self,
        user_id: str,
        gap_report_id: str,
        application_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Auto-map all user evidence to gaps in a report."""
        # Fetch gap report
        gap_report = await self.db.get(TABLES["gap_reports"], gap_report_id)
        if not gap_report or gap_report.get("user_id") != user_id:
            raise ValueError("Gap report not found")

        skill_gaps = gap_report.get("skill_gaps", [])
        if not skill_gaps:
            return {"mappings": [], "unmapped_gaps": [], "coverage_summary": {}}

        # Fetch user evidence
        evidence_items = await self.db.query(
            TABLES["evidence"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
        )
        if not evidence_items:
            return {
                "mappings": [],
                "unmapped_gaps": [{"skill_name": g.get("skill", ""), "gap_severity": g.get("gap_severity", "")} for g in skill_gaps],
                "coverage_summary": {"total_gaps": len(skill_gaps), "gaps_with_evidence": 0, "coverage_percentage": 0},
            }

        # Simplify evidence for AI
        evidence_for_ai = [
            {
                "id": e["id"],
                "title": e.get("title", ""),
                "type": e.get("type", ""),
                "description": e.get("description", ""),
                "skills": e.get("skills", []),
                "tools": e.get("tools", []),
            }
            for e in evidence_items
        ]

        chain = EvidenceMapperChain(self.ai_client)
        result = await chain.map_evidence(skill_gaps, evidence_for_ai)

        # Delete old mappings for this gap report
        old_mappings = await self.db.query(
            TABLES["evidence_mappings"],
            filters=[("gap_report_id", "==", gap_report_id), ("user_id", "==", user_id)],
        )
        for old in old_mappings:
            await self.db.delete(TABLES["evidence_mappings"], old["id"])

        # Save new mappings
        saved = []
        for m in result.get("mappings", []):
            record = {
                "user_id": user_id,
                "evidence_id": m["evidence_id"],
                "gap_report_id": gap_report_id,
                "application_id": application_id,
                "skill_name": m["skill_name"],
                "gap_severity": m.get("gap_severity", ""),
                "relevance_score": m.get("relevance_score", 0),
                "ai_explanation": m.get("explanation", ""),
                "is_confirmed": False,
            }
            doc_id = await self.db.create(TABLES["evidence_mappings"], record)
            saved.append({**record, "id": doc_id})

        logger.info("evidence_mapped", count=len(saved), gap_report_id=gap_report_id)
        return {
            "mappings": saved,
            "unmapped_gaps": result.get("unmapped_gaps", []),
            "unmapped_evidence": result.get("unmapped_evidence", []),
            "coverage_summary": result.get("coverage_summary", {}),
        }

    async def get_mappings(self, user_id: str, gap_report_id: str) -> List[Dict[str, Any]]:
        """Get all evidence mappings for a gap report."""
        return await self.db.query(
            TABLES["evidence_mappings"],
            filters=[("gap_report_id", "==", gap_report_id), ("user_id", "==", user_id)],
            order_by="relevance_score",
            order_direction="DESCENDING",
        )

    async def confirm_mapping(self, mapping_id: str, user_id: str, confirmed: bool = True) -> bool:
        """Confirm or reject an AI-suggested mapping."""
        mapping = await self.db.get(TABLES["evidence_mappings"], mapping_id)
        if not mapping or mapping.get("user_id") != user_id:
            return False
        await self.db.update(TABLES["evidence_mappings"], mapping_id, {"is_confirmed": confirmed})
        return True
