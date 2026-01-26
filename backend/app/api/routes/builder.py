"""
Document Builder routes
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.schemas.document import (
    DocumentCreate, DocumentUpdate, DocumentResponse,
    DocumentGenerate, DocumentList
)
from app.services.document import DocumentService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/generate", response_model=DocumentResponse)
async def generate_document(
    request: DocumentGenerate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate a document using AI."""
    doc_service = DocumentService(db)

    try:
        document = await doc_service.generate_document(
            user_id=current_user.id,
            document_type=request.document_type,
            profile_id=request.profile_id,
            job_id=request.job_id,
            benchmark_id=request.benchmark_id,
            options=request.options
        )
        return document
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/generate-all")
async def generate_all_documents(
    profile_id: UUID,
    job_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate complete application package."""
    doc_service = DocumentService(db)

    try:
        documents = await doc_service.generate_all_documents(
            user_id=current_user.id,
            profile_id=profile_id,
            job_id=job_id
        )
        return {"documents": documents, "count": len(documents)}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    document_type: str = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all user's documents."""
    doc_service = DocumentService(db)
    documents = await doc_service.get_user_documents(
        current_user.id,
        document_type=document_type
    )
    return documents


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific document."""
    doc_service = DocumentService(db)
    document = await doc_service.get_document(document_id, current_user.id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    return document


@router.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    update_data: DocumentUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a document."""
    doc_service = DocumentService(db)
    document = await doc_service.update_document(
        document_id, current_user.id, update_data
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    return document


@router.post("/documents/{document_id}/version", response_model=DocumentResponse)
async def create_document_version(
    document_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new version of a document."""
    doc_service = DocumentService(db)
    document = await doc_service.create_version(document_id, current_user.id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a document."""
    doc_service = DocumentService(db)
    deleted = await doc_service.delete_document(document_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
