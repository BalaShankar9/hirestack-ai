"""
Validator Chain
Quality checks and validation for all AI outputs
"""
from typing import Dict, Any, List, Tuple

from ai_engine.client import AIClient


VALIDATOR_SYSTEM = """You are a quality assurance specialist for career documents and analysis.

Your role is to:
1. Verify accuracy and consistency of information
2. Check for factual errors or fabrications
3. Ensure professional tone and formatting
4. Validate completeness of required sections
5. Flag any concerning content

Be thorough but constructive. Identify issues and suggest fixes."""


DOCUMENT_VALIDATION_PROMPT = """Validate this generated document for quality and accuracy:

DOCUMENT TYPE: {document_type}

ORIGINAL PROFILE DATA:
{profile_data}

GENERATED CONTENT:
{content}

Check for:
1. Accuracy - Does it match the source data?
2. Fabrication - Any invented achievements or experiences?
3. Consistency - Are dates, titles, and facts consistent?
4. Professionalism - Is the tone appropriate?
5. Completeness - Are all sections properly filled?
6. Grammar - Any spelling or grammar issues?

Return ONLY valid JSON:
```json
{{
  "is_valid": true/false,
  "quality_score": 85,
  "issues": [
    {{
      "severity": "critical|major|minor",
      "category": "accuracy|fabrication|consistency|professionalism|completeness|grammar",
      "description": "What the issue is",
      "location": "Where in the document",
      "suggestion": "How to fix it"
    }}
  ],
  "warnings": [
    "Non-critical observations"
  ],
  "improvements": [
    "Suggestions to enhance quality"
  ]
}}
```"""


ANALYSIS_VALIDATION_PROMPT = """Validate this gap analysis for accuracy and fairness:

USER PROFILE:
{user_profile}

BENCHMARK:
{benchmark}

GENERATED ANALYSIS:
{analysis}

Verify:
1. Scores are fair and justified
2. Gaps are accurately identified
3. Recommendations are realistic
4. No unfair bias in assessment
5. Strengths are properly recognized

Return ONLY valid JSON:
```json
{{
  "is_valid": true/false,
  "fairness_score": 90,
  "issues": [
    {{
      "type": "scoring|gaps|recommendations|bias",
      "description": "Issue description",
      "suggestion": "How to correct"
    }}
  ],
  "verified_elements": [
    "Elements that are accurate"
  ]
}}
```"""


class ValidatorChain:
    """Chain for validating AI-generated content."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def validate_document(
        self,
        document_type: str,
        content: str,
        profile_data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Validate a generated document."""
        import json

        prompt = DOCUMENT_VALIDATION_PROMPT.format(
            document_type=document_type,
            profile_data=json.dumps(profile_data, indent=2),
            content=content
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=VALIDATOR_SYSTEM,
            temperature=0.2,
            max_tokens=2000
        )

        is_valid = result.get("is_valid", True)

        # Check for critical issues
        critical_issues = [
            i for i in result.get("issues", [])
            if i.get("severity") == "critical"
        ]

        if critical_issues:
            is_valid = False

        return is_valid, result

    async def validate_analysis(
        self,
        user_profile: Dict[str, Any],
        benchmark: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Validate a gap analysis."""
        import json

        prompt = ANALYSIS_VALIDATION_PROMPT.format(
            user_profile=json.dumps(user_profile, indent=2),
            benchmark=json.dumps(benchmark, indent=2),
            analysis=json.dumps(analysis, indent=2)
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=VALIDATOR_SYSTEM,
            temperature=0.2,
            max_tokens=2000
        )

        return result.get("is_valid", True), result

    def validate_json_structure(
        self,
        data: Dict[str, Any],
        required_fields: List[str]
    ) -> Tuple[bool, List[str]]:
        """Validate JSON has required fields."""
        missing = []
        for field in required_fields:
            if field not in data or data[field] is None:
                missing.append(field)

        return len(missing) == 0, missing

    def sanitize_content(self, content: str) -> str:
        """Sanitize content for safe display."""
        # Remove potential XSS vectors while preserving markdown
        import re

        # Remove script tags
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)

        # Remove onclick and other event handlers
        content = re.sub(r'\bon\w+\s*=', '', content, flags=re.IGNORECASE)

        # Remove javascript: links
        content = re.sub(r'javascript:', '', content, flags=re.IGNORECASE)

        return content

    def check_for_fabrication(
        self,
        generated: Dict[str, Any],
        source: Dict[str, Any]
    ) -> List[str]:
        """Check if generated content fabricates information."""
        warnings = []

        # Check experience
        gen_companies = set()
        if generated.get("experience"):
            for exp in generated["experience"]:
                if exp.get("company"):
                    gen_companies.add(exp["company"].lower())

        source_companies = set()
        if source.get("experience"):
            for exp in source["experience"]:
                if exp.get("company"):
                    source_companies.add(exp["company"].lower())

        fabricated_companies = gen_companies - source_companies
        if fabricated_companies:
            warnings.append(f"Potentially fabricated companies: {fabricated_companies}")

        return warnings
