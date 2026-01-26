"""Export schemas"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID

from app.schemas.base import BaseSchema, IDMixin


ExportFormatEnum = Literal["pdf", "docx", "html", "markdown", "zip"]
ExportStatusEnum = Literal["pending", "processing", "completed", "failed"]


class ExportOptions(BaseSchema):
    """Export customization options."""
    include_header: bool = True
    include_footer: bool = True
    page_size: str = "A4"
    margins: Optional[Dict[str, int]] = None
    font_family: Optional[str] = None
    font_size: Optional[int] = None
    theme: Optional[str] = None  # professional, modern, minimal


class ExportRequest(BaseSchema):
    """Request to export documents."""
    document_ids: List[UUID]
    format: ExportFormatEnum
    filename: Optional[str] = None
    options: Optional[ExportOptions] = None


class ExportStatus(BaseSchema):
    """Export job status."""
    id: UUID
    status: ExportStatusEnum
    progress: Optional[int] = None
    message: Optional[str] = None
    file_url: Optional[str] = None
    expires_at: Optional[datetime] = None


class ExportResponse(IDMixin):
    """Full export response."""
    user_id: UUID
    document_ids: List[UUID]
    format: str
    filename: str
    file_url: Optional[str] = None
    file_size: Optional[int] = None
    options: Optional[ExportOptions] = None
    status: str = "pending"
    error_message: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExportList(BaseSchema):
    """List of exports."""
    exports: List[ExportResponse]
    total: int
