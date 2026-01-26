"""
Export routes - PDF/DOCX generation
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.schemas.export import ExportRequest, ExportResponse, ExportStatus
from app.services.export import ExportService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("", response_model=ExportResponse)
async def create_export(
    request: ExportRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create an export of documents."""
    export_service = ExportService(db)

    try:
        export = await export_service.create_export(
            user_id=current_user.id,
            document_ids=request.document_ids,
            format=request.format,
            filename=request.filename,
            options=request.options
        )
        return export
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[ExportResponse])
async def list_exports(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all user's exports."""
    export_service = ExportService(db)
    exports = await export_service.get_user_exports(current_user.id)
    return exports


@router.get("/{export_id}", response_model=ExportResponse)
async def get_export(
    export_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get export details."""
    export_service = ExportService(db)
    export = await export_service.get_export(export_id, current_user.id)

    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found"
        )
    return export


@router.get("/{export_id}/download")
async def download_export(
    export_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Download an exported file."""
    export_service = ExportService(db)

    try:
        file_content, filename, content_type = await export_service.download_export(
            export_id, current_user.id
        )

        return StreamingResponse(
            iter([file_content]),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/{export_id}/status", response_model=ExportStatus)
async def get_export_status(
    export_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get export processing status."""
    export_service = ExportService(db)
    status = await export_service.get_status(export_id, current_user.id)

    if not status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found"
        )
    return status


@router.delete("/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_export(
    export_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an export."""
    export_service = ExportService(db)
    deleted = await export_service.delete_export(export_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found"
        )
