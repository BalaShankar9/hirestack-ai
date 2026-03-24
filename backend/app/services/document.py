"""
Document Service
Handles document generation and management with Firestore
"""
from typing import List, Optional, Dict, Any
import structlog

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB
from ai_engine.client import AIClient
from ai_engine.chains.document_generator import DocumentGeneratorChain

logger = structlog.get_logger()


class DocumentService:
    """Service for document operations using Firestore."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()
        self.ai_client = AIClient()

    async def generate_document(
        self,
        user_id: str,
        document_type: str,
        profile_id: str,
        job_id: Optional[str] = None,
        benchmark_id: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a document using AI."""
        # Fetch profile
        profile = await self.db.get(COLLECTIONS["profiles"], profile_id)
        if not profile or profile.get("user_id") != user_id:
            raise ValueError("Profile not found")

        # Fetch optional job
        job = None
        if job_id:
            job = await self.db.get(COLLECTIONS["jobs"], job_id)
            if job and job.get("user_id") != user_id:
                job = None

        # Fetch gap analysis if we have a benchmark
        gap_analysis: Optional[Dict[str, Any]] = None
        if benchmark_id:
            gaps = await self.db.query(
                COLLECTIONS["gap_reports"],
                filters=[
                    ("user_id", "==", user_id),
                    ("profile_id", "==", profile_id),
                    ("benchmark_id", "==", benchmark_id),
                ],
                order_by="created_at",
                order_direction="DESCENDING",
                limit=1,
            )
            if gaps:
                gap_analysis = {"strengths": gaps[0].get("strengths", []), "skill_gaps": gaps[0].get("skill_gaps", [])}

        # Build data dicts
        profile_data = {
            "name": profile.get("name"),
            "title": profile.get("title"),
            "summary": profile.get("summary"),
            "contact_info": profile.get("contact_info"),
            "skills": profile.get("skills", []),
            "experience": profile.get("experience", []),
            "education": profile.get("education", []),
            "certifications": profile.get("certifications", []),
            "projects": profile.get("projects", []),
        }

        job_requirements: Dict[str, Any] = {}
        company_info: Dict[str, Any] = {}
        if job:
            job_requirements = {
                "required_skills": job.get("required_skills"),
                "requirements": job.get("requirements"),
                "responsibilities": job.get("responsibilities"),
            }
            company_info = job.get("company_info", {})

        # Generate with AI
        generator = DocumentGeneratorChain(self.ai_client)
        job_title = job.get("title", "Target Role") if job else "Target Role"
        company = job.get("company", "Target Company") if job else "Target Company"

        if document_type == "cv":
            content = await generator.generate_cv(profile_data, job_title, company, job_requirements, gap_analysis)
        elif document_type == "cover_letter":
            content = await generator.generate_cover_letter(
                profile_data, job_title, company, company_info, job_requirements,
                gap_analysis.get("strengths", []) if gap_analysis else [],
            )
        elif document_type == "motivation":
            result = await generator.generate_motivation_statement(profile_data, company, company_info, job_title)
            content = str(result)
        else:
            raise ValueError(f"Unsupported document type: {document_type}")

        title = f"{document_type.replace('_', ' ').title()} - {job_title}"
        record = {
            "user_id": user_id,
            "document_type": document_type,
            "title": title,
            "content": content,
            "target_job_id": job_id,
            "target_company": company,
            "doc_metadata": {"generated": True, "options": options},
            "status": "draft",
        }

        doc_id = await self.db.create(COLLECTIONS["documents"], record)
        logger.info("document_generated", doc_id=doc_id, type=document_type)
        return await self.db.get(COLLECTIONS["documents"], doc_id)

    async def generate_all_documents(
        self, user_id: str, profile_id: str, job_id: str
    ) -> List[Dict[str, Any]]:
        """Generate complete application package."""
        documents: List[Dict[str, Any]] = []
        for doc_type in ["cv", "cover_letter", "motivation"]:
            try:
                doc = await self.generate_document(user_id=user_id, document_type=doc_type, profile_id=profile_id, job_id=job_id)
                documents.append(doc)
            except Exception as e:
                logger.warning("document_gen_failed", type=doc_type, error=str(e))
        return documents

    async def get_user_documents(self, user_id: str, document_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        filters = [("user_id", "==", user_id)]
        if document_type:
            filters.append(("document_type", "==", document_type))
        return await self.db.query(
            COLLECTIONS["documents"], filters=filters, order_by="created_at", order_direction="DESCENDING", limit=limit,
        )

    async def get_document(self, document_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.db.get(COLLECTIONS["documents"], document_id)
        if doc and doc.get("user_id") == user_id:
            return doc
        return None

    async def update_document(self, document_id: str, user_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ALLOWED = {"title", "content", "status"}
        doc = await self.get_document(document_id, user_id)
        if not doc:
            return None
        safe = {k: v for k, v in update_data.items() if k in ALLOWED}
        if safe:
            # Bump version on content change
            if "content" in safe:
                safe["version"] = (doc.get("version") or 0) + 1
            await self.db.update(COLLECTIONS["documents"], document_id, safe)
        return await self.db.get(COLLECTIONS["documents"], document_id)

    async def delete_document(self, document_id: str, user_id: str) -> bool:
        doc = await self.get_document(document_id, user_id)
        if not doc:
            return False
        await self.db.delete(COLLECTIONS["documents"], document_id)
        return True
