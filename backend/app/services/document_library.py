"""
Document Library Service — manages Benchmark, Fixed, and Tailored documents.

Three document categories:
  • benchmark  – Ideal-candidate standard (per-application, auto-generated)
  • fixed      – User's persistent library (cross-application, evolves over time)
  • tailored   – Job-specific adapted documents (per-application, planner-decided)
"""
from __future__ import annotations

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = structlog.get_logger("hirestack.document_library")


# ═══════════════════════════════════════════════════════════════════════
#  Core document type definitions
# ═══════════════════════════════════════════════════════════════════════

# Documents that every application should have in its benchmark library
BENCHMARK_DOCUMENT_TYPES = [
    {"key": "cv", "label": "Benchmark CV"},
    {"key": "cover_letter", "label": "Benchmark Cover Letter"},
    {"key": "personal_statement", "label": "Benchmark Personal Statement"},
    {"key": "executive_summary", "label": "Benchmark Executive Summary"},
    {"key": "skills_matrix", "label": "Benchmark Skills Matrix"},
]

# Documents that belong in every user's fixed library (cross-application)
FIXED_DOCUMENT_TYPES = [
    {"key": "master_cv", "label": "Master CV"},
    {"key": "career_narrative", "label": "Career Narrative"},
    {"key": "core_competencies", "label": "Core Competencies"},
    {"key": "evidence_portfolio", "label": "Evidence Portfolio"},
    {"key": "skills_inventory", "label": "Skills Inventory"},
]


# ═══════════════════════════════════════════════════════════════════════
#  Document Library Service
# ═══════════════════════════════════════════════════════════════════════

class DocumentLibraryService:
    """Manages the three-tier document library (benchmark, fixed, tailored)."""

    def __init__(self, db: Any, tables: Dict[str, str]) -> None:
        self._db = db
        self._tables = tables

    # ── Read operations ───────────────────────────────────────────

    async def get_application_documents(
        self, user_id: str, application_id: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get all documents for an application, organized by category."""
        resp = await asyncio.to_thread(
            lambda: self._db.table(self._tables["document_library"])
            .select("*")
            .eq("user_id", user_id)
            .or_(f"application_id.eq.{application_id},application_id.is.null")
            .order("doc_category")
            .order("created_at")
            .execute()
        )
        rows = resp.data or []
        result: Dict[str, List[Dict[str, Any]]] = {
            "benchmark": [],
            "fixed": [],
            "tailored": [],
        }
        for row in rows:
            cat = row.get("doc_category", "tailored")
            if cat in result:
                result[cat].append(row)
        return result

    async def get_documents_by_category(
        self, user_id: str, category: str, application_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get documents for a specific category."""
        query = (
            self._db.table(self._tables["document_library"])
            .select("*")
            .eq("user_id", user_id)
            .eq("doc_category", category)
            .order("created_at")
        )
        if application_id and category != "fixed":
            query = query.eq("application_id", application_id)
        elif category == "fixed":
            query = query.is_("application_id", "null")
        resp = await asyncio.to_thread(lambda: query.execute())
        return resp.data or []

    async def get_document(self, user_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single document by ID."""
        resp = await asyncio.to_thread(
            lambda: self._db.table(self._tables["document_library"])
            .select("*")
            .eq("id", doc_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return resp.data if resp else None

    # ── Write operations ──────────────────────────────────────────

    async def create_document(
        self,
        user_id: str,
        doc_type: str,
        doc_category: str,
        label: str,
        *,
        application_id: Optional[str] = None,
        html_content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        status: str = "planned",
        source: str = "planner",
    ) -> Dict[str, Any]:
        """Create a new document in the library."""
        row = {
            "user_id": user_id,
            "application_id": application_id,
            "doc_type": doc_type,
            "doc_category": doc_category,
            "label": label,
            "html_content": html_content,
            "metadata": metadata or {},
            "status": status,
            "source": source,
        }
        resp = await asyncio.to_thread(
            lambda: self._db.table(self._tables["document_library"])
            .insert(row)
            .execute()
        )
        return (resp.data or [{}])[0]

    async def update_document(
        self, user_id: str, doc_id: str, patch: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing document."""
        allowed_fields = {
            "html_content", "metadata", "status", "label",
            "version", "error_message",
        }
        safe_patch = {k: v for k, v in patch.items() if k in allowed_fields}
        if not safe_patch:
            return None
        resp = await asyncio.to_thread(
            lambda: self._db.table(self._tables["document_library"])
            .update(safe_patch)
            .eq("id", doc_id)
            .eq("user_id", user_id)
            .execute()
        )
        return (resp.data or [None])[0]

    async def update_document_content(
        self, user_id: str, doc_id: str, html_content: str, *, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update document content and mark as ready."""
        patch: Dict[str, Any] = {
            "html_content": html_content,
            "status": "ready",
        }
        if metadata:
            patch["metadata"] = metadata
        await asyncio.to_thread(
            lambda: self._db.table(self._tables["document_library"])
            .update(patch)
            .eq("id", doc_id)
            .eq("user_id", user_id)
            .execute()
        )

    # ── Bulk operations for pipeline ──────────────────────────────

    async def create_planned_documents(
        self,
        user_id: str,
        application_id: str,
        documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Create multiple planned documents at once (from planner output).
        Each dict in documents should have: doc_type, doc_category, label, and optional metadata.
        """
        rows = []
        for doc in documents:
            rows.append({
                "user_id": user_id,
                "application_id": application_id if doc.get("doc_category") != "fixed" else None,
                "doc_type": doc["doc_type"],
                "doc_category": doc.get("doc_category", "tailored"),
                "label": doc.get("label", doc["doc_type"].replace("_", " ").title()),
                "html_content": "",
                "metadata": doc.get("metadata", {}),
                "status": "planned",
                "source": doc.get("source", "planner"),
            })
        if not rows:
            return []
        resp = await asyncio.to_thread(
            lambda: self._db.table(self._tables["document_library"])
            .insert(rows)
            .execute()
        )
        return resp.data or []

    async def mark_generating(self, user_id: str, doc_ids: List[str]) -> None:
        """Mark a batch of documents as generating."""
        for doc_id in doc_ids:
            await asyncio.to_thread(
                lambda did=doc_id: self._db.table(self._tables["document_library"])
                .update({"status": "generating"})
                .eq("id", did)
                .eq("user_id", user_id)
                .execute()
            )

    async def mark_error(self, user_id: str, doc_id: str, error_message: str) -> None:
        """Mark a document as failed."""
        await asyncio.to_thread(
            lambda: self._db.table(self._tables["document_library"])
            .update({"status": "error", "error_message": error_message[:500]})
            .eq("id", doc_id)
            .eq("user_id", user_id)
            .execute()
        )

    # ── Initialization helpers ────────────────────────────────────

    async def ensure_fixed_library(self, user_id: str) -> List[Dict[str, Any]]:
        """Ensure the user has a fixed document library. Creates planned entries if missing."""
        existing = await self.get_documents_by_category(user_id, "fixed")
        existing_types = {d["doc_type"] for d in existing}

        new_docs = []
        for doc_def in FIXED_DOCUMENT_TYPES:
            if doc_def["key"] not in existing_types:
                new_docs.append({
                    "doc_type": doc_def["key"],
                    "doc_category": "fixed",
                    "label": doc_def["label"],
                    "source": "auto_evolve",
                })

        if new_docs:
            created = await self.create_planned_documents(user_id, "", new_docs)
            existing.extend(created)

        return existing

    async def create_benchmark_library(
        self, user_id: str, application_id: str,
        extra_types: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Create the benchmark document library for an application."""
        docs = []
        for doc_def in BENCHMARK_DOCUMENT_TYPES:
            docs.append({
                "doc_type": doc_def["key"],
                "doc_category": "benchmark",
                "label": doc_def["label"],
            })
        for extra in (extra_types or []):
            docs.append({
                "doc_type": extra.get("key", extra.get("doc_type", "")),
                "doc_category": "benchmark",
                "label": extra.get("label", ""),
            })
        return await self.create_planned_documents(user_id, application_id, docs)

    async def create_tailored_documents_from_plan(
        self,
        user_id: str,
        application_id: str,
        planned_docs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Create tailored document entries from the planner's output."""
        docs = []
        for d in planned_docs:
            docs.append({
                "doc_type": d.get("key", d.get("doc_type", "")),
                "doc_category": "tailored",
                "label": d.get("label", ""),
                "metadata": {k: v for k, v in d.items() if k not in ("key", "doc_type", "label")},
            })
        return await self.create_planned_documents(user_id, application_id, docs)

    # ── Summary for pipeline/mission control ──────────────────────

    async def get_library_summary(
        self, user_id: str, application_id: str
    ) -> Dict[str, Any]:
        """Get a summary of the document library state for an application."""
        all_docs = await self.get_application_documents(user_id, application_id)
        summary: Dict[str, Any] = {}
        for category, docs in all_docs.items():
            total = len(docs)
            ready = sum(1 for d in docs if d.get("status") == "ready")
            generating = sum(1 for d in docs if d.get("status") == "generating")
            planned = sum(1 for d in docs if d.get("status") == "planned")
            error = sum(1 for d in docs if d.get("status") == "error")
            summary[category] = {
                "total": total,
                "ready": ready,
                "generating": generating,
                "planned": planned,
                "error": error,
            }
        return summary
