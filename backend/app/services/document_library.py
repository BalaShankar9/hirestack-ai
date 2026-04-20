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
from typing import Any, Dict, List, Optional

logger = structlog.get_logger("hirestack.document_library")


# ═══════════════════════════════════════════════════════════════════════
#  Core document type definitions
# ═══════════════════════════════════════════════════════════════════════

# Documents that every application should have in its benchmark library
# Canonical 6-doc benchmark base set: CV (long-form), Resume (1–2 page),
# Cover Letter, Personal Statement, Portfolio, Learning Plan.
# Other doc types (executive_summary, skills_matrix, interview_prep, etc.)
# are now planner-driven optional/required docs rather than always-on benchmark.
BENCHMARK_DOCUMENT_TYPES = [
    {"key": "cv",                  "label": "Benchmark CV"},
    {"key": "resume",              "label": "Benchmark Résumé"},
    {"key": "cover_letter",        "label": "Benchmark Cover Letter"},
    {"key": "personal_statement",  "label": "Benchmark Personal Statement"},
    {"key": "portfolio",           "label": "Benchmark Portfolio"},
    {"key": "learning_plan",       "label": "Benchmark Learning Plan"},
]

# Documents that belong in every user's fixed library (cross-application)
FIXED_DOCUMENT_TYPES = [
    {"key": "master_cv", "label": "Master CV"},
    {"key": "career_narrative", "label": "Career Narrative"},
    {"key": "core_competencies", "label": "Core Competencies"},
    {"key": "evidence_portfolio", "label": "Evidence Portfolio"},
    {"key": "skills_inventory", "label": "Skills Inventory"},
    {"key": "professional_summary", "label": "Professional Summary"},
    {"key": "achievements_log", "label": "Achievements Log"},
    {"key": "certifications_tracker", "label": "Certifications & Training"},
    {"key": "references_sheet", "label": "References Sheet"},
    {"key": "career_timeline", "label": "Career Timeline"},
]

# Template content for fixed documents (shown as starter content)
FIXED_DOCUMENT_TEMPLATES: Dict[str, str] = {
    "master_cv": (
        "<h1>Master CV</h1>"
        "<p>Your comprehensive career document containing <strong>all</strong> roles, skills, projects, "
        "and accomplishments. This is your single source of truth — tailored CVs are generated from this.</p>"
        "<h2>How to use</h2>"
        "<ul><li>Add every role you've held, including dates and key achievements</li>"
        "<li>Include all certifications, education, and professional development</li>"
        "<li>List technical skills, tools, and methodologies</li>"
        "<li>HireStack AI will tailor job-specific CVs from this master document</li></ul>"
    ),
    "career_narrative": (
        "<h1>Career Narrative</h1>"
        "<p>A compelling story of your professional journey — connecting your experiences, motivations, "
        "and aspirations into a cohesive narrative.</p>"
        "<h2>How to use</h2>"
        "<ul><li>Describe the thread that connects your career moves</li>"
        "<li>Highlight pivotal moments and what you learned</li>"
        "<li>Explain your professional mission and values</li>"
        "<li>This feeds into cover letters and personal statements</li></ul>"
    ),
    "core_competencies": (
        "<h1>Core Competencies</h1>"
        "<p>An inventory of your top professional competencies with evidence and proficiency levels.</p>"
        "<h2>How to use</h2>"
        "<ul><li>List your top 10–15 competencies</li>"
        "<li>Rate your proficiency: Expert / Advanced / Intermediate</li>"
        "<li>Link each competency to concrete evidence (projects, results)</li>"
        "<li>HireStack uses this to match you against job requirements</li></ul>"
    ),
    "evidence_portfolio": (
        "<h1>Evidence Portfolio</h1>"
        "<p>A structured collection of evidence supporting your competency claims — projects, metrics, "
        "testimonials, and artifacts.</p>"
        "<h2>How to use</h2>"
        "<ul><li>Add STAR-format entries (Situation, Task, Action, Result)</li>"
        "<li>Include quantified outcomes where possible</li>"
        "<li>Attach or reference supporting documents and links</li>"
        "<li>This powers the evidence-backed claims in your applications</li></ul>"
    ),
    "skills_inventory": (
        "<h1>Skills Inventory</h1>"
        "<p>A complete catalog of your technical and soft skills with proficiency ratings.</p>"
        "<h2>How to use</h2>"
        "<ul><li>Categorize skills: Technical, Leadership, Domain, Tools</li>"
        "<li>Rate each skill's proficiency and recency</li>"
        "<li>HireStack AI uses this for gap analysis and keyword optimization</li></ul>"
    ),
    "professional_summary": (
        "<h1>Professional Summary</h1>"
        "<p>A concise, polished elevator pitch summarizing who you are, what you do, and the value you bring.</p>"
        "<h2>How to use</h2>"
        "<ul><li>Keep it to 3–5 sentences</li>"
        "<li>Lead with your strongest value proposition</li>"
        "<li>Include years of experience and key specializations</li>"
        "<li>This appears at the top of generated CVs and LinkedIn profiles</li></ul>"
    ),
    "achievements_log": (
        "<h1>Achievements Log</h1>"
        "<p>A chronological record of your professional achievements with metrics and impact.</p>"
        "<h2>How to use</h2>"
        "<ul><li>Record achievements as they happen</li>"
        "<li>Include quantified impact (%, $, time saved)</li>"
        "<li>Tag each with relevant skills and competencies</li>"
        "<li>HireStack pulls from this to strengthen application claims</li></ul>"
    ),
    "certifications_tracker": (
        "<h1>Certifications & Training</h1>"
        "<p>Track all your professional certifications, courses, and training with dates and status.</p>"
        "<h2>How to use</h2>"
        "<ul><li>List certification name, issuing body, and date</li>"
        "<li>Track renewal dates and continuing education requirements</li>"
        "<li>Include online courses and workshops</li>"
        "<li>HireStack highlights relevant certifications per application</li></ul>"
    ),
    "references_sheet": (
        "<h1>References Sheet</h1>"
        "<p>A ready-to-share document with your professional references, pre-formatted for employers.</p>"
        "<h2>How to use</h2>"
        "<ul><li>Include 3–5 professional references</li>"
        "<li>List name, title, relationship, and contact info</li>"
        "<li>Always confirm permission before listing someone</li>"
        "<li>Keep updated — this is shared on request during interviews</li></ul>"
    ),
    "career_timeline": (
        "<h1>Career Timeline</h1>"
        "<p>A visual timeline of your career progression showing roles, promotions, and key milestones.</p>"
        "<h2>How to use</h2>"
        "<ul><li>Add each role with start/end dates</li>"
        "<li>Mark promotions, lateral moves, and industry changes</li>"
        "<li>Include education and certification milestones</li>"
        "<li>HireStack uses this to tell your career growth story</li></ul>"
    ),
}


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
        application_id: Optional[str],
        documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Create multiple planned documents at once (from planner output).
        Each dict in documents should have: doc_type, doc_category, label, and optional metadata.
        """
        rows = []
        for doc in documents:
            rows.append({
                "user_id": user_id,
                "application_id": application_id if (application_id and doc.get("doc_category") != "fixed") else None,
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

    async def upsert_application_document(
        self,
        *,
        user_id: str,
        application_id: str,
        doc_category: str,
        doc_type: str,
        label: str,
        html_content: str = "",
        status: str = "ready",
        source: str = "planner",
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find an existing planned/generating row for (user, app, category, type)
        and update it; otherwise insert a new row.

        This is the durable persistence primitive used by pipeline_runtime so that
        pre-created "planned" placeholders evolve into "ready"/"error" rows rather
        than being duplicated. Failures here MUST NOT raise — they degrade to a
        warning and return an empty dict so the caller can keep moving.
        """
        try:
            # Look for an existing row for this slot (most recent first).
            existing_resp = await asyncio.to_thread(
                lambda: self._db.table(self._tables["document_library"])
                .select("id,status")
                .eq("user_id", user_id)
                .eq("application_id", application_id)
                .eq("doc_category", doc_category)
                .eq("doc_type", doc_type)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            existing = (existing_resp.data or [None])[0]

            if existing and existing.get("id"):
                patch: Dict[str, Any] = {
                    "html_content": html_content,
                    "status": status,
                    "label": label,
                }
                if metadata is not None:
                    patch["metadata"] = metadata
                if error_message is not None:
                    patch["error_message"] = error_message[:500]
                resp = await asyncio.to_thread(
                    lambda: self._db.table(self._tables["document_library"])
                    .update(patch)
                    .eq("id", existing["id"])
                    .eq("user_id", user_id)
                    .execute()
                )
                return (resp.data or [{}])[0]

            # No existing row → insert fresh
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
            if error_message is not None:
                row["error_message"] = error_message[:500]
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._tables["document_library"])
                .insert(row)
                .execute()
            )
            return (resp.data or [{}])[0]
        except Exception as ex:
            logger.warning(
                "document_library.upsert_failed",
                doc_type=doc_type,
                doc_category=doc_category,
                error=str(ex)[:200],
            )
            return {}

    # ── Initialization helpers ────────────────────────────────────

    async def ensure_fixed_library(self, user_id: str) -> List[Dict[str, Any]]:
        """Ensure the user has a fixed document library. Creates entries with template content if missing."""
        existing = await self.get_documents_by_category(user_id, "fixed")
        existing_types = {d["doc_type"] for d in existing}

        new_rows = []
        for doc_def in FIXED_DOCUMENT_TYPES:
            if doc_def["key"] not in existing_types:
                template = FIXED_DOCUMENT_TEMPLATES.get(doc_def["key"], "")
                new_rows.append({
                    "user_id": user_id,
                    "application_id": None,
                    "doc_type": doc_def["key"],
                    "doc_category": "fixed",
                    "label": doc_def["label"],
                    "html_content": template,
                    "metadata": {},
                    "status": "ready" if template else "planned",
                    "source": "auto_evolve",
                })

        if new_rows:
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._tables["document_library"])
                .insert(new_rows)
                .execute()
            )
            created = resp.data or []
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
