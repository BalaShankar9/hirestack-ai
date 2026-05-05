"""
AIM \u2014 Document parsing helper.

Accepts the same upload formats as the resume parser (`FileParser`) and
returns plain text for the Parser agent.
"""
from __future__ import annotations

from typing import Optional

from app.services.file_parser import FileParser


class AIMDocumentParser:
    def __init__(self) -> None:
        self.parser = FileParser()

    async def parse(self, file_bytes: bytes, file_type: str) -> str:
        """`file_type` is a file extension like 'pdf', 'docx', 'txt'."""
        text = await self.parser.extract_text(file_bytes, file_type)
        return (text or "").strip()

    @staticmethod
    def ext_from_filename(name: Optional[str]) -> str:
        if not name or "." not in name:
            return "txt"
        return name.rsplit(".", 1)[-1].lower()
