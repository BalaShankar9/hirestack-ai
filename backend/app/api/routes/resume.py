"""
Resume utilities (parse/extract).

The frontend owns Supabase Auth; the backend verifies the token and
provides server-side helpers (e.g. PDF parsing) for reliability.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user, get_current_user_or_guest
from app.core.config import settings
from app.services.file_parser import FileParser


router = APIRouter()

_file_parser = FileParser()


def _max_bytes() -> int:
    return int(settings.max_upload_size_mb) * 1024 * 1024


@router.post("/parse")
async def parse_resume(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user_or_guest),
    max_pages: int = 4,
) -> Dict[str, Any]:
    """
    Extract plain text from a resume file.

    Supported: PDF, DOCX, DOC, TXT.
    Returns: { text, fileName, contentType }
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename")

    raw = await file.read()
    if len(raw) > _max_bytes():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {settings.max_upload_size_mb}MB).",
        )

    name = file.filename
    ext = (name.lower().split(".")[-1] if "." in name else "").strip()
    content_type = file.content_type or ""

    # Map content-type to extension if extension is missing/unclear
    if not ext or ext not in ("pdf", "docx", "doc", "txt"):
        ct_map = {
            "application/pdf": "pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
            "application/msword": "doc",
            "text/plain": "txt",
        }
        ext = ct_map.get(content_type, ext)

    if ext not in ("pdf", "docx", "doc", "txt"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Use PDF, DOCX, or TXT.",
        )

    try:
        text = await _file_parser.extract_text(raw, ext)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse file: {str(e)}",
        )

    return {
        "fileName": name,
        "contentType": content_type,
        "text": text,
        "userId": current_user.get("id"),
    }
