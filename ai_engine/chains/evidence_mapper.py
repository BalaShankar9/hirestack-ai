"""
Evidence Mapper Chain
AI-powered mapping of evidence items to skill gaps
"""
from typing import Dict, Any, List

from ai_engine.client import AIClient


EVIDENCE_MAPPER_SYSTEM = """You are an expert career evidence analyst who specializes in matching proof-of-skill artifacts to job requirements.

Your task is to analyze a candidate's evidence portfolio (certificates, projects, courses, awards, publications)
and map each piece of evidence to specific skill gaps identified in their gap analysis.

Be precise about relevance scoring:
- 90-100: Direct, strong proof of the skill (e.g., AWS cert maps to "AWS" gap)
- 70-89: Strong indirect proof (e.g., a cloud project maps to "AWS" gap)
- 50-69: Moderate relevance (e.g., a DevOps cert partially covers "Kubernetes" gap)
- Below 50: Weak or tangential connection — don't include these."""

EVIDENCE_MAP_PROMPT = """Map the candidate's evidence to their identified skill gaps.

═══════════════════════════════════════
SKILL GAPS (from gap analysis):
═══════════════════════════════════════
{skill_gaps}

═══════════════════════════════════════
EVIDENCE PORTFOLIO:
═══════════════════════════════════════
{evidence_items}

For each evidence item, determine which skill gaps it helps address.
Only include mappings with relevance_score >= 50.

Return ONLY valid JSON:
```json
{{
    "mappings": [
        {{
            "evidence_id": "uuid-of-evidence",
            "evidence_title": "Evidence title",
            "skill_name": "Exact skill name from gaps",
            "gap_severity": "critical|major|moderate|minor",
            "relevance_score": 50-100,
            "explanation": "Why this evidence proves this skill (1-2 sentences)"
        }}
    ],
    "unmapped_gaps": [
        {{
            "skill_name": "Skill with no evidence",
            "gap_severity": "critical|major|moderate|minor",
            "suggestion": "What kind of evidence would help"
        }}
    ],
    "unmapped_evidence": [
        {{
            "evidence_id": "uuid",
            "evidence_title": "Title",
            "suggestion": "How this could be better utilized"
        }}
    ],
    "coverage_summary": {{
        "total_gaps": 10,
        "gaps_with_evidence": 6,
        "coverage_percentage": 60,
        "critical_gaps_covered": 2,
        "critical_gaps_total": 3
    }}
}}
```"""


class EvidenceMapperChain:
    """Maps evidence items to skill gaps using AI."""

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client

    async def map_evidence(
        self,
        skill_gaps: List[Dict[str, Any]],
        evidence_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Map evidence items to skill gaps."""
        import json
        prompt = EVIDENCE_MAP_PROMPT.format(
            skill_gaps=json.dumps(skill_gaps, indent=2),
            evidence_items=json.dumps(evidence_items, indent=2),
        )
        return await self.ai.complete_json(
            prompt=prompt,
            system=EVIDENCE_MAPPER_SYSTEM,
            max_tokens=4096,
            temperature=0.2,
        )
