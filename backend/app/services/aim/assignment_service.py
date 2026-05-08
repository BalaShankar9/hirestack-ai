"""
AIM \u2014 AssignmentService: CRUD + analyze (Parser+Recon) orchestration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.core.database import SupabaseDB, TABLES, get_db

from ai_engine.chains.aim_pipeline import AnalysisResult, analyze_assignment


class AIMAssignmentService:
    def __init__(self, db: Optional[SupabaseDB] = None) -> None:
        self.db = db or get_db()

    # ── CRUD ───────────────────────────────────────────────────────
    async def create(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "user_id": user_id,
            "title": payload.get("title") or "Untitled assignment",
            "course": payload.get("course"),
            "academic_level": payload.get("academic_level"),
            "referencing_style": payload.get("referencing_style"),
            "deadline": payload.get("deadline"),
            "word_count": payload.get("word_count"),
            "status": "draft",
        }
        new_id = await self.db.create(TABLES["aim_assignments"], row)
        row["id"] = new_id
        return row

    async def get(self, user_id: str, assignment_id: str) -> Optional[dict[str, Any]]:
        row = await self.db.get(TABLES["aim_assignments"], assignment_id)
        if not row or row.get("user_id") != user_id:
            return None
        return row

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return await self.db.query(
            TABLES["aim_assignments"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def update_status(self, assignment_id: str, status_value: str) -> None:
        await self.db.update(
            TABLES["aim_assignments"],
            assignment_id,
            {"status": status_value, "updated_at": datetime.now(timezone.utc).isoformat()},
        )

    async def delete(self, user_id: str, assignment_id: str) -> bool:
        existing = await self.get(user_id, assignment_id)
        if not existing:
            return False
        return await self.db.delete(TABLES["aim_assignments"], assignment_id)

    # ── Documents ──────────────────────────────────────────────────
    async def attach_document(
        self,
        user_id: str,
        assignment_id: str,
        *,
        doc_type: str,
        file_name: Optional[str],
        raw_text: str,
    ) -> dict[str, Any]:
        doc = {
            "assignment_id": assignment_id,
            "user_id": user_id,
            "type": doc_type,
            "file_name": file_name,
            "raw_text": raw_text,
        }
        doc_id = await self.db.create(TABLES["aim_assignment_documents"], doc)
        doc["id"] = doc_id
        return doc

    async def get_documents(self, assignment_id: str) -> list[dict[str, Any]]:
        return await self.db.query(
            TABLES["aim_assignment_documents"],
            filters=[("assignment_id", "==", assignment_id)],
            order_by="created_at",
            order_direction="ASCENDING",
        )

    # ── Analysis ───────────────────────────────────────────────────
    async def analyze(self, user_id: str, assignment_id: str) -> AnalysisResult:
        assignment = await self.get(user_id, assignment_id)
        if not assignment:
            raise ValueError("assignment not found")
        docs = await self.get_documents(assignment_id)
        brief_parts = [d.get("raw_text", "") for d in docs if d.get("type") == "brief"]
        rubric_parts = [d.get("raw_text", "") for d in docs if d.get("type") == "rubric"]
        brief_text = "\n\n".join([p for p in brief_parts if p]).strip()
        rubric_text = "\n\n".join([p for p in rubric_parts if p]).strip()
        if not brief_text:
            raise ValueError("at least one document of type='brief' is required before analysis")

        await self.update_status(assignment_id, "analyzing")
        try:
            analysis = await analyze_assignment(brief_text, rubric_text)
        except Exception:
            await self.update_status(assignment_id, "failed")
            raise

        # persist analysis
        await self._upsert_analysis(user_id, assignment_id, analysis)

        if analysis.needs_clarification:
            await self.update_status(assignment_id, "draft")
        else:
            await self._materialize_sections(user_id, assignment_id, analysis.recon or {})
            await self.update_status(assignment_id, "ready")
        return analysis

    async def _upsert_analysis(
        self, user_id: str, assignment_id: str, analysis: AnalysisResult
    ) -> None:
        existing = await self.db.query(
            TABLES["aim_assignment_analysis"],
            filters=[("assignment_id", "==", assignment_id)],
            limit=1,
        )
        recon = analysis.recon or {}
        payload = {
            "assignment_id": assignment_id,
            "user_id": user_id,
            "directive": analysis.parsed.get("directive"),
            "parser_confidence": analysis.parser_confidence,
            "needs_clarification": analysis.needs_clarification,
            "clarification_questions": analysis.clarification_questions or None,
            "structure": recon.get("structure") or [],
            "rubric_breakdown": analysis.parsed.get("rubric_breakdown") or [],
            "expectations": {
                "academic_level": analysis.parsed.get("academic_level"),
                "referencing_style": analysis.parsed.get("referencing_style"),
                "hidden_expectations": analysis.parsed.get("hidden_expectations") or [],
                "distinction_strategy": recon.get("distinction_strategy"),
                "mark_loss_patterns": recon.get("mark_loss_patterns") or [],
                "what_its_really_asking": recon.get("what_its_really_asking"),
                "section_strategy": recon.get("section_strategy") or [],
            },
            "recon_report": recon,
            "recon_version": (existing[0].get("recon_version", 0) + 1) if existing else 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if existing:
            await self.db.update(
                TABLES["aim_assignment_analysis"], existing[0]["id"], payload
            )
        else:
            await self.db.create(TABLES["aim_assignment_analysis"], payload)

    async def _materialize_sections(
        self, user_id: str, assignment_id: str, recon: dict[str, Any]
    ) -> None:
        """Reconcile aim_sections rows from recon.structure.

        Re-analysis must update the section plan rather than silently no-op.
        Existing sections are updated in place by ``order_index``; new sections
        are created; stale sections are deleted only when they have no outputs
        or deadline tasks attached.
        """
        desired = sorted(
            recon.get("structure") or [],
            key=lambda sec: int(sec.get("order_index", 0)),
        )
        existing = await self.db.query(
            TABLES["aim_sections"],
            filters=[("assignment_id", "==", assignment_id)],
            order_by="order_index",
            order_direction="ASCENDING",
        )
        existing_by_order = {
            int(row.get("order_index", 0)): row
            for row in existing
        }
        seen_orders: set[int] = set()

        for sec in desired:
            order_index = int(sec.get("order_index", 0))
            seen_orders.add(order_index)
            row = {
                "assignment_id": assignment_id,
                "user_id": user_id,
                "title": sec.get("title", "Section"),
                "order_index": order_index,
                "word_limit": int(sec.get("word_limit") or 0) or None,
                "purpose": sec.get("purpose"),
                "key_argument": sec.get("key_argument"),
                "rubric_links": sec.get("rubric_links") or [],
            }
            current = existing_by_order.get(order_index)
            if current:
                await self.db.update(TABLES["aim_sections"], current["id"], row)
            else:
                await self.db.create(TABLES["aim_sections"], row)

        for row in existing:
            order_index = int(row.get("order_index", 0))
            if order_index in seen_orders:
                continue
            if await self._section_has_artifacts(row["id"]):
                continue
            await self.db.delete(TABLES["aim_sections"], row["id"])

    async def _section_has_artifacts(self, section_id: str) -> bool:
        outputs = await self.db.query(
            TABLES["aim_section_outputs"],
            filters=[("section_id", "==", section_id)],
            limit=1,
        )
        if outputs:
            return True
        tasks = await self.db.query(
            TABLES["aim_tasks"],
            filters=[("section_id", "==", section_id)],
            limit=1,
        )
        return bool(tasks)

    async def get_analysis(self, assignment_id: str) -> Optional[dict[str, Any]]:
        rows = await self.db.query(
            TABLES["aim_assignment_analysis"],
            filters=[("assignment_id", "==", assignment_id)],
            limit=1,
        )
        return rows[0] if rows else None
