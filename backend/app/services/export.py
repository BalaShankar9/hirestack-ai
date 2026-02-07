"""
Export Service
Handles document export to PDF/DOCX formats with Firestore
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import io
import base64
import structlog

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from docx import Document as DocxDocument

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB

logger = structlog.get_logger()


class ExportService:
    """Service for export operations using Firestore."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()

    async def create_export(
        self,
        user_id: str,
        document_ids: List[str],
        fmt: str,
        filename: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an export bundle."""
        # Fetch documents, verify ownership
        documents: List[Dict[str, Any]] = []
        for did in document_ids:
            doc = await self.db.get(COLLECTIONS["documents"], did)
            if not doc or doc.get("user_id") != user_id:
                raise ValueError(f"Document {did} not found or not accessible")
            documents.append(doc)

        if not filename:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"hirestack_export_{timestamp}.{fmt}"

        # Generate file content
        if fmt == "pdf":
            file_bytes = self._generate_pdf(documents, options)
        elif fmt == "docx":
            file_bytes = self._generate_docx(documents, options)
        elif fmt == "markdown":
            file_bytes = self._generate_markdown(documents)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        # Store as base64 in Firestore (small exports only; production should use Cloud Storage)
        b64 = base64.b64encode(file_bytes).decode()
        record = {
            "user_id": user_id,
            "document_ids": document_ids,
            "format": fmt,
            "filename": filename,
            "file_size": len(file_bytes),
            "file_url": f"data:application/octet-stream;base64,{b64}",
            "options": options,
            "status": "completed",
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        }
        doc_id = await self.db.create(COLLECTIONS["exports"], record)
        logger.info("export_created", export_id=doc_id, format=fmt)
        return await self.db.get(COLLECTIONS["exports"], doc_id)

    # ── PDF ──
    def _generate_pdf(self, documents: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("CustomTitle", parent=styles["Heading1"], fontSize=18, spaceAfter=12)
        body_style = ParagraphStyle("CustomBody", parent=styles["Normal"], fontSize=11, spaceAfter=6, leading=14)
        story: list = []

        for document in documents:
            story.append(Paragraph(document.get("title", "Untitled"), title_style))
            story.append(Spacer(1, 12))
            for para in (document.get("content", "")).split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                para = para.replace("**", "<b>").replace("__", "<b>")
                para = para.replace("*", "<i>").replace("_", "<i>")
                if para.startswith("#"):
                    level = min(len(para.split()[0]), 3)
                    text = para.lstrip("#").strip()
                    story.append(Paragraph(text, styles[f"Heading{level}"]))
                elif para.startswith("- ") or para.startswith("* "):
                    story.append(Paragraph("• " + para[2:], body_style))
                else:
                    story.append(Paragraph(para, body_style))
            story.append(Spacer(1, 24))

        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    # ── DOCX ──
    def _generate_docx(self, documents: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> bytes:
        docx = DocxDocument()
        for document in documents:
            docx.add_heading(document.get("title", "Untitled"), level=1)
            for para in (document.get("content", "")).split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                if para.startswith("#"):
                    level = min(len(para.split()[0].rstrip("#")), 4)
                    docx.add_heading(para.lstrip("#").strip(), level=level + 1)
                elif para.startswith("- ") or para.startswith("* "):
                    docx.add_paragraph(para[2:], style="List Bullet")
                else:
                    p = docx.add_paragraph()
                    parts = para.split("**")
                    for i, part in enumerate(parts):
                        run = p.add_run(part)
                        if i % 2 == 1:
                            run.bold = True
            docx.add_page_break()

        buffer = io.BytesIO()
        docx.save(buffer)
        buffer.seek(0)
        return buffer.read()

    # ── Markdown ──
    def _generate_markdown(self, documents: List[Dict[str, Any]]) -> bytes:
        parts = []
        for document in documents:
            parts.append(f"# {document.get('title', 'Untitled')}\n\n")
            parts.append(document.get("content", ""))
            parts.append("\n\n---\n\n")
        return "".join(parts).encode("utf-8")

    # ── CRUD ──
    async def get_user_exports(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(
            COLLECTIONS["exports"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def get_export(self, export_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        export = await self.db.get(COLLECTIONS["exports"], export_id)
        if export and export.get("user_id") == user_id:
            return export
        return None

    async def download_export(self, export_id: str, user_id: str) -> Tuple[bytes, str, str]:
        """Return (file_bytes, filename, content_type)."""
        export = await self.get_export(export_id, user_id)
        if not export:
            raise ValueError("Export not found")

        file_url = export.get("file_url", "")
        if not file_url.startswith("data:"):
            raise ValueError("Export file not available")

        file_content = base64.b64decode(file_url.split(",")[1])
        content_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "markdown": "text/markdown",
        }
        return file_content, export.get("filename", "export"), content_types.get(export.get("format", ""), "application/octet-stream")

    async def delete_export(self, export_id: str, user_id: str) -> bool:
        export = await self.get_export(export_id, user_id)
        if not export:
            return False
        await self.db.delete(COLLECTIONS["exports"], export_id)
        return True
