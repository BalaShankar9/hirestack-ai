"""AIM \u2014 documents (brief, rubric, notes, references)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services.aim.assignment_service import AIMAssignmentService
from app.services.aim.document_parser import AIMDocumentParser

router = APIRouter()

MAX_DOC_BYTES = 250_000   # 250KB per document is generous for academic briefs


class DocumentTextPayload(BaseModel):
    type: Literal["brief", "rubric", "notes", "reference"]
    file_name: Optional[str] = Field(None, max_length=500)
    raw_text: str = Field(..., min_length=1, max_length=MAX_DOC_BYTES)


@router.post("/assignments/{assignment_id}/documents", status_code=201)
async def attach_document_text(
    assignment_id: str,
    payload: DocumentTextPayload,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMAssignmentService()
    if not await svc.get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    return await svc.attach_document(
        user_id=current_user["id"],
        assignment_id=assignment_id,
        doc_type=payload.type,
        file_name=payload.file_name,
        raw_text=payload.raw_text,
    )


@router.post("/assignments/{assignment_id}/documents/upload", status_code=201)
async def upload_document(
    assignment_id: str,
    type: Literal["brief", "rubric", "notes", "reference"] = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMAssignmentService()
    if not await svc.get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    raw = await file.read()
    if len(raw) > MAX_DOC_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"file exceeds {MAX_DOC_BYTES} bytes")
    parser = AIMDocumentParser()
    ext = parser.ext_from_filename(file.filename)
    try:
        text = await parser.parse(raw, ext)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="could not extract text from file")
    return await svc.attach_document(
        user_id=current_user["id"],
        assignment_id=assignment_id,
        doc_type=type,
        file_name=file.filename,
        raw_text=text,
    )


@router.get("/assignments/{assignment_id}/documents")
async def list_documents(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = AIMAssignmentService()
    if not await svc.get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    return await svc.get_documents(assignment_id)
