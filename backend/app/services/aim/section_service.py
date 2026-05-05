"""
AIM \u2014 SectionService: section CRUD, generate (writer\u2192reviewer loop),
output versioning with current-version pointer, fix diagnostic, and
grade prediction.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from app.core.database import SupabaseDB, TABLES, get_db
from app.services.aim.quality_gate import GateAction, decide, decide_from_attempt

from ai_engine.chains.aim_pipeline import (
    AIMEmitter,
    SectionGenerationResult,
    fix_section,
    generate_section,
    predict_grade,
)


class AIMSectionService:
    def __init__(self, db: Optional[SupabaseDB] = None) -> None:
        self.db = db or get_db()

    # ── Sections ───────────────────────────────────────────────────
    async def list_sections(self, assignment_id: str) -> list[dict[str, Any]]:
        return await self.db.query(
            TABLES["aim_sections"],
            filters=[("assignment_id", "==", assignment_id)],
            order_by="order_index",
            order_direction="ASCENDING",
        )

    async def get_section(self, user_id: str, section_id: str) -> Optional[dict[str, Any]]:
        row = await self.db.get(TABLES["aim_sections"], section_id)
        if not row or row.get("user_id") != user_id:
            return None
        return row

    # ── Outputs (version history) ──────────────────────────────────
    async def list_outputs(self, section_id: str) -> list[dict[str, Any]]:
        return await self.db.query(
            TABLES["aim_section_outputs"],
            filters=[("section_id", "==", section_id)],
            order_by="version",
            order_direction="DESCENDING",
        )

    async def get_current_output(self, section_id: str) -> Optional[dict[str, Any]]:
        rows = await self.db.query(
            TABLES["aim_section_outputs"],
            filters=[("section_id", "==", section_id), ("is_current", "==", True)],
            limit=1,
        )
        return rows[0] if rows else None

    # ── Generation ─────────────────────────────────────────────────
    async def generate(
        self,
        user_id: str,
        section_id: str,
        *,
        max_attempts: int = 3,
        emit: Optional[AIMEmitter] = None,
    ) -> SectionGenerationResult:
        section = await self.get_section(user_id, section_id)
        if not section:
            raise ValueError("section not found")
        # load parsed + recon for the assignment
        analysis_rows = await self.db.query(
            TABLES["aim_assignment_analysis"],
            filters=[("assignment_id", "==", section["assignment_id"])],
            limit=1,
        )
        if not analysis_rows:
            raise ValueError("assignment has not been analyzed yet")
        analysis = analysis_rows[0]
        parsed = {
            "directive": analysis.get("directive"),
            "rubric_breakdown": analysis.get("rubric_breakdown") or [],
            "academic_level": (analysis.get("expectations") or {}).get("academic_level"),
            "referencing_style": (analysis.get("expectations") or {}).get("referencing_style"),
        }
        # Recover from recon_report blob (richer)
        recon = analysis.get("recon_report") or {}

        result = await generate_section(
            section=section,
            parsed=parsed,
            recon=recon,
            section_id=section_id,
            max_attempts=max_attempts,
            emit=emit,
        )
        # persist all attempts; mark final as current
        await self._persist_attempts(user_id, section_id, result)
        return result

    async def _persist_attempts(
        self,
        user_id: str,
        section_id: str,
        result: SectionGenerationResult,
    ) -> None:
        # determine next version offset (in case we already had outputs)
        existing = await self.list_outputs(section_id)
        base_version = max((int(o.get("version", 0)) for o in existing), default=0)
        # demote any current
        for row in existing:
            if row.get("is_current"):
                await self.db.update(
                    TABLES["aim_section_outputs"], row["id"], {"is_current": False}
                )
        for offset, attempt in enumerate(result.history, start=1):
            is_final = attempt is result.final_attempt
            decision = decide_from_attempt(attempt)
            # Only the FINAL attempt is eligible to be surfaced as current,
            # and only if the gate says so. Intermediate attempts are stored
            # for audit but never become current.
            is_current = is_final and decision.is_current
            payload = {
                "section_id": section_id,
                "user_id": user_id,
                "content": attempt.content,
                "quality_score": attempt.weighted_score,
                "sub_scores": (attempt.reviewer or {}).get("sub_scores") or {},
                "reviewer_issues": (attempt.reviewer or {}).get("ranked_issues") or [],
                "blocked_phrases": (attempt.reviewer or {}).get("filter_hits") or [],
                "version": base_version + offset,
                "is_current": is_current,
                "passed_gate": decision.passed_gate,
                "gate_action": decision.action.value,
                "model_used": attempt.model_used,
                "latency_ms": attempt.latency_ms,
            }
            await self.db.create(TABLES["aim_section_outputs"], payload)

    # ── Fix-My-Section ────────────────────────────────────────────
    async def fix(self, user_id: str, section_id: str, draft: str) -> dict[str, Any]:
        section = await self.get_section(user_id, section_id)
        if not section:
            raise ValueError("section not found")
        analysis_rows = await self.db.query(
            TABLES["aim_assignment_analysis"],
            filters=[("assignment_id", "==", section["assignment_id"])],
            limit=1,
        )
        analysis = analysis_rows[0] if analysis_rows else {}
        parsed = {
            "directive": analysis.get("directive"),
            "rubric_breakdown": analysis.get("rubric_breakdown") or [],
        }
        return await fix_section(section, parsed, draft)

    async def save_manual_output(
        self,
        user_id: str,
        section_id: str,
        content: str,
        quality_score: float | None = None,
    ) -> dict[str, Any]:
        """Persist a user-supplied draft (e.g. accepted Fix-My-Section revision)
        as a new current version. Demotes any prior current."""
        section = await self.get_section(user_id, section_id)
        if not section:
            raise ValueError("section not found")
        if not content or not content.strip():
            raise ValueError("content is required")
        existing = await self.list_outputs(section_id)
        for row in existing:
            if row.get("is_current"):
                await self.db.update(
                    TABLES["aim_section_outputs"], row["id"], {"is_current": False}
                )
        next_version = max((int(o.get("version", 0)) for o in existing), default=0) + 1
        decision = decide(quality_score or 0.0, force=True)
        payload = {
            "section_id": section_id,
            "user_id": user_id,
            "content": content,
            "quality_score": quality_score,
            "sub_scores": {},
            "reviewer_issues": [],
            "blocked_phrases": [],
            "version": next_version,
            "is_current": True,
            "passed_gate": (quality_score or 0) >= 85,
            "gate_action": (
                GateAction.SHOW.value if (quality_score or 0) >= 85 else decision.action.value
            ),
            "model_used": "manual",
            "latency_ms": 0,
        }
        new_id = await self.db.create(TABLES["aim_section_outputs"], payload)
        payload["id"] = new_id
        return payload

    # ── Grade prediction ──────────────────────────────────────────
    async def predict_grade_for_assignment(
        self, user_id: str, assignment_id: str
    ) -> dict[str, Any]:
        sections = await self.list_sections(assignment_id)
        if not sections:
            raise ValueError("no sections to evaluate")
        section_reviews: list[dict[str, Any]] = []
        for s in sections:
            current = await self.get_current_output(s["id"])
            if not current:
                continue
            section_reviews.append({
                "section_title": s.get("title"),
                "sub_scores": current.get("sub_scores") or {},
                "ranked_issues": current.get("reviewer_issues") or [],
            })
        if not section_reviews:
            raise ValueError("no generated sections to evaluate yet")
        analysis_rows = await self.db.query(
            TABLES["aim_assignment_analysis"],
            filters=[("assignment_id", "==", assignment_id)],
            limit=1,
        )
        analysis = analysis_rows[0] if analysis_rows else {}
        parsed = {
            "directive": analysis.get("directive"),
            "rubric_breakdown": analysis.get("rubric_breakdown") or [],
            "academic_level": (analysis.get("expectations") or {}).get("academic_level"),
        }
        prediction = await predict_grade(parsed, section_reviews)
        # persist evaluation
        eval_row = {
            "assignment_id": assignment_id,
            "user_id": user_id,
            "predicted_grade_low": prediction.get("predicted_grade_low"),
            "predicted_grade_high": prediction.get("predicted_grade_high"),
            "band": prediction.get("band"),
            "overall_quality": sum(
                float(r.get("sub_scores", {}).get("directive_alignment", 0))
                for r in section_reviews
            ) / max(1, len(section_reviews)),
            "per_criterion": prediction.get("per_criterion") or [],
            "feedback": prediction.get("feedback") or {},
            "reasoning": prediction.get("reasoning"),
        }
        await self.db.create(TABLES["aim_evaluations"], eval_row)
        return prediction
