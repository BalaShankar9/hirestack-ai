"""
Document Discovery Chain
Analyzes a job description to determine exactly which documents the application needs.
Different jobs require different document sets — this chain figures out what's needed.
"""
from typing import Dict, Any


DISCOVERY_SYSTEM = """You are a senior career strategist who has placed 10,000+ candidates across every industry.
You know exactly which application documents each job type requires.

Your job: analyze a job description and determine the COMPLETE set of documents needed for a winning application.

Key rules:
- EVERY job needs a CV/resume and cover letter (minimum)
- Academic/research roles need: research statement, teaching philosophy, publications list
- Government/public sector roles need: selection criteria responses (STAR method)
- Creative roles need: portfolio, case studies
- Senior/executive roles need: executive summary
- European/international roles often need: motivation letter (instead of or alongside cover letter)
- Consulting roles need: case study or project proposals
- Any role explicitly requesting specific documents in the JD must include those

Return ONLY valid JSON."""

DISCOVERY_PROMPT = """Analyze this job description and determine exactly which documents are needed for a complete, winning application.

JOB TITLE: {job_title}
COMPANY: {company}

JOB DESCRIPTION:
{jd_text}

Return JSON:
{{
  "required_documents": [
    {{
      "key": "unique_snake_case_key",
      "label": "Human-readable document name",
      "priority": "critical|high|medium",
      "reason": "Why this document is needed for THIS specific job",
      "max_pages": 2,
      "format_notes": "Any specific formatting requirements mentioned in the JD"
    }}
  ],
  "optional_documents": [
    {{
      "key": "unique_snake_case_key",
      "label": "Human-readable document name",
      "priority": "medium|low",
      "reason": "Why this could strengthen the application"
    }}
  ],
  "industry": "technology|finance|healthcare|academic|government|creative|consulting|legal|other",
  "job_level": "junior|mid|senior|executive|academic",
  "document_strategy": "2-3 sentence strategy for how documents should be tailored for this specific role",
  "tone": "formal|professional|conversational|academic|creative",
  "key_themes": ["3-5 themes that should run through ALL documents"]
}}

IMPORTANT: The system ALWAYS generates these standard documents automatically:
cv, cover_letter, personal_statement, portfolio, learning_plan

DO NOT include those in your required_documents list.
Only include ADDITIONAL documents that this specific job needs beyond the standard set.
If no extra documents are needed, return empty required_documents and optional_documents.

Valid EXTRA document keys (only include if truly needed for this job):
executive_summary, selection_criteria, research_statement, teaching_philosophy,
publications_list, project_proposals, case_study, diversity_statement,
motivation_letter, references_list, writing_sample, technical_assessment,
elevator_pitch, ninety_day_plan, recommendation_letter_template, values_statement,
leadership_philosophy, clinical_portfolio, design_portfolio, code_samples,
consulting_deck, board_presentation, grant_proposal, thesis_abstract,
professional_development_plan, community_engagement_statement, safety_statement,
equity_statement, conflict_of_interest_declaration, media_kit, speaker_bio"""


class DocumentDiscoveryChain:
    """Analyzes JD to determine required application documents."""

    VERSION = "1.0.0"

    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def discover(
        self,
        jd_text: str,
        job_title: str = "",
        company: str = "",
    ) -> Dict[str, Any]:
        """Analyze JD and return the document set needed."""
        prompt = DISCOVERY_PROMPT.format(
            job_title=job_title or "Not specified",
            company=company or "Not specified",
            jd_text=jd_text[:5000],
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=DISCOVERY_SYSTEM,
            max_tokens=2000,
            temperature=0.2,
            task_type="reasoning",
        )

        # Validate and ensure minimum documents
        required = result.get("required_documents") or []
        optional = result.get("optional_documents") or []

        # Ensure CV and cover letter are always included
        req_keys = {d.get("key") for d in required}
        if "cv" not in req_keys:
            required.insert(0, {"key": "cv", "label": "Tailored CV", "priority": "critical", "reason": "Standard requirement"})
        if "cover_letter" not in req_keys:
            required.insert(1, {"key": "cover_letter", "label": "Cover Letter", "priority": "critical", "reason": "Standard requirement"})

        # Always add learning_plan as internal doc
        all_keys = req_keys | {d.get("key") for d in optional}
        if "learning_plan" not in all_keys:
            optional.append({"key": "learning_plan", "label": "Learning Plan", "priority": "medium", "reason": "Internal skill development roadmap"})

        result["required_documents"] = required
        result["optional_documents"] = optional
        result.setdefault("industry", "other")
        result.setdefault("job_level", "mid")
        result.setdefault("document_strategy", "")
        result.setdefault("tone", "professional")
        result.setdefault("key_themes", [])

        return result
