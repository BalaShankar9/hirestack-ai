"""
Document Service
Handles document generation and management with Firestore
"""
from typing import List, Optional, Dict, Any
import structlog

from app.core.database import get_firestore_db, get_supabase, COLLECTIONS, TABLES, FirestoreDB
from ai_engine.client import AIClient
from ai_engine.chains.document_generator import DocumentGeneratorChain

logger = structlog.get_logger()

# Try to import agent pipelines — fall back to chains-only if unavailable
try:
    from ai_engine.agents.pipelines import cv_generation_pipeline, cover_letter_pipeline, personal_statement_pipeline
    _PIPELINES_AVAILABLE = True
except Exception:
    _PIPELINES_AVAILABLE = False


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

        # Generate with AI — prefer agent pipeline, fall back to chain
        job_title = job.get("title", "Target Role") if job else "Target Role"
        company = job.get("company", "Target Company") if job else "Target Company"

        content = await self._generate_with_pipeline_or_chain(
            document_type, profile_data, job_title, company,
            job_requirements, company_info, gap_analysis,
        )

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

    async def _generate_with_pipeline_or_chain(
        self,
        document_type: str,
        profile_data: Dict[str, Any],
        job_title: str,
        company: str,
        job_requirements: Dict[str, Any],
        company_info: Dict[str, Any],
        gap_analysis: Optional[Dict[str, Any]],
    ) -> str:
        """Try agent pipeline first, fall back to direct chain on failure."""
        if _PIPELINES_AVAILABLE:
            try:
                return await self._generate_via_pipeline(
                    document_type, profile_data, job_title, company,
                    job_requirements, company_info, gap_analysis,
                )
            except Exception as pipe_err:
                logger.warning("pipeline_fallback_to_chain", type=document_type, error=str(pipe_err)[:200])

        return await self._generate_via_chain(
            document_type, profile_data, job_title, company,
            job_requirements, company_info, gap_analysis,
        )

    async def _generate_via_pipeline(
        self,
        document_type: str,
        profile_data: Dict[str, Any],
        job_title: str,
        company: str,
        job_requirements: Dict[str, Any],
        company_info: Dict[str, Any],
        gap_analysis: Optional[Dict[str, Any]],
    ) -> str:
        """Generate content using the multi-agent pipeline."""
        pipeline_input = {
            "user_profile": profile_data,
            "job_title": job_title,
            "company": company,
            "job_requirements": job_requirements,
            "company_info": company_info,
            "gap_analysis": gap_analysis or {},
        }

        sb = get_supabase()
        if document_type == "cv":
            pipe = cv_generation_pipeline(ai_client=self.ai_client, db=sb, tables=TABLES)
        elif document_type == "cover_letter":
            pipe = cover_letter_pipeline(ai_client=self.ai_client, db=sb, tables=TABLES)
        elif document_type in ("motivation", "personal_statement"):
            pipe = personal_statement_pipeline(ai_client=self.ai_client, db=sb, tables=TABLES)
        else:
            raise ValueError(f"Unsupported document type: {document_type}")

        result = await pipe.execute(pipeline_input)
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _generate_via_chain(
        self,
        document_type: str,
        profile_data: Dict[str, Any],
        job_title: str,
        company: str,
        job_requirements: Dict[str, Any],
        company_info: Dict[str, Any],
        gap_analysis: Optional[Dict[str, Any]],
    ) -> str:
        """Generate content using the direct chain (fallback)."""
        generator = DocumentGeneratorChain(self.ai_client)

        if document_type == "cv":
            return await generator.generate_cv(profile_data, job_title, company, job_requirements, gap_analysis)
        elif document_type == "cover_letter":
            return await generator.generate_cover_letter(
                profile_data, job_title, company, company_info, job_requirements,
                gap_analysis.get("strengths", []) if gap_analysis else [],
            )
        elif document_type in ("motivation", "personal_statement"):
            result = await generator.generate_motivation_statement(profile_data, company, company_info, job_title)
            return str(result)
        else:
            raise ValueError(f"Unsupported document type: {document_type}")

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
