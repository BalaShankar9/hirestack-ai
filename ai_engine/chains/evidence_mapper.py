"""
Evidence Mapper Chain
Maps user evidence items to identified skill gaps using AI
"""
from typing import Dict, Any, List

from ai_engine.client import AIClient


EVIDENCE_MAPPER_SYSTEM = """You are an expert career evidence analyst.

Your task is to map a candidate's evidence items (certifications, projects, publications, etc.)
to their identified skill gaps. For each gap, determine which evidence items partially or fully
address it, and provide a relevance score and explanation."""

EVIDENCE_MAPPING_PROMPT = """Map the following evidence items to the candidate's skill gaps.

SKILL_GAPS:
{skill_gaps}

EVIDENCE_ITEMS:
{evidence_items}

For each evidence item, determine which skill gap(s) it addresses.
Return ONLY valid MINIFIED JSON with this structure:
{{
  "mappings": [
    {{
      "evidence_id": "<id>",
      "skill_name": "<gap skill name>",
      "gap_severity": "<high|medium|low>",
      "relevance_score": <0-100>,
      "explanation": "<why this evidence addresses the gap>"
    }}
  ],
  "unmapped_gaps": ["<skill names with no matching evidence>"],
  "summary": "<brief overall assessment>"
}}

Only include mappings with relevance_score >= 30.
No markdown, no code fences, no trailing commas."""


class EvidenceMapperChain:
    """Chain that maps evidence items to skill gaps."""

    def __init__(self, client: AIClient):
        self.client = client

    async def map_evidence(
        self,
        skill_gaps: List[Dict[str, Any]],
        evidence_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Map evidence items to skill gaps."""
        import json

        prompt = EVIDENCE_MAPPING_PROMPT.format(
            skill_gaps=json.dumps(skill_gaps, default=str),
            evidence_items=json.dumps(evidence_items, default=str),
        )

        result = await self.client.generate(
            prompt=prompt,
            system=EVIDENCE_MAPPER_SYSTEM,
            response_format="json",
        )

        if isinstance(result, str):
            result = json.loads(result)

        return result
