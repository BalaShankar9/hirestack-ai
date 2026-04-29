"""
Document Variant Service
Multi-variant document generation (A/B Doc Lab) with Supabase
"""
from typing import Optional, Dict, Any, List
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from ai_engine.client import get_ai_client
from ai_engine.chains.doc_variant import DocumentVariantChain

logger = structlog.get_logger()

TONES = ["conservative", "balanced", "creative"]


class DocVariantService:
    """Service for generating and comparing document variants."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.ai_client = get_ai_client()

    async def generate_variants(
        self,
        user_id: str,
        original_content: str,
        document_type: str,
        job_title: str = "",
        company: str = "",
        application_id: Optional[str] = None,
        tones: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate multiple tone variants of a document."""
        tones_to_generate = tones or TONES
        chain = DocumentVariantChain(self.ai_client)

        variants = {}
        saved = []

        for tone in tones_to_generate:
            content = await chain.generate_variant(
                document_content=original_content,
                document_type=document_type,
                tone=tone,
                job_title=job_title,
                company=company,
            )
            variants[tone] = content

            word_count = len(content.split())
            record = {
                "user_id": user_id,
                "application_id": application_id,
                "document_type": document_type,
                "variant_name": tone,
                "tone": tone,
                "content": content,
                "word_count": word_count,
                "is_selected": tone == "balanced",
            }
            doc_id = await self.db.create(TABLES["doc_variants"], record)
            saved.append({**record, "id": doc_id})

        # Compare variants — adds evidence_coverage, deltas, and a
        # system-recommended winner with AI-generated reasoning.
        comparison = await chain.compare_variants(
            variants=variants,
            job_title=job_title,
            company=company,
            original_content=original_content,
        )

        winner_tone = (comparison.get("winner") or {}).get("variant")

        # Update scores from comparison and persist evidence_coverage +
        # winner metadata in ai_analysis JSONB.
        for comp in comparison.get("comparison", []):
            variant_name = comp.get("variant", "")
            for s in saved:
                if s["variant_name"] == variant_name:
                    is_winner = winner_tone == variant_name
                    ai_analysis = dict(comp)
                    if is_winner:
                        ai_analysis["winner_reasoning"] = (
                            comparison.get("winner") or {}
                        ).get("reasoning")
                    await self.db.update(TABLES["doc_variants"], s["id"], {
                        "ats_score": comp.get("ats_score"),
                        "readability_score": comp.get("readability_score"),
                        "keyword_density": comp.get("keyword_density"),
                        "ai_analysis": ai_analysis,
                        "is_selected": is_winner if winner_tone else s["is_selected"],
                    })
                    # Reflect persisted state on the in-memory record so
                    # callers see ats_score / evidence_coverage / winner.
                    s["ats_score"] = comp.get("ats_score")
                    s["readability_score"] = comp.get("readability_score")
                    s["keyword_density"] = comp.get("keyword_density")
                    s["evidence_coverage"] = comp.get("evidence_coverage")
                    s["composite_score"] = comp.get("composite_score")
                    s["delta_vs_original"] = comp.get("delta_vs_original")
                    s["ai_analysis"] = ai_analysis
                    if winner_tone:
                        s["is_selected"] = is_winner

        logger.info("variants_generated", count=len(saved), doc_type=document_type)
        return {
            "variants": saved,
            "comparison": comparison,
        }

    async def get_variants(
        self, user_id: str, application_id: Optional[str] = None, document_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get variants for an application."""
        filters = [("user_id", "==", user_id)]
        if application_id:
            filters.append(("application_id", "==", application_id))
        if document_type:
            filters.append(("document_type", "==", document_type))
        return await self.db.query(
            TABLES["doc_variants"],
            filters=filters,
            order_by="created_at",
            order_direction="DESCENDING",
        )

    async def select_variant(self, variant_id: str, user_id: str) -> bool:
        """Select a variant as the chosen one."""
        variant = await self.db.get(TABLES["doc_variants"], variant_id)
        if not variant or variant.get("user_id") != user_id:
            return False

        # Deselect others of same type/application
        siblings = await self.db.query(
            TABLES["doc_variants"],
            filters=[
                ("user_id", "==", user_id),
                ("application_id", "==", variant.get("application_id")),
                ("document_type", "==", variant["document_type"]),
            ],
        )
        for s in siblings:
            if s["id"] != variant_id:
                await self.db.update(TABLES["doc_variants"], s["id"], {"is_selected": False})

        await self.db.update(TABLES["doc_variants"], variant_id, {"is_selected": True})
        return True
