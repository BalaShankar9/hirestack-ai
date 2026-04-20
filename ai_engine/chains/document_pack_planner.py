"""
Document Pack Planner — catalog-driven AI planner that selects
the optimal set of documents for each job description.

Unlike DocumentDiscoveryChain (which discovers from scratch every time),
this selects from the live platform catalog and classifies into
core / required / optional / deferred buckets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("hirestack.document_pack_planner")

# ═══════════════════════════════════════════════════════════════════════
#  Plan dataclass
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class DocumentPackPlan:
    """The output of the planner — a prioritized document selection for a specific JD."""

    # Always generated (cv, resume, cover_letter, personal_statement, portfolio)
    core: List[Dict[str, Any]] = field(default_factory=list)

    # JD-driven must-haves beyond core (auto-generated as benchmark + tailored)
    required: List[Dict[str, Any]] = field(default_factory=list)

    # Nice-to-have docs, generated only on user request
    optional: List[Dict[str, Any]] = field(default_factory=list)

    # In catalog but not relevant for this JD
    deferred: List[Dict[str, Any]] = field(default_factory=list)

    # JD mentions doc types that don't exist in catalog yet
    new_candidates: List[Dict[str, Any]] = field(default_factory=list)

    # Per-doc-key explanation of why it's in the plan
    reasons: Dict[str, str] = field(default_factory=dict)

    # Strategy metadata
    strategy: str = ""
    industry: str = ""
    job_level: str = ""
    tone: str = "professional"
    key_themes: List[str] = field(default_factory=list)
    confidence: float = 0.8

    def all_required_keys(self) -> List[str]:
        """Keys that should be auto-generated (core + required)."""
        return [d["key"] for d in self.core] + [d["key"] for d in self.required]

    def all_optional_keys(self) -> List[str]:
        """Keys available on-demand only."""
        return [d["key"] for d in self.optional]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "core": self.core,
            "required": self.required,
            "optional": self.optional,
            "deferred_count": len(self.deferred),
            "new_candidates": self.new_candidates,
            "reasons": self.reasons,
            "strategy": self.strategy,
            "industry": self.industry,
            "job_level": self.job_level,
            "tone": self.tone,
            "key_themes": self.key_themes,
            "confidence": self.confidence,
        }


# ═══════════════════════════════════════════════════════════════════════
#  Planner prompt
# ═══════════════════════════════════════════════════════════════════════

PLANNER_SYSTEM = """You are a senior career strategist who has reviewed 50,000+ job applications across every industry.
Given a job description and a catalog of available document types, you select the OPTIMAL document pack.

Rules:
1. Core documents (cv, resume, cover_letter, personal_statement, portfolio, elevator_pitch, linkedin_summary, follow_up_email, thank_you_note, references_list) are ALWAYS included — do not list them.
2. From the catalog, pick documents that the JD explicitly or implicitly requires → "required" list.
3. From the catalog, pick documents that would STRENGTHEN the application but aren't required → "optional" list.
4. If the JD mentions documents not in the catalog, add them to "new_candidates".
5. Every selection must include a concise "reason" explaining WHY for this specific job.
6. Be selective — more required docs = more AI cost. Only add what genuinely helps.
7. For government/public sector: selection_criteria and capability_statement are almost always required.
8. For academic: research_statement, teaching_philosophy usually required.
9. For executive/senior roles: executive_summary often required.
10. For ANY role where the JD mentions "lead", "own", "drive", "build", "manage", "grow", "responsible for", or "head of": include thirty_sixty_ninety_day_plan in required. Mid-level roles with these signals benefit enormously from a 30-60-90 plan as a differentiator. Note: this rule intentionally over-includes to maximize candidate differentiation — even IC roles with ownership language benefit from this document.
11. For consulting/freelance/contract roles: project_proposal is required.
12. For all roles: interview_prep_guide is optional but always beneficial — surface it.
13. For developer advocate, academic, or conference-speaker roles: speaking_proposal is required.

Return ONLY valid JSON."""

PLANNER_PROMPT = """Analyze this job description and select the optimal document pack from our catalog.

JOB TITLE: {job_title}
COMPANY: {company}

JOB DESCRIPTION:
{jd_text}

AVAILABLE DOCUMENT CATALOG (key | label | category | seen_count):
{catalog_text}

USER PROFILE SUMMARY:
{profile_summary}
{company_intel_section}
Return JSON:
{{
  "required": [
    {{"key": "catalog_key", "label": "Document Name", "reason": "Why this is required for this specific job"}}
  ],
  "optional": [
    {{"key": "catalog_key", "label": "Document Name", "reason": "Why this would strengthen the application"}}
  ],
  "new_candidates": [
    {{"key": "proposed_snake_case_key", "label": "Document Name", "reason": "JD mentions this but it's not in our catalog"}}
  ],
  "industry": "technology|finance|healthcare|academic|government|creative|consulting|legal|other",
  "job_level": "junior|mid|senior|executive|academic",
  "strategy": "2-3 sentence strategy for how documents should work together for this role",
  "tone": "formal|professional|conversational|academic|creative",
  "key_themes": ["3-5 themes that should run through all documents"],
  "confidence": 0.85
}}

IMPORTANT:
- Do NOT include core docs (cv, resume, cover_letter, personal_statement, portfolio) — they are always generated.
- Select ONLY from catalog keys listed above for required/optional.
- Only use new_candidates for docs the JD explicitly requests that aren't in the catalog.
- Be cost-conscious: each required doc uses AI credits."""


# ═══════════════════════════════════════════════════════════════════════
#  Core doc fallback (always present)
# ═══════════════════════════════════════════════════════════════════════

CORE_DOCS = [
    {"key": "cv", "label": "Tailored CV", "priority": "critical"},
    {"key": "resume", "label": "Tailored Résumé", "priority": "critical"},
    {"key": "cover_letter", "label": "Cover Letter", "priority": "critical"},
    {"key": "personal_statement", "label": "Personal Statement", "priority": "high"},
    {"key": "portfolio", "label": "Portfolio & Evidence", "priority": "high"},
    # Extended core — always generated for every application (H2-1)
    {"key": "elevator_pitch", "label": "Elevator Pitch", "priority": "high"},
    {"key": "linkedin_summary", "label": "LinkedIn Summary", "priority": "high"},
    {"key": "follow_up_email", "label": "Follow-Up Email", "priority": "medium"},
    {"key": "thank_you_note", "label": "Interview Thank-You Note", "priority": "medium"},
    {"key": "references_list", "label": "References List", "priority": "medium"},
]


# ═══════════════════════════════════════════════════════════════════════
#  Planner class
# ═══════════════════════════════════════════════════════════════════════

class DocumentPackPlanner:
    """
    AI-driven document pack planner.

    Takes the live catalog as selection space and produces a DocumentPackPlan
    for a specific JD.
    """

    VERSION = "1.0.0"

    def __init__(self, ai_client: Any, catalog: List[Dict[str, Any]]) -> None:
        self._ai = ai_client
        self._catalog = catalog
        self._catalog_keys = {row["key"] for row in catalog if row.get("key")}

    async def plan(
        self,
        jd_text: str,
        job_title: str = "",
        company: str = "",
        user_profile: Optional[Dict[str, Any]] = None,
        company_intel: Optional[Dict[str, Any]] = None,
    ) -> DocumentPackPlan:
        """Analyze a JD and produce the optimal document pack plan."""
        # Build catalog text for the prompt (skip core docs — they're always included)
        core_keys = {"cv", "resume", "cover_letter", "personal_statement", "portfolio"}
        catalog_lines = []
        for row in self._catalog:
            if row.get("key") in core_keys:
                continue
            catalog_lines.append(
                f"{row.get('key', '?')} | {row.get('label', '?')} | "
                f"{row.get('category', '?')} | seen {row.get('seen_count', 0)}x"
            )
        catalog_text = "\n".join(catalog_lines) if catalog_lines else "(no extra documents in catalog)"

        # Build profile summary
        profile_summary = "No resume provided"
        if user_profile:
            parts = []
            if user_profile.get("name"):
                parts.append(f"Name: {user_profile['name']}")
            if user_profile.get("experience_years"):
                parts.append(f"Experience: {user_profile['experience_years']} years")
            if user_profile.get("skills"):
                skills = user_profile["skills"]
                if isinstance(skills, list):
                    parts.append(f"Skills: {', '.join(str(s) for s in skills[:10])}")
            if user_profile.get("education"):
                edu = user_profile["education"]
                if isinstance(edu, list) and edu:
                    latest = edu[0] if isinstance(edu[0], dict) else {}
                    parts.append(f"Education: {latest.get('degree', '')} {latest.get('institution', '')}")
            profile_summary = " | ".join(parts) if parts else "Resume provided but minimal data extracted"

        # Build company intel summary for the prompt — use digest if available (H1-2 / H3-3)
        company_intel_section = ""
        if company_intel:
            digest = company_intel.get("application_strategy_digest", "")
            if digest:
                # Use the pre-generated 150-word digest — saves ~4,000 tokens vs full JSON
                company_intel_section = f"\nAPPLICATION STRATEGY DIGEST:\n{digest}\n"
            else:
                # Fallback: build a brief summary from structured fields
                intel_parts = []
                hiring = company_intel.get("hiring_intelligence", {})
                if hiring.get("must_have_skills"):
                    intel_parts.append(f"Must-have skills: {', '.join(str(s) for s in hiring['must_have_skills'][:10])}")
                culture = company_intel.get("culture_and_values", {})
                if culture.get("core_values"):
                    intel_parts.append(f"Core values: {', '.join(str(v) for v in culture['core_values'][:6])}")
                strategy = company_intel.get("application_strategy", {})
                if strategy.get("keywords_to_use"):
                    intel_parts.append(f"Keywords to target: {', '.join(str(k) for k in strategy['keywords_to_use'][:8])}")
                tech = company_intel.get("tech_and_engineering", {})
                if tech.get("tech_stack"):
                    intel_parts.append(f"Tech stack: {', '.join(str(t) for t in tech['tech_stack'][:8])}")
                confidence = company_intel.get("confidence", "unknown")
                intel_parts.append(f"Intel confidence: {confidence}")
                if intel_parts:
                    company_intel_section = "\nCOMPANY INTELLIGENCE:\n" + "\n".join(intel_parts) + "\n"

        prompt = PLANNER_PROMPT.format(
            job_title=job_title or "Not specified",
            company=company or "Not specified",
            jd_text=jd_text[:5000],
            catalog_text=catalog_text,
            profile_summary=profile_summary,
            company_intel_section=company_intel_section,
        )

        try:
            result = await self._ai.complete_json(
                prompt=prompt,
                system=PLANNER_SYSTEM,
                max_tokens=2000,
                temperature=0.2,
                task_type="fast_doc",  # Doc planning is a classification task — use Flash
            )
            return self._parse_plan(result)
        except Exception as e:
            logger.warning("document_pack_planner.ai_failed", error=str(e)[:200])
            # Fallback: core docs only, no extras
            return DocumentPackPlan(
                core=list(CORE_DOCS),
                strategy="Fallback: generating core documents only due to planner error.",
                confidence=0.3,
            )

    def _parse_plan(self, raw: Dict[str, Any]) -> DocumentPackPlan:
        """Parse and validate the AI's response into a DocumentPackPlan."""
        plan = DocumentPackPlan(
            core=list(CORE_DOCS),
            strategy=raw.get("strategy", ""),
            industry=raw.get("industry", "other"),
            job_level=raw.get("job_level", "mid"),
            tone=raw.get("tone", "professional"),
            key_themes=raw.get("key_themes", []),
            confidence=min(1.0, max(0.0, raw.get("confidence", 0.8))),
        )

        # Validate required docs — must be in catalog and not core
        core_keys = {"cv", "resume", "cover_letter", "personal_statement", "portfolio"}
        for doc in raw.get("required", []):
            key = doc.get("key", "").strip()
            if not key or key in core_keys:
                continue
            if key in self._catalog_keys:
                plan.required.append({
                    "key": key,
                    "label": doc.get("label", key.replace("_", " ").title()),
                    "priority": "high",
                    "reason": doc.get("reason", ""),
                })
                plan.reasons[key] = doc.get("reason", "Required by job description")

        # Validate optional docs
        required_keys = {d["key"] for d in plan.required}
        for doc in raw.get("optional", []):
            key = doc.get("key", "").strip()
            if not key or key in core_keys or key in required_keys:
                continue
            if key in self._catalog_keys:
                plan.optional.append({
                    "key": key,
                    "label": doc.get("label", key.replace("_", " ").title()),
                    "priority": "medium",
                    "reason": doc.get("reason", ""),
                })
                plan.reasons[key] = doc.get("reason", "Could strengthen application")

        # New candidates — doc types not in catalog
        selected_keys = core_keys | required_keys | {d["key"] for d in plan.optional}
        for doc in raw.get("new_candidates", []):
            key = doc.get("key", "").strip()
            if not key or key in selected_keys or key in self._catalog_keys:
                continue
            plan.new_candidates.append({
                "key": key,
                "label": doc.get("label", key.replace("_", " ").title()),
                "reason": doc.get("reason", ""),
            })
            plan.reasons[key] = doc.get("reason", "New document type discovered")

        # Deferred — everything in catalog that wasn't selected
        all_selected = selected_keys | {d["key"] for d in plan.new_candidates}
        for row in self._catalog:
            key = row.get("key", "")
            if key and key not in all_selected:
                plan.deferred.append({
                    "key": key,
                    "label": row.get("label", ""),
                    "category": row.get("category", ""),
                })

        # Add reasons for core docs
        for doc in CORE_DOCS:
            plan.reasons[doc["key"]] = "Core document — always generated"

        logger.info(
            "document_pack_planner.plan_complete",
            core=len(plan.core),
            required=len(plan.required),
            optional=len(plan.optional),
            new_candidates=len(plan.new_candidates),
            deferred=len(plan.deferred),
            industry=plan.industry,
            confidence=plan.confidence,
        )

        return plan
