"""
File Parser Utility
Extracts text from PDF, DOCX, DOC, and TXT files
"""
import io
from typing import Optional

import pdfplumber
from docx import Document as DocxDocument


class FileParser:
    """Utility for extracting text from various file formats."""

    async def extract_text(
        self,
        file_contents: bytes,
        file_type: str
    ) -> str:
        """Extract text from file contents based on file type."""
        file_type = file_type.lower().strip(".")

        if file_type == "pdf":
            return await self._extract_pdf(file_contents)
        elif file_type in ("docx", "doc"):
            return await self._extract_docx(file_contents)
        elif file_type == "txt":
            return await self._extract_txt(file_contents)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    async def _extract_pdf(self, file_contents: bytes) -> str:
        """Extract text from PDF file."""
        text_parts = []

        with pdfplumber.open(io.BytesIO(file_contents)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        full_text = "\n\n".join(text_parts)

        if not full_text.strip():
            raise ValueError("Could not extract text from PDF. The file may be image-based or corrupted.")

        return full_text

    async def _extract_docx(self, file_contents: bytes) -> str:
        """Extract text from DOCX file."""
        try:
            doc = DocxDocument(io.BytesIO(file_contents))
            text_parts = []

            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)

            # Also extract from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(
                        cell.text.strip() for cell in row.cells if cell.text.strip()
                    )
                    if row_text:
                        text_parts.append(row_text)

            full_text = "\n".join(text_parts)

            if not full_text.strip():
                raise ValueError("Could not extract text from document.")

            return full_text

        except Exception as e:
            raise ValueError(f"Failed to parse DOCX file: {str(e)}")

    async def _extract_txt(self, file_contents: bytes) -> str:
        """Extract text from TXT file."""
        try:
            # Try UTF-8 first, then fall back to other encodings
            for encoding in ["utf-8", "utf-16", "latin-1", "cp1252"]:
                try:
                    return file_contents.decode(encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError("Could not decode text file")
        except Exception as e:
            raise ValueError(f"Failed to read text file: {str(e)}")
