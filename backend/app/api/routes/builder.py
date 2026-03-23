"""
Document Builder routes (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.services.document import DocumentService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class GenerateDocumentRequest(BaseModel):
    document_type: Literal["cv", "cover_letter", "motivation"] = Field("cv", description="Type of document")
    profile_id: str = Field(..., min_length=1, max_length=100, description="Profile ID to use")
    job_id: Optional[str] = Field(None, max_length=100, description="Job description ID")
    benchmark_id: Optional[str] = Field(None, max_length=100, description="Benchmark ID for gap-aware generation")
    options: Optional[Dict[str, Any]] = Field(None, description="Additional generation options")

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, v: str) -> str:
        try:
            _uuid.UUID(v)
        except (ValueError, AttributeError):
            raise ValueError("profile_id must be a valid UUID")
        return v

    @field_validator("job_id", "benchmark_id")
    @classmethod
    def validate_optional_uuids(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                _uuid.UUID(v)
            except (ValueError, AttributeError):
                raise ValueError("must be a valid UUID")
        return v


class GenerateAllRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=100, description="Profile ID")
    job_id: str = Field(..., min_length=1, max_length=100, description="Job description ID")

    @field_validator("profile_id", "job_id")
    @classmethod
    def validate_uuids(cls, v: str) -> str:
        try:
            _uuid.UUID(v)
        except (ValueError, AttributeError):
            raise ValueError("must be a valid UUID")
        return v


class UpdateDocumentRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = Field(None, max_length=500_000)
    status: Optional[Literal["draft", "final", "archived"]] = None


@router.post("/generate")
@limiter.limit("15/minute")
async def generate_document(
    http_request: Request,
    request: GenerateDocumentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a document using AI."""
    service = DocumentService()
    try:
        return await service.generate_document(
            user_id=current_user["id"],
            document_type=request.document_type,
            profile_id=request.profile_id,
            job_id=request.job_id,
            benchmark_id=request.benchmark_id,
            options=request.options,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document generation failed. Please check your inputs.")


@router.post("/generate-all")
@limiter.limit("5/minute")
async def generate_all_documents(
    http_request: Request,
    request: GenerateAllRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate complete application package."""
    service = DocumentService()
    try:
        documents = await service.generate_all_documents(
            user_id=current_user["id"],
            profile_id=request.profile_id,
            job_id=request.job_id,
        )
        return {"documents": documents, "count": len(documents)}
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document generation failed. Please check your inputs.")


VALID_DOCUMENT_TYPES = {"cv", "cover_letter", "motivation", "personal_statement", "portfolio"}


@router.get("/documents")
@limiter.limit("30/minute")
async def list_documents(
    request: Request,
    document_type: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's documents."""
    if document_type and document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid document_type. Must be one of: {', '.join(sorted(VALID_DOCUMENT_TYPES))}")
    service = DocumentService()
    return await service.get_user_documents(current_user["id"], document_type=document_type)


@router.get("/documents/{document_id}")
@limiter.limit("30/minute")
async def get_document(
    request: Request,
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific document."""
    _validate_uuid(document_id, "document_id")
    service = DocumentService()
    document = await service.get_document(document_id, current_user["id"])
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.put("/documents/{document_id}")
@limiter.limit("15/minute")
async def update_document(
    request: Request,
    document_id: str,
    update_data: UpdateDocumentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a document."""
    _validate_uuid(document_id, "document_id")
    service = DocumentService()
    document = await service.update_document(
        document_id, current_user["id"], update_data.model_dump(exclude_none=True)
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("/documents/{document_id}/version")
@limiter.limit("10/minute")
async def create_document_version(
    request: Request,
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new version of a document."""
    _validate_uuid(document_id, "document_id")
    service = DocumentService()
    document = await service.create_version(document_id, current_user["id"])
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_document(
    request: Request,
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a document."""
    _validate_uuid(document_id, "document_id")
    service = DocumentService()
    deleted = await service.delete_document(document_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
