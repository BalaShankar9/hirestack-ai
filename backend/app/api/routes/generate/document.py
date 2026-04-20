"""On-demand single document generation endpoint (POST /document)."""
import asyncio
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user, check_billing_limit
from app.core.security import limiter

from .schemas import GenerateDocumentRequest
from .helpers import _sanitize_output_html, logger
from .jobs import _persist_application_patch

router = APIRouter()


@router.post("/document")
@limiter.limit("5/minute")
async def generate_on_demand_document(
    request: Request,
    req: GenerateDocumentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a single optional document for an existing application."""
    from app.api.deps import check_usage_guard
    await check_usage_guard(current_user)
    await check_billing_limit("ai_calls", current_user)
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    from app.core.database import get_supabase, TABLES
    from ai_engine.client import AIClient
    from ai_engine.chains.adaptive_document import AdaptiveDocumentChain

    sb = get_supabase()

    # Fetch application with ownership check
    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("*")
        .eq("id", req.application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    app_data = app_resp.data
    confirmed_facts = app_data.get("confirmed_facts") or {}

    job_title = confirmed_facts.get("jobTitle") or confirmed_facts.get("job_title") or ""
    company = confirmed_facts.get("company") or ""
    jd_text = confirmed_facts.get("jdText") or confirmed_facts.get("jd_text") or ""
    _resume_data = confirmed_facts.get("resume") or {}
    user_profile = app_data.get("user_profile") or {}

    if not job_title:
        raise HTTPException(status_code=400, detail="Application is missing job title")

    # Build context for AdaptiveDocumentChain
    gap_analysis = app_data.get("gap_analysis") or {}
    benchmark_data = app_data.get("benchmark") or {}
    company_intel = app_data.get("company_intel") or {}

    gaps_summary = ""
    skill_gaps = gap_analysis.get("skill_gaps") or gap_analysis.get("skillGaps") or []
    if skill_gaps:
        gaps_summary = "; ".join(
            g.get("skill", "") for g in skill_gaps[:10] if isinstance(g, dict) and g.get("skill")
        )

    strengths = gap_analysis.get("strengths") or gap_analysis.get("key_strengths") or []
    strengths_summary = ""
    if strengths:
        strengths_summary = "; ".join(
            (s.get("skill", "") if isinstance(s, dict) else str(s)) for s in strengths[:10]
        )

    ideal_skills = benchmark_data.get("ideal_skills") or []
    benchmark_keywords = ", ".join(
        s.get("name", "") for s in ideal_skills[:15] if isinstance(s, dict)
    )

    doc_pack_plan = app_data.get("doc_pack_plan") or {}
    doc_label = req.doc_label or req.doc_key.replace("_", " ").title()

    # Fetch evidence items for this application/user
    evidence_summary = ""
    try:
        ev_resp = await asyncio.to_thread(
            lambda: sb.table(TABLES.get("evidence", "evidence"))
            .select("title, type, description, skills")
            .eq("user_id", user_id)
            .limit(15)
            .execute()
        )
        ev_items = ev_resp.data or []
        if ev_items:
            evidence_summary = "\n".join(
                f"- {e.get('title', '')} ({e.get('type', '')}): {(e.get('description') or '')[:120]}"
                + (f" | Skills: {', '.join(e['skills'])}" if e.get('skills') else "")
                for e in ev_items
            )
    except Exception:
        pass  # Evidence is optional enrichment

    # Fetch latest ATS scan feedback for this application
    ats_feedback = ""
    try:
        ats_resp = await asyncio.to_thread(
            lambda: sb.table(TABLES.get("ats_scans", "ats_scans"))
            .select("ats_score, missing_keywords, recommendations")
            .eq("user_id", user_id)
            .eq("application_id", req.application_id)
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if ats_resp.data:
            scan = ats_resp.data
            missing = scan.get("missing_keywords") or []
            recs = scan.get("recommendations") or []
            parts = []
            if missing:
                parts.append(f"Missing keywords: {', '.join(str(k) for k in missing[:10])}")
            if recs:
                parts.append(f"Suggestions: {'; '.join(str(r) for r in recs[:5])}")
            if parts:
                ats_feedback = " | ".join(parts)
    except Exception:
        pass  # ATS feedback is optional enrichment

    context = {
        "profile": user_profile,
        "job_title": job_title,
        "company": company or "the company",
        "industry": doc_pack_plan.get("industry", "professional"),
        "tone": doc_pack_plan.get("tone", "professional"),
        "jd_text": jd_text,
        "gaps_summary": gaps_summary,
        "strengths_summary": strengths_summary,
        "benchmark_keywords": benchmark_keywords,
        "company_intel": company_intel,
        "key_themes": doc_pack_plan.get("key_themes", []),
        "evidence_context": evidence_summary,
        "ats_feedback": ats_feedback,
    }

    ai = AIClient()
    chain = AdaptiveDocumentChain(ai)

    try:
        html = await chain.generate(
            doc_type=req.doc_key,
            doc_label=doc_label,
            context=context,
            mode="user",
        )
    except Exception as gen_err:
        logger.error("on_demand_doc.generation_failed", doc_key=req.doc_key, error=str(gen_err)[:200])
        raise HTTPException(status_code=500, detail="Document generation failed")

    html = _sanitize_output_html(html) if html else ""

    # Persist to application's generated_documents
    existing_docs = app_data.get("generated_documents") or {}
    existing_docs[req.doc_key] = html
    try:
        await _persist_application_patch(
            sb, TABLES, req.application_id,
            {"generated_documents": existing_docs},
        )
    except Exception as persist_err:
        logger.warning("on_demand_doc.persist_failed", error=str(persist_err)[:200])

    return {"doc_key": req.doc_key, "doc_label": doc_label, "html": html}


# ── Stale job cleanup ─────────────────────────────────────────────────

