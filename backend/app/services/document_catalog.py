"""
Document Catalog Service — manages the platform-wide document type catalog.

The catalog is append-only: every document type encountered in any job description
is retained forever. The catalog grows as the platform processes more JDs.

Usage:
    from app.services.document_catalog import get_full_catalog, observe_document_types
    catalog = await get_full_catalog(db, tables)
    await observe_document_types(db, tables, discovered_docs, user_id, ...)
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ai_engine.chains.document_pack_planner import DocumentPackPlan

logger = structlog.get_logger("hirestack.document_catalog")


# ═══════════════════════════════════════════════════════════════════════
#  Seed catalog — built from AdaptiveDocumentChain's DOCUMENT_TYPE_PROMPTS
# ═══════════════════════════════════════════════════════════════════════

SEED_CATALOG: Tuple[Dict[str, Any], ...] = (
    # Core (always generated)
    {"key": "cv", "label": "Tailored CV", "description": "Your resume tailored and optimized for the specific job description", "category": "core", "generatable": True},
    {"key": "cover_letter", "label": "Cover Letter", "description": "Compelling narrative connecting your experience to the role", "category": "core", "generatable": True},
    {"key": "personal_statement", "label": "Personal Statement", "description": "Authentic career narrative revealing the person behind the resume", "category": "core", "generatable": True},
    {"key": "portfolio", "label": "Portfolio & Evidence", "description": "Showcase of projects presented as mini case studies with impact", "category": "core", "generatable": True},

    # Professional
    {"key": "executive_summary", "label": "Executive Summary", "description": "Concise one-page overview of qualifications and value proposition", "category": "executive", "generatable": True},
    {"key": "elevator_pitch", "label": "Elevator Pitch", "description": "Brief compelling pitch for networking and quick introductions", "category": "professional", "generatable": True},
    {"key": "references_list", "label": "References List", "description": "Formatted professional references with contact details", "category": "professional", "generatable": True},
    {"key": "motivation_letter", "label": "Motivation Letter", "description": "Deeper exploration of career motivation and role alignment", "category": "professional", "generatable": True},
    {"key": "recommendation_letter_template", "label": "Recommendation Letter Template", "description": "Draft template for recommenders to customize", "category": "professional", "generatable": True},
    {"key": "ninety_day_plan", "label": "90-Day Plan", "description": "Strategic onboarding plan showing immediate value delivery", "category": "executive", "generatable": True},
    {"key": "values_statement", "label": "Values Statement", "description": "Articulation of professional values and ethical framework", "category": "professional", "generatable": True},
    {"key": "leadership_philosophy", "label": "Leadership Philosophy", "description": "Framework describing leadership style and management approach", "category": "executive", "generatable": True},
    {"key": "professional_development_plan", "label": "Professional Development Plan", "description": "Structured plan for ongoing skill development and career growth", "category": "professional", "generatable": True},

    # Academic
    {"key": "research_statement", "label": "Research Statement", "description": "Overview of research interests, methodology, and future directions", "category": "academic", "generatable": True},
    {"key": "teaching_philosophy", "label": "Teaching Philosophy", "description": "Statement of teaching approach, methods, and educational values", "category": "academic", "generatable": True},
    {"key": "publications_list", "label": "Publications List", "description": "Formatted list of academic publications and citations", "category": "academic", "generatable": True},
    {"key": "thesis_abstract", "label": "Thesis Abstract", "description": "Concise summary of thesis research for non-specialist audiences", "category": "academic", "generatable": True},
    {"key": "grant_proposal", "label": "Grant Proposal", "description": "Structured proposal for research funding applications", "category": "academic", "generatable": True},

    # Compliance / Government
    {"key": "selection_criteria", "label": "Selection Criteria Response", "description": "Structured STAR-format response to government selection criteria", "category": "compliance", "generatable": True},
    {"key": "diversity_statement", "label": "Diversity Statement", "description": "Commitment to diversity, equity, and inclusion in professional practice", "category": "compliance", "generatable": True},
    {"key": "safety_statement", "label": "Safety Statement", "description": "Professional approach to workplace safety and compliance", "category": "compliance", "generatable": True},
    {"key": "equity_statement", "label": "Equity Statement", "description": "Framework for advancing equity in professional context", "category": "compliance", "generatable": True},
    {"key": "conflict_of_interest_declaration", "label": "Conflict of Interest Declaration", "description": "Transparent disclosure of potential conflicts", "category": "compliance", "generatable": True},
    {"key": "community_engagement_statement", "label": "Community Engagement Statement", "description": "Description of community involvement and outreach activities", "category": "compliance", "generatable": True},

    # Technical
    {"key": "technical_assessment", "label": "Technical Assessment", "description": "Demonstration of technical knowledge relevant to the role", "category": "technical", "generatable": True},
    {"key": "code_samples", "label": "Code Samples", "description": "Curated examples of code quality and problem-solving approach", "category": "technical", "generatable": True},
    {"key": "writing_sample", "label": "Writing Sample", "description": "Example of professional writing demonstrating communication skills", "category": "technical", "generatable": True},
    {"key": "case_study", "label": "Case Study", "description": "Detailed analysis of a professional project or business problem solved", "category": "technical", "generatable": True},

    # Creative / Portfolio
    {"key": "design_portfolio", "label": "Design Portfolio", "description": "Visual showcase of design work with process documentation", "category": "creative", "generatable": True},
    {"key": "clinical_portfolio", "label": "Clinical Portfolio", "description": "Documentation of clinical experience and patient care competencies", "category": "creative", "generatable": True},
    {"key": "speaker_bio", "label": "Speaker Bio", "description": "Professional biography for speaking engagements and conferences", "category": "creative", "generatable": True},
    {"key": "media_kit", "label": "Media Kit", "description": "Press-ready materials including bio, photos, and key achievements", "category": "creative", "generatable": True},
    {"key": "consulting_deck", "label": "Consulting Deck", "description": "Presentation-style overview of expertise and methodology", "category": "executive", "generatable": True},
    {"key": "board_presentation", "label": "Board Presentation", "description": "Executive-level presentation of qualifications for board roles", "category": "executive", "generatable": True},
)

# Quick lookups (immutable, built once)
SEED_KEYS: frozenset[str] = frozenset(entry["key"] for entry in SEED_CATALOG)
SEED_BY_KEY: Dict[str, Dict[str, Any]] = {entry["key"]: entry for entry in SEED_CATALOG}
CORE_DOC_KEYS: frozenset[str] = frozenset(
    entry["key"] for entry in SEED_CATALOG if entry["category"] == "core"
)


# ═══════════════════════════════════════════════════════════════════════
#  Catalog operations
# ═══════════════════════════════════════════════════════════════════════

async def ensure_catalog_seeded(db: Any, tables: Dict[str, str]) -> None:
    """Idempotent: insert seed catalog entries if they don't exist."""
    table = tables.get("document_type_catalog", "document_type_catalog")
    try:
        rows = [
            {
                "key": e["key"],
                "label": e["label"],
                "description": e["description"],
                "category": e["category"],
                "generatable": e["generatable"],
                "seen_count": 0,
                "source_context": "",
            }
            for e in SEED_CATALOG
        ]
        await asyncio.to_thread(
            lambda: db.table(table).upsert(rows, on_conflict="key").execute()
        )
        logger.info("document_catalog.seeded", count=len(rows))
    except Exception as e:
        logger.warning("document_catalog.seed_failed", error=str(e)[:200])


async def get_full_catalog(db: Any, tables: Dict[str, str]) -> List[Dict[str, Any]]:
    """Return all catalog entries ordered by seen_count DESC, key ASC."""
    table = tables.get("document_type_catalog", "document_type_catalog")
    try:
        resp = await asyncio.to_thread(
            lambda: db.table(table)
            .select("*")
            .order("seen_count", desc=True)
            .order("key")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.warning("document_catalog.fetch_failed", error=str(e)[:200])
        # Fallback to seed catalog shape so callers always get a usable list
        return [
            {**entry, "id": None, "seen_count": 0, "source_context": ""}
            for entry in SEED_CATALOG
        ]


async def get_catalog_keyset(db: Any, tables: Dict[str, str]) -> Set[str]:
    """Return the set of known document keys (cheap, single column)."""
    table = tables.get("document_type_catalog", "document_type_catalog")
    try:
        resp = await asyncio.to_thread(
            lambda: db.table(table).select("key").execute()
        )
        return {row["key"] for row in (resp.data or []) if row.get("key")}
    except Exception:
        return set(SEED_KEYS)


async def get_catalog_id_map(db: Any, tables: Dict[str, str]) -> Dict[str, str]:
    """Return {key: id} mapping for observation FK lookups."""
    table = tables.get("document_type_catalog", "document_type_catalog")
    try:
        resp = await asyncio.to_thread(
            lambda: db.table(table).select("id, key").execute()
        )
        return {row["key"]: row["id"] for row in (resp.data or []) if row.get("key")}
    except Exception:
        return {}


async def observe_document_types(
    db: Any,
    tables: Dict[str, str],
    discovered_docs: List[Dict[str, Any]],
    user_id: str,
    application_id: Optional[str] = None,
    job_title: str = "",
    industry: str = "",
    job_level: str = "",
) -> None:
    """
    Record that certain document types were discovered in a job description.

    For known catalog entries: atomically increment seen_count via RPC + add observation.
    For unknown types: create new catalog entry (generatable=False if unknown) + observation.
    Batches observation inserts for efficiency.
    """
    if not discovered_docs:
        return

    catalog_table = tables.get("document_type_catalog", "document_type_catalog")
    obs_table = tables.get("document_observations", "document_observations")

    # Single roundtrip: fetch key→id map
    id_map = await get_catalog_id_map(db, tables)
    existing_keys = set(id_map.keys())

    # Collect new entries to insert and observations to batch
    new_entries: List[Dict[str, Any]] = []
    keys_to_increment: List[str] = []
    pending_observations: List[Dict[str, Any]] = []

    for doc in discovered_docs:
        doc_key = doc.get("key", "").strip()
        if not doc_key:
            continue

        doc_label = doc.get("label", doc_key.replace("_", " ").title())
        doc_reason = doc.get("reason", "")

        if doc_key in existing_keys:
            keys_to_increment.append(doc_key)
        else:
            # New document type — append to catalog
            source_parts = []
            if job_level:
                source_parts.append(job_level)
            if industry:
                source_parts.append(industry)
            source_ctx = f"First seen in a {' '.join(source_parts)} role" if source_parts else "Discovered from job application"
            if job_title:
                source_ctx += f" ({job_title})"

            new_entries.append({
                "key": doc_key,
                "label": doc_label,
                "description": doc_reason or "Document type discovered from job applications",
                "category": _infer_category(doc_key),
                "generatable": doc_key in SEED_KEYS,
                "seen_count": 1,
                "source_context": source_ctx,
            })
            existing_keys.add(doc_key)

        # Prepare observation row (catalog_entry_id filled after inserts)
        pending_observations.append({
            "_doc_key": doc_key,  # temporary, resolved below
            "user_id": user_id,
            "job_title": (job_title or "")[:200],
            "industry": (industry or "")[:100],
            "job_level": (job_level or "")[:50],
            "reason": (doc_reason or "")[:500],
            **({"application_id": application_id} if application_id else {}),
        })

    # ── Batch insert new catalog entries ──────────────────────────────
    if new_entries:
        try:
            await asyncio.to_thread(
                lambda: db.table(catalog_table)
                .upsert(new_entries, on_conflict="key")
                .execute()
            )
            logger.info("document_catalog.new_types_added",
                        keys=[e["key"] for e in new_entries])
        except Exception as e:
            logger.warning("document_catalog.insert_new_failed", error=str(e)[:200])

    # ── Atomic batch increment seen_count via RPC for existing keys ──
    if keys_to_increment:
        try:
            await asyncio.to_thread(
                lambda: db.rpc(
                    "increment_catalog_seen_count_batch",
                    {"p_keys": keys_to_increment},
                ).execute()
            )
        except Exception as e:
            # Fall back to per-key increment if batch RPC not deployed yet
            logger.debug("document_catalog.batch_increment_unavailable", error=str(e)[:120])
            for key in keys_to_increment:
                try:
                    await asyncio.to_thread(
                        lambda k=key: db.rpc(
                            "increment_catalog_seen_count", {"p_key": k}
                        ).execute()
                    )
                except Exception as e2:
                    logger.warning("document_catalog.increment_failed", key=key, error=str(e2)[:200])

    # ── Refresh id_map to include newly-inserted entries ──────────────
    if new_entries:
        id_map = await get_catalog_id_map(db, tables)

    # ── Batch insert observation rows ─────────────────────────────────
    obs_rows = []
    for obs in pending_observations:
        doc_key = obs.pop("_doc_key")
        catalog_entry_id = id_map.get(doc_key)
        if not catalog_entry_id:
            continue
        obs["catalog_entry_id"] = catalog_entry_id
        obs_rows.append(obs)

    if obs_rows:
        try:
            await asyncio.to_thread(
                lambda: db.table(obs_table).insert(obs_rows).execute()
            )
            logger.info("document_catalog.observations_recorded", count=len(obs_rows))
        except Exception as e:
            logger.warning("document_catalog.observations_failed", error=str(e)[:200])


def _infer_category(doc_key: str) -> str:
    """Best-effort category classification for unknown document types."""
    key = doc_key.lower()
    if any(t in key for t in ("research", "teaching", "thesis", "publications", "grant", "academic")):
        return "academic"
    if any(t in key for t in ("selection_criteria", "diversity", "equity", "safety", "compliance", "conflict")):
        return "compliance"
    if any(t in key for t in ("code", "technical", "assessment", "writing_sample", "case_study")):
        return "technical"
    if any(t in key for t in ("portfolio", "design", "clinical", "speaker", "media", "creative")):
        return "creative"
    if any(t in key for t in ("executive", "board", "leadership", "consulting", "ninety_day")):
        return "executive"
    return "professional"


# ═══════════════════════════════════════════════════════════════════════
#  High-level helper — single call for all execution paths
# ═══════════════════════════════════════════════════════════════════════


async def discover_and_observe(
    db: Any,
    tables: Dict[str, str],
    ai_client: Any,
    jd_text: str,
    job_title: str = "",
    company: str = "",
    user_profile: Optional[Dict[str, Any]] = None,
    user_id: str = "",
    application_id: Optional[str] = None,
    company_intel: Optional[Dict[str, Any]] = None,
    phase_timeout: float = 60.0,
) -> Optional["DocumentPackPlan"]:
    """
    Seed catalog → plan optimal doc pack → record observations.

    This is the single entry point that all execution paths (PipelineRuntime,
    _run_sync_pipeline, _stream_agent_pipeline, _run_generation_job_inner)
    should call to ensure consistent catalog learning.

    Returns the DocumentPackPlan on success, or None on failure.
    """
    from ai_engine.chains.document_pack_planner import DocumentPackPlanner

    try:
        await ensure_catalog_seeded(db, tables)
        catalog = await get_full_catalog(db, tables)

        planner = DocumentPackPlanner(ai_client=ai_client, catalog=catalog)
        doc_pack_plan: DocumentPackPlan = await asyncio.wait_for(
            planner.plan(
                jd_text=jd_text,
                job_title=job_title,
                company=company,
                user_profile=user_profile,
                company_intel=company_intel,
            ),
            timeout=phase_timeout,
        )

        # Collect all discovered doc types for observation
        all_discovered = (
            doc_pack_plan.core
            + doc_pack_plan.required
            + doc_pack_plan.optional
            + doc_pack_plan.new_candidates
        )

        await observe_document_types(
            db=db,
            tables=tables,
            discovered_docs=all_discovered,
            user_id=user_id,
            application_id=application_id,
            job_title=job_title,
            industry=doc_pack_plan.industry,
            job_level=doc_pack_plan.job_level,
        )

        logger.info(
            "document_catalog.discover_and_observe_done",
            core=len(doc_pack_plan.core),
            required=len(doc_pack_plan.required),
            optional=len(doc_pack_plan.optional),
            new_candidates=len(doc_pack_plan.new_candidates),
        )
        return doc_pack_plan
    except Exception as exc:
        logger.warning("document_catalog.discover_and_observe_failed", error=str(exc)[:200])
        return None
