"""
Export Service
Handles document export to PDF/DOCX formats with Supabase
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import io
import base64
import structlog

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph as RLParagraph, Spacer
from reportlab.lib.units import inch
from docx import Document as DocxDocument
from docx.shared import Pt, Cm

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()


def generate_docx_from_html(html_content: str, document_type: str = "cv") -> bytes:
    """Convert HTML content to proper DOCX using python-docx."""
    import re

    doc = DocxDocument()
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)

    text = re.sub(r"<br\s*/?>", "\n", html_content)
    text = re.sub(r"</(p|div|h[1-6]|li)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    for para_text in paragraphs:
        p = doc.add_paragraph(para_text)
        p.style.font.size = Pt(11)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


class ExportService:
    """Service for export operations using Supabase."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def create_export(
        self,
        user_id: str,
        document_ids: List[str] = None,
        fmt: str = "pdf",
        filename: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an export bundle from application documents or standalone documents."""
        documents: List[Dict[str, Any]] = []

        # If options contains application_id, export from the applications table
        app_id = (options or {}).get("application_id")
        if app_id:
            app = await self.db.get(TABLES["applications"], app_id)
            if not app or app.get("user_id") != user_id:
                raise ValueError("Application not found or not accessible")

            doc_types = (options or {}).get("document_types", ["cv", "cover_letter"])
            type_map = {
                "cv": ("Tailored CV", "cv_html"),
                "cover_letter": ("Cover Letter", "cover_letter_html"),
                "personal_statement": ("Personal Statement", "personal_statement_html"),
                "portfolio": ("Portfolio", "portfolio_html"),
            }
            for dt in doc_types:
                if dt in type_map:
                    title, field = type_map[dt]
                    content = app.get(field, "")
                    if content:
                        documents.append({"title": title, "content": content, "format": "html"})
        elif document_ids:
            # Fallback: fetch from documents table
            for did in document_ids:
                doc = await self.db.get(TABLES["documents"], did)
                if not doc or doc.get("user_id") != user_id:
                    raise ValueError(f"Document {did} not found or not accessible")
                documents.append(doc)

        if not documents:
            raise ValueError("No documents to export")

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

        # Store as base64 in Supabase (for small exports; production should use Supabase Storage)
        b64 = base64.b64encode(file_bytes).decode()
        record = {
            "user_id": user_id,
            "document_ids": document_ids or [],
            "format": fmt,
            "filename": filename,
            "file_size": len(file_bytes),
            "file_url": f"data:application/octet-stream;base64,{b64}",
            "options": options,
            "status": "completed",
        }
        doc_id = await self.db.create(TABLES["exports"], record)
        logger.info("export_created", export_id=doc_id, format=fmt, doc_count=len(documents))
        return await self.db.get(TABLES["exports"], doc_id)

    def _strip_html(self, html: str) -> str:
        """Simple HTML to plain text conversion."""
        import re
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'</(p|div|h[1-6]|li|tr)>', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&#\d+;', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    # ── PDF ──
    def _generate_pdf(self, documents: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("CustomTitle", parent=styles["Heading1"], fontSize=18, spaceAfter=12)
        body_style = ParagraphStyle("CustomBody", parent=styles["Normal"], fontSize=11, spaceAfter=6, leading=14)
        story: list = []

        for document in documents:
            story.append(RLParagraph(document.get("title", "Untitled"), title_style))
            story.append(Spacer(1, 12))

            content = document.get("content", "")
            # If content is HTML, strip tags for PDF
            if "<" in content and ">" in content:
                content = self._strip_html(content)

            for para in content.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                # Escape XML special chars for reportlab
                para = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(RLParagraph(para, body_style))
            story.append(Spacer(1, 24))

        if not story:
            story.append(RLParagraph("No content to export.", body_style))

        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    # ── DOCX ──
    def _generate_docx(self, documents: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> bytes:
        docx = DocxDocument()
        for document in documents:
            docx.add_heading(document.get("title", "Untitled"), level=1)

            content = document.get("content", "")
            if "<" in content and ">" in content:
                content = self._strip_html(content)

            for para in content.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                if para.startswith("#"):
                    level = min(len(para.split()[0].rstrip("#")), 4)
                    docx.add_heading(para.lstrip("#").strip(), level=level + 1)
                elif para.startswith("- ") or para.startswith("* "):
                    docx.add_paragraph(para[2:], style="List Bullet")
                else:
                    docx.add_paragraph(para)
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
            content = document.get("content", "")
            if "<" in content and ">" in content:
                content = self._strip_html(content)
            parts.append(content)
            parts.append("\n\n---\n\n")
        return "".join(parts).encode("utf-8")

    # ── CRUD ──
    async def get_user_exports(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(
            TABLES["exports"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def get_export(self, export_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        export = await self.db.get(TABLES["exports"], export_id)
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
        await self.db.delete(TABLES["exports"], export_id)
        return True
