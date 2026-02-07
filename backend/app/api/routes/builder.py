"""
Document Builder routes (Firestore)
"""
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.services.document import DocumentService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/generate")
async def generate_document(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a document using AI."""
    service = DocumentService()
    try:
        return await service.generate_document(
            user_id=current_user["id"],
            document_type=request.get("document_type", "cv"),
            profile_id=request.get("profile_id"),
            job_id=request.get("job_id"),
            benchmark_id=request.get("benchmark_id"),
            options=request.get("options"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/generate-all")
async def generate_all_documents(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate complete application package."""
    service = DocumentService()
    try:
        documents = await service.generate_all_documents(
            user_id=current_user["id"],
            profile_id=request.get("profile_id"),
            job_id=request.get("job_id"),
        )
        return {"documents": documents, "count": len(documents)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/documents")
async def list_documents(
    document_type: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's documents."""
    service = DocumentService()
    return await service.get_user_documents(current_user["id"], document_type=document_type)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific document."""
    service = DocumentService()
    document = await service.get_document(document_id, current_user["id"])
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.put("/documents/{document_id}")
async def update_document(
    document_id: str,
    update_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a document."""
    service = DocumentService()
    document = await service.update_document(document_id, current_user["id"], update_data)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("/documents/{document_id}/version")
async def create_document_version(
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new version of a document."""
    service = DocumentService()
    document = await service.create_version(document_id, current_user["id"])
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a document."""
    service = DocumentService()
    deleted = await service.delete_document(document_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
