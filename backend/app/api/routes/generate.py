"""
Unified AI Generation Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Single endpoint that orchestrates the full AI-powered application generation:
  1. Parse resume → structured user profile
  2. Build ideal candidate benchmark
  3. Analyze gaps (user vs benchmark)
  4. Generate strategically tailored CV (HTML)
  5. Generate tailored cover letter (HTML)
  6. Generate learning plan / roadmap
  7. Compute match scores
"""
import asyncio
import json
import traceback
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import structlog

logger = structlog.get_logger()

router = APIRouter()


# ── Request schema ────────────────────────────────────────────────────
class PipelineRequest(BaseModel):
    job_title: str
    company: str = ""
    jd_text: str
    resume_text: str = ""


# ── Main pipeline endpoint ────────────────────────────────────────────
@router.post("/pipeline")
async def generate_pipeline(req: PipelineRequest):
    """Run the complete AI generation pipeline and return all modules."""
    try:
        from ai_engine.client import AIClient
        from ai_engine.chains.role_profiler import RoleProfilerChain
        from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
        from ai_engine.chains.gap_analyzer import GapAnalyzerChain
        from ai_engine.chains.document_generator import DocumentGeneratorChain
        from ai_engine.chains.career_consultant import CareerConsultantChain
        from ai_engine.chains.validator import ValidatorChain

        ai = AIClient()
        company = req.company or "the company"

        logger.info(
            "pipeline.start",
            job_title=req.job_title,
            company=company,
            jd_length=len(req.jd_text),
            resume_length=len(req.resume_text),
        )

        # ── Phase 1: Parse resume + Build benchmark (parallel) ────────
        profiler = RoleProfilerChain(ai)
        benchmark_chain = BenchmarkBuilderChain(ai)

        if req.resume_text.strip():
            user_profile, benchmark_data = await asyncio.gather(
                profiler.parse_resume(req.resume_text),
                benchmark_chain.create_ideal_profile(
                    req.job_title, company, req.jd_text
                ),
            )
        else:
            user_profile = {}
            benchmark_data = await benchmark_chain.create_ideal_profile(
                req.job_title, company, req.jd_text
            )

        logger.info("pipeline.phase1_done", has_profile=bool(user_profile))

        # Extract keywords from benchmark ideal skills
        ideal_skills = benchmark_data.get("ideal_skills", [])
        keywords = [
            s.get("name", "")
            for s in ideal_skills
            if isinstance(s, dict) and s.get("name")
        ]
        if not keywords:
            keywords = _extract_keywords_from_jd(req.jd_text)

        # ── Phase 2: Gap Analysis ─────────────────────────────────────
        gap_chain = GapAnalyzerChain(ai)
        gap_analysis = await gap_chain.analyze_gaps(
            user_profile, benchmark_data, req.job_title, company
        )

        logger.info(
            "pipeline.phase2_done",
            compatibility=gap_analysis.get("compatibility_score", 0),
        )

        # ── Phase 3: Generate documents (parallel) ────────────────────
        doc_chain = DocumentGeneratorChain(ai)
        consultant = CareerConsultantChain(ai)

        # Prepare context strings for the prompts
        skill_gaps = gap_analysis.get("skill_gaps", [])
        strengths = gap_analysis.get("strengths", [])
        key_gaps_str = ", ".join(
            g.get("skill", "") for g in skill_gaps[:8] if isinstance(g, dict)
        ) or "None identified"
        strengths_str = ", ".join(
            s.get("area", "") for s in strengths[:8] if isinstance(s, dict)
        ) or "None identified"
        compatibility = gap_analysis.get("compatibility_score", 50)

        cv_html, cl_html, roadmap = await asyncio.gather(
            doc_chain.generate_tailored_cv(
                user_profile=user_profile,
                job_title=req.job_title,
                company=company,
                jd_text=req.jd_text,
                gap_analysis=gap_analysis,
                resume_text=req.resume_text,
            ),
            doc_chain.generate_tailored_cover_letter(
                user_profile=user_profile,
                job_title=req.job_title,
                company=company,
                jd_text=req.jd_text,
                gap_analysis=gap_analysis,
            ),
            consultant.generate_roadmap(
                gap_analysis, user_profile, req.job_title, company
            ),
        )

        logger.info(
            "pipeline.phase3_done",
            cv_length=len(cv_html) if isinstance(cv_html, str) else 0,
            cl_length=len(cl_html) if isinstance(cl_html, str) else 0,
        )

        # Handle exceptions from gather
        if isinstance(cv_html, Exception):
            logger.error("pipeline.cv_failed", error=str(cv_html))
            cv_html = ""
        if isinstance(cl_html, Exception):
            logger.error("pipeline.cl_failed", error=str(cl_html))
            cl_html = ""
        if isinstance(roadmap, Exception):
            logger.error("pipeline.roadmap_failed", error=str(roadmap))
            roadmap = {}

        # ── Phase 4: Personal statement + Portfolio (parallel) ────────
        ps_html = ""
        portfolio_html = ""
        try:
            ps_result, portfolio_result = await asyncio.gather(
                doc_chain.generate_tailored_personal_statement(
                    user_profile=user_profile,
                    job_title=req.job_title,
                    company=company,
                    jd_text=req.jd_text,
                    gap_analysis=gap_analysis,
                    resume_text=req.resume_text,
                ),
                doc_chain.generate_tailored_portfolio(
                    user_profile=user_profile,
                    job_title=req.job_title,
                    company=company,
                    jd_text=req.jd_text,
                    gap_analysis=gap_analysis,
                    resume_text=req.resume_text,
                ),
                return_exceptions=True,
            )

            if isinstance(ps_result, Exception):
                logger.error("pipeline.ps_failed", error=str(ps_result))
            else:
                ps_html = ps_result if isinstance(ps_result, str) else ""

            if isinstance(portfolio_result, Exception):
                logger.error("pipeline.portfolio_failed", error=str(portfolio_result))
            else:
                portfolio_html = portfolio_result if isinstance(portfolio_result, str) else ""
        except Exception as phase4_err:
            logger.error("pipeline.phase4_error", error=str(phase4_err))

        logger.info(
            "pipeline.phase4_done",
            ps_length=len(ps_html),
            portfolio_length=len(portfolio_html),
        )

        # ── Phase 5: Validate key documents (non-blocking) ───────────
        validation = {}
        try:
            validator = ValidatorChain(ai)
            cv_valid, cv_validation = await validator.validate_document(
                document_type="Tailored CV",
                content=cv_html[:3000] if cv_html else "",
                profile_data=user_profile,
            )
            validation["cv"] = {
                "valid": cv_valid,
                "qualityScore": cv_validation.get("quality_score", 0),
                "issues": len(cv_validation.get("issues", [])),
            }
            logger.info("pipeline.validation_done", cv_valid=cv_valid)
        except Exception as val_err:
            logger.warning("pipeline.validation_skipped", error=str(val_err))

        # ── Format response for frontend ──────────────────────────────
        response = _format_response(
            benchmark_data=benchmark_data,
            gap_analysis=gap_analysis,
            roadmap=roadmap if isinstance(roadmap, dict) else {},
            cv_html=cv_html if isinstance(cv_html, str) else "",
            cl_html=cl_html if isinstance(cl_html, str) else "",
            ps_html=ps_html,
            portfolio_html=portfolio_html,
            validation=validation,
            keywords=keywords,
            job_title=req.job_title,
        )

        logger.info("pipeline.complete", overall_score=response["scores"]["overall"])
        return response

    except Exception as e:
        logger.error(
            "pipeline.error",
            error=str(e),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"AI generation failed: {str(e)}",
        )


# ── Response formatters ───────────────────────────────────────────────

def _format_response(
    benchmark_data: Dict[str, Any],
    gap_analysis: Dict[str, Any],
    roadmap: Dict[str, Any],
    cv_html: str,
    cl_html: str,
    ps_html: str,
    portfolio_html: str,
    validation: Dict[str, Any],
    keywords: List[str],
    job_title: str,
) -> Dict[str, Any]:
    """Transform chain outputs into the frontend's expected data shapes."""

    # ── Benchmark ─────────────────────────────
    ideal_profile = benchmark_data.get("ideal_profile", {})
    ideal_skills = benchmark_data.get("ideal_skills", [])
    ideal_experience = benchmark_data.get("ideal_experience", [])

    summary_text = ""
    if isinstance(ideal_profile, dict):
        summary_text = ideal_profile.get("summary", "")
    if not summary_text:
        summary_text = f"AI-generated benchmark for {job_title}"

    rubric: List[str] = []
    for skill in ideal_skills[:10]:
        if isinstance(skill, dict):
            name = skill.get("name", "Unknown")
            level = skill.get("level", "required")
            importance = skill.get("importance", "important")
            rubric.append(f"{name} — {level} level ({importance})")

    benchmark = {
        "summary": summary_text,
        "keywords": keywords,
        "rubric": rubric,
        "idealProfile": ideal_profile if isinstance(ideal_profile, dict) else {},
        "idealSkills": ideal_skills,
        "idealExperience": ideal_experience,
        "scoringWeights": benchmark_data.get("scoring_weights", {}),
        "createdAt": None,
    }

    # ── Gaps ──────────────────────────────────
    compatibility = gap_analysis.get("compatibility_score", 50)
    skill_gaps = gap_analysis.get("skill_gaps", [])
    exp_gaps = gap_analysis.get("experience_gaps", [])
    strengths_raw = gap_analysis.get("strengths", [])
    recommendations_raw = gap_analysis.get("recommendations", [])
    category_scores = gap_analysis.get("category_scores", {})
    quick_wins = gap_analysis.get("quick_wins", [])

    missing_kw = [
        g.get("skill", "") for g in skill_gaps if isinstance(g, dict) and g.get("skill")
    ]
    strength_labels = [
        s.get("area", s.get("description", ""))
        for s in strengths_raw
        if isinstance(s, dict)
    ]
    rec_labels = [
        r.get("title", r.get("description", ""))
        for r in recommendations_raw
        if isinstance(r, dict)
    ]

    gaps = {
        "missingKeywords": missing_kw,
        "strengths": strength_labels,
        "recommendations": rec_labels,
        "gaps": [
            {
                "dimension": g.get("skill", ""),
                "gap": f"{g.get('current_level', '?')} → {g.get('required_level', 'required')}",
                "severity": _map_severity(g.get("gap_severity", "moderate")),
                "suggestion": g.get("recommendation", ""),
            }
            for g in skill_gaps
            if isinstance(g, dict)
        ],
        "summary": gap_analysis.get("executive_summary", ""),
        "compatibility": compatibility,
        "categoryScores": category_scores,
        "quickWins": quick_wins,
        "interviewReadiness": gap_analysis.get("interview_readiness", {}),
    }

    # ── Learning Plan ─────────────────────────
    roadmap_data = roadmap.get("roadmap", {}) if isinstance(roadmap, dict) else {}
    weekly_plans = roadmap_data.get("weekly_plans", [])
    skill_dev = roadmap_data.get("skill_development", [])
    lr_resources = roadmap.get("learning_resources", []) if isinstance(roadmap, dict) else []

    learning_plan = {
        "focus": [
            s.get("skill", "")
            for s in skill_dev[:6]
            if isinstance(s, dict) and s.get("skill")
        ],
        "plan": [
            {
                "week": wp.get("week", i + 1),
                "theme": wp.get("theme", f"Week {i + 1}"),
                "outcomes": wp.get("goals", []),
                "tasks": [
                    a.get("activity", "")
                    for a in wp.get("activities", [])
                    if isinstance(a, dict)
                ],
                "goals": wp.get("goals", []),
            }
            for i, wp in enumerate(weekly_plans[:12])
            if isinstance(wp, dict)
        ],
        "resources": [
            {
                "skill": r.get("skill_covered", r.get("skill", "")),
                "title": r.get("title", ""),
                "provider": r.get("provider", ""),
                "timebox": r.get("duration", "Self-paced"),
                "url": r.get("url"),
            }
            for r in lr_resources[:12]
            if isinstance(r, dict)
        ],
    }

    # ── Scores ────────────────────────────────
    match_score = min(100, max(0, compatibility))
    ats_score = min(100, match_score + 15)
    scan_score = min(100, match_score + 10)

    scores = {
        "match": match_score,
        "atsReadiness": ats_score,
        "recruiterScan": scan_score,
        "evidenceStrength": 0,
        "topFix": _derive_top_fix(missing_kw),
        "benchmark": match_score,
        "gaps": max(0, 100 - len(missing_kw) * 8),
        "cv": min(100, match_score + 20),
        "coverLetter": min(100, match_score + 15),
        "overall": match_score,
    }

    scorecard = {
        "overall": scores["overall"],
        "dimensions": [
            {"name": "Match", "score": scores["match"], "feedback": f"{scores['match']}% keyword alignment"},
            {"name": "ATS Readiness", "score": scores["atsReadiness"], "feedback": f"{scores['atsReadiness']}% ATS-optimized"},
            {"name": "Recruiter Scan", "score": scores["recruiterScan"], "feedback": f"{scores['recruiterScan']}% scan-friendly"},
            {"name": "Evidence Strength", "score": scores["evidenceStrength"], "feedback": "Add evidence to boost this score"},
        ],
        "match": scores["match"],
        "atsReadiness": scores["atsReadiness"],
        "recruiterScan": scores["recruiterScan"],
        "evidenceStrength": scores["evidenceStrength"],
        "topFix": scores["topFix"],
        "updatedAt": None,
    }

    return {
        "benchmark": benchmark,
        "gaps": gaps,
        "learningPlan": learning_plan,
        "cvHtml": cv_html,
        "coverLetterHtml": cl_html,
        "personalStatementHtml": ps_html,
        "portfolioHtml": portfolio_html,
        "validation": validation,
        "scorecard": scorecard,
        "scores": scores,
    }


# ── Helpers ───────────────────────────────────────────────────────────

def _map_severity(severity: str) -> str:
    return {"critical": "high", "major": "high", "moderate": "medium", "minor": "low"}.get(
        severity, "medium"
    )


def _derive_top_fix(missing: List[str]) -> str:
    if missing:
        return f'Add proof for "{missing[0]}" — include a concrete project or measurable result.'
    return "Your profile is strong! Polish your summary and lead with your best proof point."


def _extract_keywords_from_jd(jd_text: str) -> List[str]:
    """Simple keyword extraction fallback."""
    KNOWN = {
        "javascript", "typescript", "python", "java", "go", "rust", "ruby", "php",
        "swift", "kotlin", "react", "angular", "vue", "svelte", "next", "nuxt",
        "node", "express", "django", "flask", "fastapi", "spring",
        "sql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "git", "github", "gitlab", "jenkins", "ci", "cd",
        "graphql", "rest", "grpc", "microservices",
        "tailwind", "css", "html", "sass",
        "jest", "playwright", "cypress", "selenium",
        "figma", "agile", "scrum", "kanban",
        "machine", "learning", "ai", "ml", "nlp",
        "linux", "bash", "shell",
    }
    words = jd_text.lower().split()
    found, seen = [], set()
    for w in words:
        clean = w.strip(".,;:!?()[]{}\"'").lower()
        if clean in KNOWN and clean not in seen:
            seen.add(clean)
            found.append(clean)
    return found[:25]
