"""
ATS Scanner Service
Handles ATS compatibility scanning operations
"""
from typing import Dict, Any, List, Optional
import structlog

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB
from ai_engine.client import AIClient
from ai_engine.chains.ats_scanner import ATSScannerChain

logger = structlog.get_logger()


class ATSService:
    """Service for ATS scanning operations using Firestore."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()
        self.ai_client = AIClient()

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

        record = {
            "user_id": user_id,
            "document_id": document_id,
            "job_id": job_id,
            "document_content_snippet": document_content[:500],
            "jd_text_snippet": jd_text[:500],
            "ats_score": scan_result.get("ats_score", 0),
            "keyword_match_rate": scan_result.get("keyword_match_rate", 0.0),
            "keywords": scan_result.get("keywords", {}),
            "formatting_issues": scan_result.get("formatting_issues", []),
            "section_analysis": scan_result.get("section_analysis", {}),
            "suggestions": scan_result.get("suggestions", []),
            "overall_assessment": scan_result.get("overall_assessment", ""),
            "pass_probability": scan_result.get("pass_probability", "unknown"),
            "status": "completed",
        }

        doc_id = await self.db.create(COLLECTIONS.get("ats_scans", "ats_scans"), record)
        logger.info("ats_scan_completed", scan_id=doc_id, score=record["ats_score"])
        return await self.db.get(COLLECTIONS.get("ats_scans", "ats_scans"), doc_id)

    async def get_user_scans(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(
            COLLECTIONS.get("ats_scans", "ats_scans"),
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def get_scan(self, scan_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        scan = await self.db.get(COLLECTIONS.get("ats_scans", "ats_scans"), scan_id)
        if scan and scan.get("user_id") == user_id:
            return scan
        return None
