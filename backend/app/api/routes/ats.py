"""
ATS Scanner routes
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.services.ats import ATSService
from app.api.deps import get_current_user, validate_uuid, check_billing_limit
from app.api.response import success_response
from app.core.security import limiter
import structlog

logger = structlog.get_logger()

router = APIRouter()

MAX_ATS_INPUT_SIZE = 100 * 1024  # 100KB combined


class ATSScanRequest(BaseModel):
    document_content: str
    jd_text: str
    document_id: str | None = None
    job_id: str | None = None


@router.post("/scan")
@limiter.limit("5/minute")
async def scan_document(
    request: Request,
    req: ATSScanRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Scan a document for ATS compatibility."""
    await check_billing_limit("ats_scans", current_user)
    combined_size = len((req.document_content + req.jd_text).encode("utf-8"))
    if combined_size > MAX_ATS_INPUT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Combined input exceeds 100KB limit",
        )

    if not req.document_content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_content is required",
        )
    if not req.jd_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="jd_text is required",
        )

    service = ATSService()
    try:
        result = await service.scan_document(
            user_id=current_user["id"],
            document_content=req.document_content,
            jd_text=req.jd_text,
            document_id=req.document_id,
            job_id=req.job_id,
        )
        return success_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("ats_scan_error", error=str(e), user_id=current_user["id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )


@router.get("")
async def list_scans(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's ATS scans."""
    service = ATSService()
    return await service.get_user_scans(current_user["id"])


@router.get("/{scan_id}")
async def get_scan(
    scan_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific ATS scan."""
    validate_uuid(scan_id, "scan_id")
    service = ATSService()
    scan = await service.get_scan(scan_id, current_user["id"])
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATS scan not found")
    return scan
