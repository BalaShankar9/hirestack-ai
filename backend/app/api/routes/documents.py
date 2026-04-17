"""Document Library API — endpoints for managing Benchmark, Fixed, and Tailored documents."""
import asyncio
import structlog
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, validate_uuid
from app.core.security import limiter

logger = structlog.get_logger()
router = APIRouter()


# ── Request/Response schemas ──────────────────────────────────────────

class GenerateDocumentRequest(BaseModel):
    doc_type: str = Field(..., min_length=1, max_length=100)
    doc_category: str = Field("tailored", pattern=r"^(benchmark|fixed|tailored)$")
    label: Optional[str] = None
    application_id: Optional[str] = None


class UpdateDocumentRequest(BaseModel):
    html_content: Optional[str] = None
    label: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/documents/library")
@limiter.limit("30/minute")
async def get_document_library(
    request: Request,
    application_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None, pattern=r"^(benchmark|fixed|tailored)$"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the user's document library, optionally filtered by application and category."""
    from app.core.database import get_supabase, TABLES
    from app.services.document_library import DocumentLibraryService

    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    sb = get_supabase()
    service = DocumentLibraryService(sb, TABLES)

    if category:
        docs = await service.get_documents_by_category(
            user_id, category, application_id=application_id
        )
        return {"documents": docs, "category": category}

    if application_id:
        validate_uuid(application_id, "application_id")
        docs = await service.get_application_documents(user_id, application_id)
        return {"documents": docs}

    # No filter — return fixed library + summary
    fixed = await service.get_documents_by_category(user_id, "fixed")
    return {"documents": {"fixed": fixed}, "category": "fixed"}


@router.get("/documents/library/summary")
@limiter.limit("30/minute")
async def get_library_summary(
    request: Request,
    application_id: str = Query(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a summary of document library state for an application."""
    validate_uuid(application_id, "application_id")
    from app.core.database import get_supabase, TABLES
    from app.services.document_library import DocumentLibraryService

    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    sb = get_supabase()
    service = DocumentLibraryService(sb, TABLES)
    summary = await service.get_library_summary(user_id, application_id)
    return {"summary": summary}


@router.get("/documents/library/all")
@limiter.limit("30/minute")
async def get_all_documents(
    request: Request,
    category: Optional[str] = Query(None, pattern=r"^(benchmark|fixed|tailored)$"),
    limit: int = Query(100, ge=1, le=500),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get ALL user documents across every application — for the global sidebar library."""
    from app.core.database import get_supabase, TABLES

    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    sb = get_supabase()

    def _query():
        q = sb.table(TABLES["document_library"]).select(
            "id, doc_type, doc_category, label, status, version, source, "
            "application_id, created_at, updated_at"
        ).eq("user_id", user_id).order("updated_at", desc=True).limit(limit)
        if category:
            q = q.eq("doc_category", category)
        return q.execute()

    import asyncio
    result = await asyncio.get_event_loop().run_in_executor(None, _query)
    return {"documents": result.data or []}


@router.get("/documents/library/{doc_id}")
@limiter.limit("30/minute")
async def get_document(
    request: Request,
    doc_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a single document from the library."""
    validate_uuid(doc_id, "doc_id")
    from app.core.database import get_supabase, TABLES
    from app.services.document_library import DocumentLibraryService

    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    sb = get_supabase()
    service = DocumentLibraryService(sb, TABLES)
    doc = await service.get_document(user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document": doc}


@router.post("/documents/library/generate")
@limiter.limit("10/minute")
async def generate_document(
    request: Request,
    req: GenerateDocumentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a single document on demand (user-initiated)."""
    from app.core.database import get_supabase, TABLES
    from app.services.document_library import DocumentLibraryService

    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    sb = get_supabase()
    service = DocumentLibraryService(sb, TABLES)

    if req.application_id:
        validate_uuid(req.application_id, "application_id")
        # Verify ownership
        app_resp = await asyncio.to_thread(
            lambda: sb.table(TABLES["applications"])
            .select("id")
            .eq("id", req.application_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not app_resp.data:
            raise HTTPException(status_code=404, detail="Application not found")

    # Create the document entry
    doc = await service.create_document(
        user_id=user_id,
        doc_type=req.doc_type,
        doc_category=req.doc_category,
        label=req.label or req.doc_type.replace("_", " ").title(),
        application_id=req.application_id,
        source="user_request",
        status="generating",
    )

    # Kick off async generation
    asyncio.create_task(
        _generate_document_async(
            user_id=user_id,
            doc_id=doc["id"],
            doc_type=req.doc_type,
            doc_category=req.doc_category,
            application_id=req.application_id,
        )
    )

    return {"document": doc, "status": "generating"}


@router.patch("/documents/library/{doc_id}")
@limiter.limit("20/minute")
async def update_document(
    request: Request,
    doc_id: str,
    req: UpdateDocumentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a document's content or label."""
    validate_uuid(doc_id, "doc_id")
    from app.core.database import get_supabase, TABLES
    from app.services.document_library import DocumentLibraryService

    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    sb = get_supabase()
    service = DocumentLibraryService(sb, TABLES)

    patch: Dict[str, Any] = {}
    if req.html_content is not None:
        patch["html_content"] = req.html_content
        patch["status"] = "ready"
    if req.label is not None:
        patch["label"] = req.label

    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await service.update_document(user_id, doc_id, patch)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document": result}


# ── Background generation helper ──────────────────────────────────────

async def _generate_document_async(
    user_id: str,
    doc_id: str,
    doc_type: str,
    doc_category: str,
    application_id: Optional[str],
) -> None:
    """Generate a document asynchronously using the adaptive document chain."""
    try:
        from app.core.database import get_supabase, TABLES
        from ai_engine.client import AIClient
        from ai_engine.chains.adaptive_document import AdaptiveDocumentChain
        from app.core.sanitize import sanitize_html
        from app.services.document_library import DocumentLibraryService

        sb = get_supabase()
        service = DocumentLibraryService(sb, TABLES)
        ai = AIClient()
        chain = AdaptiveDocumentChain(ai)

        # Build context from application if available
        context: Dict[str, Any] = {}
        if application_id:
            app_resp = await asyncio.to_thread(
                lambda: sb.table(TABLES["applications"])
                .select("confirmed_facts,benchmark,gaps,company_intel")
                .eq("id", application_id)
                .maybe_single()
                .execute()
            )
            if app_resp.data:
                app = app_resp.data
                facts = app.get("confirmed_facts") or {}
                benchmark = app.get("benchmark") or {}
                gaps = app.get("gaps") or {}
                intel = app.get("company_intel") or {}

                context = {
                    "job_title": facts.get("jobTitle", ""),
                    "company": facts.get("company", ""),
                    "profile": {},
                    "jd_text": facts.get("jdText", ""),
                    "industry": intel.get("industry", ""),
                    "tone": "professional",
                    "key_themes": [],
                    "gaps_summary": ", ".join(
                        g.get("skill", "") for g in (gaps.get("skill_gaps") or [])[:8]
                        if isinstance(g, dict)
                    ) or "None identified",
                    "strengths_summary": ", ".join(
                        s.get("area", "") for s in (gaps.get("strengths") or [])[:8]
                        if isinstance(s, dict)
                    ) or "None identified",
                    "benchmark_keywords": ", ".join(
                        s.get("name", "") for s in (benchmark.get("ideal_skills") or [])[:15]
                        if isinstance(s, dict)
                    ),
                    "company_intel": str(intel)[:1000] if intel else "",
                }

        mode = "benchmark" if doc_category == "benchmark" else "user"
        html = await chain.generate(
            doc_type=doc_type,
            doc_label=doc_type.replace("_", " ").title(),
            context=context,
            mode=mode,
        )

        if html and html.strip():
            safe_html = sanitize_html(html)
            await service.update_document_content(user_id, doc_id, safe_html)
        else:
            await service.mark_error(user_id, doc_id, "AI returned empty content")

    except Exception as e:
        logger.error("document_generate_async_failed", doc_id=doc_id, error=str(e)[:300])
        try:
            from app.core.database import get_supabase, TABLES
            from app.services.document_library import DocumentLibraryService
            sb = get_supabase()
            service = DocumentLibraryService(sb, TABLES)
            await service.mark_error(user_id, doc_id, str(e)[:500])
        except Exception as mark_err:
            logger.error("document_mark_error_failed", doc_id=doc_id, error=str(mark_err)[:200])
