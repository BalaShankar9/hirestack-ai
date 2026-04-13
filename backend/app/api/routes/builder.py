"""
Document Builder routes (Firestore)
"""
from typing import Dict, Any, Optional

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, Field

from app.services.document import DocumentService
from app.api.deps import get_current_user, check_billing_limit
import structlog

logger = structlog.get_logger()

router = APIRouter()


class GenerateDocumentRequest(BaseModel):
    document_type: str = Field("cv", pattern="^(cv|cover_letter|personal_statement|portfolio|roadmap)$")
    profile_id: Optional[str] = None
    job_id: Optional[str] = None
    benchmark_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


@limiter.limit("3/minute")
@router.post("/generate")
async def generate_document(
    body: GenerateDocumentRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a document using AI."""
    await check_billing_limit("ai_calls", current_user)
    service = DocumentService()
    try:
        return await service.generate_document(
            user_id=current_user["id"],
            document_type=body.document_type,
            profile_id=body.profile_id,
            job_id=body.job_id,
            benchmark_id=body.benchmark_id,
            options=body.options,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("unexpected_error", error=str(e), endpoint="generate_document")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")


class GenerateAllRequest(BaseModel):
    profile_id: Optional[str] = None
    job_id: Optional[str] = None


@limiter.limit("3/minute")
@router.post("/generate-all")
async def generate_all_documents(
    body: GenerateAllRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate complete application package."""
    service = DocumentService()
    try:
        documents = await service.generate_all_documents(
            user_id=current_user["id"],
            profile_id=body.profile_id,
            job_id=body.job_id,
        )
        return {"documents": documents, "count": len(documents)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("unexpected_error", error=str(e), endpoint="generate_all_documents")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")


@limiter.limit("30/minute")
@router.get("/documents")
async def list_documents(
    request: Request,
    document_type: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's documents."""
    service = DocumentService()
    return await service.get_user_documents(current_user["id"], document_type=document_type)


@limiter.limit("30/minute")
@router.get("/documents/{document_id}")
async def get_document(
    request: Request,
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific document."""
    service = DocumentService()
    document = await service.get_document(document_id, current_user["id"])
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


class UpdateDocumentRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = Field(None, max_length=200000)
    status: Optional[str] = Field(None, max_length=50)


@limiter.limit("30/minute")
@router.put("/documents/{document_id}")
async def update_document(
    request: Request,
    document_id: str,
    update_data: UpdateDocumentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a document."""
    service = DocumentService()
    document = await service.update_document(document_id, current_user["id"], update_data.model_dump(exclude_none=True))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@limiter.limit("30/minute")
@router.post("/documents/{document_id}/version")
async def create_document_version(
    request: Request,
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new version of a document."""
    service = DocumentService()
    document = await service.create_version(document_id, current_user["id"])
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@limiter.limit("30/minute")
@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    request: Request,
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a document."""
    service = DocumentService()
    deleted = await service.delete_document(document_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
