"""Document schemas"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID

from app.schemas.base import BaseSchema, TimestampMixin, IDMixin


DocumentTypeEnum = Literal[
    "cv", "cover_letter", "portfolio", "case_study",
    "action_plan", "proposal", "motivation", "company_research"
]


class DocumentSection(BaseSchema):
    """Document section."""
    id: str
    title: str
    content: str
    order: int


class DocumentGenerate(BaseSchema):
    """Request to generate a document."""
    document_type: DocumentTypeEnum
    profile_id: UUID
    job_id: Optional[UUID] = None
    benchmark_id: Optional[UUID] = None
    template_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


class DocumentCreate(BaseSchema):
    """Schema for creating a document."""
    document_type: DocumentTypeEnum
    title: str
    content: str
    structured_content: Optional[Dict[str, Any]] = None
    target_job_id: Optional[UUID] = None
    target_company: Optional[str] = None
    template_id: Optional[str] = None
    is_benchmark: bool = False


class DocumentUpdate(BaseSchema):
    """Schema for updating a document."""
    title: Optional[str] = None
    content: Optional[str] = None
    structured_content: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class DocumentResponse(IDMixin, TimestampMixin):
    """Full document response."""
    user_id: UUID
    document_type: str
    title: str
    content: str
    structured_content: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    target_job_id: Optional[UUID] = None
    target_company: Optional[str] = None
    version: int = 1
    parent_id: Optional[UUID] = None
    template_id: Optional[str] = None
    status: str = "draft"
    is_benchmark: bool = False

    class Config:
        from_attributes = True


class DocumentList(BaseSchema):
    """List of documents."""
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int
