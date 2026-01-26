"""
Export Service
Handles document export to PDF/DOCX formats
"""
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta
import io
import markdown

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from docx import Document as DocxDocument
from docx.shared import Inches, Pt

from app.models.document import Document
from app.models.export import Export
from app.schemas.export import ExportResponse, ExportStatus, ExportOptions


class ExportService:
    """Service for export operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_export(
        self,
        user_id: UUID,
        document_ids: List[UUID],
        format: str,
        filename: Optional[str] = None,
        options: Optional[ExportOptions] = None
    ) -> ExportResponse:
        """Create an export of documents."""
        # Verify all documents belong to user
        result = await self.db.execute(
            select(Document)
            .where(Document.id.in_(document_ids), Document.user_id == user_id)
        )
        documents = result.scalars().all()

        if len(documents) != len(document_ids):
            raise ValueError("Some documents not found or not accessible")

        # Generate filename
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"hirestack_export_{timestamp}.{format}"

        # Generate export content
        if format == "pdf":
            file_content = await self._generate_pdf(documents, options)
        elif format == "docx":
            file_content = await self._generate_docx(documents, options)
        elif format == "markdown":
            file_content = await self._generate_markdown(documents)
        else:
            raise ValueError(f"Unsupported format: {format}")

        # Create export record
        export = Export(
            user_id=user_id,
            document_ids=document_ids,
            format=format,
            filename=filename,
            file_size=len(file_content),
            options=options.model_dump() if options else None,
            status="completed",
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )

        # Store file content (in production, upload to S3)
        # For now, we'll store as base64 in metadata
        import base64
        export.file_url = f"data:application/octet-stream;base64,{base64.b64encode(file_content).decode()}"

        self.db.add(export)
        await self.db.commit()
        await self.db.refresh(export)

        return ExportResponse.model_validate(export)

    async def _generate_pdf(
        self,
        documents: List[Document],
        options: Optional[ExportOptions] = None
    ) -> bytes:
        """Generate PDF from documents."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )

        styles = getSampleStyleSheet()
        story = []

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=12
        )

        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            leading=14
        )

        for document in documents:
            # Add title
            story.append(Paragraph(document.title, title_style))
            story.append(Spacer(1, 12))

            # Convert markdown to HTML-like for reportlab
            content = document.content
            paragraphs = content.split('\n\n')

            for para in paragraphs:
                if para.strip():
                    # Simple markdown conversion
                    para = para.replace('**', '<b>').replace('__', '<b>')
                    para = para.replace('*', '<i>').replace('_', '<i>')
                    para = para.strip()

                    if para.startswith('#'):
                        # Heading
                        level = len(para.split()[0])
                        text = para.lstrip('#').strip()
                        story.append(Paragraph(text, styles[f'Heading{min(level, 3)}']))
                    elif para.startswith('- ') or para.startswith('* '):
                        # Bullet point
                        text = '• ' + para[2:]
                        story.append(Paragraph(text, body_style))
                    else:
                        story.append(Paragraph(para, body_style))

            story.append(Spacer(1, 24))

        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    async def _generate_docx(
        self,
        documents: List[Document],
        options: Optional[ExportOptions] = None
    ) -> bytes:
        """Generate DOCX from documents."""
        doc = DocxDocument()

        for document in documents:
            # Add title
            doc.add_heading(document.title, level=1)

            # Parse and add content
            content = document.content
            paragraphs = content.split('\n\n')

            for para in paragraphs:
                if para.strip():
                    if para.startswith('#'):
                        # Heading
                        level = len(para.split()[0].rstrip('#'))
                        text = para.lstrip('#').strip()
                        doc.add_heading(text, level=min(level + 1, 4))
                    elif para.startswith('- ') or para.startswith('* '):
                        # Bullet point
                        text = para[2:]
                        doc.add_paragraph(text, style='List Bullet')
                    else:
                        p = doc.add_paragraph()
                        # Handle bold/italic
                        parts = para.split('**')
                        for i, part in enumerate(parts):
                            run = p.add_run(part)
                            if i % 2 == 1:
                                run.bold = True

            doc.add_page_break()

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.read()

    async def _generate_markdown(self, documents: List[Document]) -> bytes:
        """Generate combined markdown file."""
        content = []

        for document in documents:
            content.append(f"# {document.title}\n\n")
            content.append(document.content)
            content.append("\n\n---\n\n")

        return "".join(content).encode('utf-8')

    async def get_user_exports(self, user_id: UUID) -> List[ExportResponse]:
        """Get all exports for a user."""
        result = await self.db.execute(
            select(Export)
            .where(Export.user_id == user_id)
            .order_by(Export.created_at.desc())
        )
        exports = result.scalars().all()
        return [ExportResponse.model_validate(e) for e in exports]

    async def get_export(
        self,
        export_id: UUID,
        user_id: UUID
    ) -> Optional[ExportResponse]:
        """Get a specific export."""
        result = await self.db.execute(
            select(Export)
            .where(Export.id == export_id, Export.user_id == user_id)
        )
        export = result.scalar_one_or_none()
        if export:
            return ExportResponse.model_validate(export)
        return None

    async def download_export(
        self,
        export_id: UUID,
        user_id: UUID
    ) -> Tuple[bytes, str, str]:
        """Download export file content."""
        result = await self.db.execute(
            select(Export)
            .where(Export.id == export_id, Export.user_id == user_id)
        )
        export = result.scalar_one_or_none()

        if not export:
            raise ValueError("Export not found")

        if export.expires_at and export.expires_at < datetime.utcnow():
            raise ValueError("Export has expired")

        # Decode file content from base64
        import base64
        if export.file_url and export.file_url.startswith("data:"):
            data = export.file_url.split(",")[1]
            file_content = base64.b64decode(data)
        else:
            raise ValueError("Export file not available")

        # Determine content type
        content_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "markdown": "text/markdown",
            "html": "text/html",
            "zip": "application/zip"
        }

        return file_content, export.filename, content_types.get(export.format, "application/octet-stream")

    async def get_status(
        self,
        export_id: UUID,
        user_id: UUID
    ) -> Optional[ExportStatus]:
        """Get export status."""
        result = await self.db.execute(
            select(Export)
            .where(Export.id == export_id, Export.user_id == user_id)
        )
        export = result.scalar_one_or_none()

        if not export:
            return None

        return ExportStatus(
            id=export.id,
            status=export.status,
            progress=100 if export.status == "completed" else 50,
            message=None,
            file_url=export.file_url if export.status == "completed" else None,
            expires_at=export.expires_at
        )

    async def delete_export(self, export_id: UUID, user_id: UUID) -> bool:
        """Delete an export."""
        result = await self.db.execute(
            select(Export)
            .where(Export.id == export_id, Export.user_id == user_id)
        )
        export = result.scalar_one_or_none()

        if not export:
            return False

        await self.db.delete(export)
        await self.db.commit()
        return True
