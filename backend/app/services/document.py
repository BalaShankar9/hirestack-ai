"""
Document Service
Handles document generation and management
"""
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.profile import Profile
from app.models.job import JobDescription
from app.models.benchmark import Benchmark
from app.models.gap import GapReport
from app.models.document import Document
from app.schemas.document import DocumentResponse, DocumentUpdate
from ai_engine.client import AIClient
from ai_engine.chains.document_generator import DocumentGeneratorChain


class DocumentService:
    """Service for document operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_client = AIClient()

    async def generate_document(
        self,
        user_id: UUID,
        document_type: str,
        profile_id: UUID,
        job_id: Optional[UUID] = None,
        benchmark_id: Optional[UUID] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> DocumentResponse:
        """Generate a document using AI."""
        # Get profile
        profile_result = await self.db.execute(
            select(Profile)
            .where(Profile.id == profile_id, Profile.user_id == user_id)
        )
        profile = profile_result.scalar_one_or_none()
        if not profile:
            raise ValueError("Profile not found")

        # Get job if provided
        job = None
        if job_id:
            job_result = await self.db.execute(
                select(JobDescription)
                .where(JobDescription.id == job_id, JobDescription.user_id == user_id)
            )
            job = job_result.scalar_one_or_none()

        # Get gap analysis if available
        gap_analysis = None
        if benchmark_id:
            gap_result = await self.db.execute(
                select(GapReport)
                .where(
                    GapReport.user_id == user_id,
                    GapReport.profile_id == profile_id,
                    GapReport.benchmark_id == benchmark_id
                )
                .order_by(GapReport.created_at.desc())
            )
            gap = gap_result.scalar_one_or_none()
            if gap:
                gap_analysis = {
                    "strengths": gap.strengths,
                    "skill_gaps": gap.skill_gaps
                }

        # Build profile data
        profile_data = {
            "name": profile.name,
            "title": profile.title,
            "summary": profile.summary,
            "contact_info": profile.contact_info,
            "skills": profile.skills or [],
            "experience": profile.experience or [],
            "education": profile.education or [],
            "certifications": profile.certifications or [],
            "projects": profile.projects or []
        }

        job_requirements = {}
        company_info = {}
        if job:
            job_requirements = {
                "required_skills": job.required_skills,
                "requirements": job.requirements,
                "responsibilities": job.responsibilities
            }
            company_info = job.company_info or {}

        # Generate document with AI
        generator = DocumentGeneratorChain(self.ai_client)

        if document_type == "cv":
            content = await generator.generate_cv(
                profile_data,
                job.title if job else "Target Role",
                job.company if job else "Target Company",
                job_requirements,
                gap_analysis
            )
        elif document_type == "cover_letter":
            content = await generator.generate_cover_letter(
                profile_data,
                job.title if job else "Target Role",
                job.company if job else "Target Company",
                company_info,
                job_requirements,
                gap_analysis.get("strengths", []) if gap_analysis else []
            )
        elif document_type == "motivation":
            result = await generator.generate_motivation_statement(
                profile_data,
                job.company if job else "Target Company",
                company_info,
                job.title if job else "Target Role"
            )
            content = str(result)
        else:
            raise ValueError(f"Unsupported document type: {document_type}")

        # Create document record
        title = f"{document_type.replace('_', ' ').title()} - {job.title if job else 'General'}"
        document = Document(
            user_id=user_id,
            document_type=document_type,
            title=title,
            content=content,
            target_job_id=job_id,
            target_company=job.company if job else None,
            metadata={"generated": True, "options": options},
            status="draft"
        )

        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)

        return DocumentResponse.model_validate(document)

    async def generate_all_documents(
        self,
        user_id: UUID,
        profile_id: UUID,
        job_id: UUID
    ) -> List[DocumentResponse]:
        """Generate all document types for a job application."""
        documents = []

        for doc_type in ["cv", "cover_letter", "motivation"]:
            try:
                doc = await self.generate_document(
                    user_id=user_id,
                    document_type=doc_type,
                    profile_id=profile_id,
                    job_id=job_id
                )
                documents.append(doc)
            except Exception:
                continue  # Skip failed documents

        return documents

    async def get_user_documents(
        self,
        user_id: UUID,
        document_type: Optional[str] = None
    ) -> List[DocumentResponse]:
        """Get all documents for a user."""
        query = select(Document).where(Document.user_id == user_id)
        if document_type:
            query = query.where(Document.document_type == document_type)
        query = query.order_by(Document.created_at.desc())

        result = await self.db.execute(query)
        documents = result.scalars().all()
        return [DocumentResponse.model_validate(d) for d in documents]

    async def get_document(
        self,
        document_id: UUID,
        user_id: UUID
    ) -> Optional[DocumentResponse]:
        """Get a specific document."""
        result = await self.db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
        )
        document = result.scalar_one_or_none()
        if document:
            return DocumentResponse.model_validate(document)
        return None

    async def update_document(
        self,
        document_id: UUID,
        user_id: UUID,
        update_data: DocumentUpdate
    ) -> Optional[DocumentResponse]:
        """Update a document."""
        result = await self.db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(document, field):
                setattr(document, field, value)

        await self.db.commit()
        await self.db.refresh(document)

        return DocumentResponse.model_validate(document)

    async def create_version(
        self,
        document_id: UUID,
        user_id: UUID
    ) -> Optional[DocumentResponse]:
        """Create a new version of a document."""
        result = await self.db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
        )
        original = result.scalar_one_or_none()

        if not original:
            return None

        # Create new version
        new_doc = Document(
            user_id=user_id,
            document_type=original.document_type,
            title=f"{original.title} (v{original.version + 1})",
            content=original.content,
            structured_content=original.structured_content,
            metadata=original.metadata,
            target_job_id=original.target_job_id,
            target_company=original.target_company,
            version=original.version + 1,
            parent_id=original.id,
            status="draft"
        )

        self.db.add(new_doc)
        await self.db.commit()
        await self.db.refresh(new_doc)

        return DocumentResponse.model_validate(new_doc)

    async def delete_document(self, document_id: UUID, user_id: UUID) -> bool:
        """Delete a document."""
        result = await self.db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            return False

        await self.db.delete(document)
        await self.db.commit()
        return True
