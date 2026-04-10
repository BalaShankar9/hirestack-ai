"""
ATS Scanner Service
Handles ATS compatibility scanning — migrated to Supabase.
"""
from typing import Dict, Any, List, Optional
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from ai_engine.client import AIClient
from ai_engine.chains.ats_scanner import ATSScannerChain

logger = structlog.get_logger()

# Columns that always exist in ats_scans table
_BASE_COLUMNS = {"user_id", "document_content", "status", "created_at", "updated_at"}
# Columns from elite_upgrades migration (may not exist)
_EXTENDED_COLUMNS = {
    "application_id", "document_id", "job_description_id",
    "ats_score", "keyword_match_rate", "readability_score", "format_score",
    "section_scores", "matched_keywords", "missing_keywords",
    "formatting_issues", "recommendations", "pass_prediction", "recruiter_view_html",
}

_extended_available: Optional[bool] = None


class ATSService:
    """Service for ATS scanning operations."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.ai_client = AIClient()

    async def _has_extended_columns(self) -> bool:
        """Check if the extended ATS columns exist (from elite_upgrades migration)."""
        global _extended_available
        if _extended_available is not None:
            return _extended_available
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            def _check():
                self.db.client.table("ats_scans").select("ats_score").limit(1).execute()
            await loop.run_in_executor(None, _check)
            _extended_available = True
        except Exception:
            _extended_available = False
            logger.info("ats_extended_columns_not_available")
        return _extended_available

    async def scan_document(
        self,
        user_id: str,
        document_content: str,
        jd_text: str,
        document_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Scan a document for ATS compatibility."""
        chain = ATSScannerChain(self.ai_client)
        scan_result = await chain.scan_document(
            document_content=document_content,
            jd_text=jd_text,
        )

        # Build the base record (always works)
        record: Dict[str, Any] = {
            "user_id": user_id,
            "document_content": document_content[:2000],
            "status": "completed",
        }

        has_extended = await self._has_extended_columns()
        if has_extended:
            breakdown = scan_result.get("score_breakdown", {})
            record.update({
                "ats_score": int(scan_result.get("ats_score", 0)),
                "keyword_match_rate": float(scan_result.get("keyword_match_rate", 0.0)),
                "readability_score": float(breakdown.get("structure_score", 0)),
                "format_score": float(breakdown.get("strategy_score", 0)),
                "section_scores": scan_result.get("structure", {}),
                "matched_keywords": scan_result.get("keywords", {}).get("present", []),
                "missing_keywords": scan_result.get("keywords", {}).get("missing", []),
                "formatting_issues": scan_result.get("structure", {}).get("parsing_issues", []),
                "recommendations": scan_result.get("strategy", {}).get("rewrite_suggestions", []),
                "pass_prediction": scan_result.get("pass_probability", "unknown"),
            })
            if document_id:
                record["document_id"] = document_id
            if job_id:
                record["job_description_id"] = job_id

        doc_id = None
        try:
            doc_id = await self.db.create(TABLES.get("ats_scans", "ats_scans"), record)
            logger.info("ats_scan_completed", scan_id=doc_id, score=scan_result.get("ats_score", 0))
        except Exception as e:
            # If extended columns fail, retry with base-only
            logger.warning("ats_scan_save_fallback", error=str(e)[:200])
            try:
                base_record = {k: v for k, v in record.items() if k in _BASE_COLUMNS}
                doc_id = await self.db.create(TABLES.get("ats_scans", "ats_scans"), base_record)
            except Exception as e2:
                # DB save completely failed — still return the AI result
                logger.warning("ats_scan_save_failed", error=str(e2)[:200])

        # Return the full scan result (even if DB storage failed)
        return {
            "id": doc_id,
            **scan_result,
            "status": "completed",
        }

    async def get_user_scans(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(
            TABLES.get("ats_scans", "ats_scans"),
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def get_scan(self, scan_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        scan = await self.db.get(TABLES.get("ats_scans", "ats_scans"), scan_id)
        if scan and scan.get("user_id") == user_id:
            return scan
        return None
