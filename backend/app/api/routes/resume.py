"""
Resume utilities (parse/extract).

The frontend owns Firebase Auth; the backend verifies the Firebase ID token and
provides server-side helpers (e.g. PDF parsing) for reliability.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user
from app.core.config import settings


router = APIRouter()


def _max_bytes() -> int:
    return int(settings.max_upload_size_mb) * 1024 * 1024


@router.post("/parse")
async def parse_resume(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    max_pages: int = 4,
) -> Dict[str, Any]:
    """
    Extract plain text from a resume file.

    Supported: PDF, DOCX, TXT.
    Returns: { text, fileName, contentType, pagesParsed?, totalPages? }
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

    text: str = ""
    total_pages: Optional[int] = None
    pages_parsed: Optional[int] = None

    try:
        if ext == "txt" or content_type.startswith("text/"):
            text = raw.decode("utf-8", errors="ignore")

        elif ext == "docx" or content_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            from docx import Document  # type: ignore

            doc = Document(io.BytesIO(raw))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
            text = "\n".join(paragraphs)

        elif ext == "pdf" or content_type == "application/pdf":
            from PyPDF2 import PdfReader  # type: ignore

            reader = PdfReader(io.BytesIO(raw))
            total_pages = len(reader.pages)
            pages_parsed = min(total_pages, max(1, int(max_pages)))
            chunks = []
            for i in range(pages_parsed):
                page = reader.pages[i]
                chunks.append(page.extract_text() or "")
            text = "\n\n".join([c.strip() for c in chunks if c.strip()])
            if total_pages and total_pages > pages_parsed:
                text += f"\n\n[Preview parsed from first {pages_parsed} pages for speed.]"

        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported file type. Use PDF, DOCX, or TXT.",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse file: {str(e)}",
        )

    return {
        "fileName": name,
        "contentType": content_type,
        "text": text,
        "totalPages": total_pages,
        "pagesParsed": pages_parsed,
        "userId": current_user.get("id"),
    }

