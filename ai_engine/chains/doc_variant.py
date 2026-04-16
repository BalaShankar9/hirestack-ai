"""
Document Variant Chain
Generates tone-varied document variants for A/B testing
"""
from typing import Dict, Any

import structlog

from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.chains.doc_variant")


DOC_VARIANT_SYSTEM = """You are an expert document writer specializing in creating
tone-varied versions of professional documents (CVs, cover letters, portfolios).

You understand how different tones affect reader perception:
- Conservative: Formal, structured, traditional — preferred by finance, legal, government
- Balanced: Professional yet approachable — works across most industries
- Creative: Bold, storytelling, personality-forward — ideal for creative/startup roles

Preserve all factual content while adjusting style, voice, and framing."""


VARIANT_PROMPT = """Create a {tone} tone variant of this document.

ORIGINAL DOCUMENT:
{document_content}

TONE INSTRUCTIONS: {tone_instructions}

TARGET ROLE: {job_title} at {company}

Return ONLY the rewritten document HTML. Do not include JSON or commentary."""


VARIANT_METADATA_PROMPT = """Analyze the differences between these two document variants and return metadata.

VARIANT A (original):
{original}

VARIANT B ({tone}):
{variant}

Return ONLY valid MINIFIED JSON (no markdown, no code fences).
"""

VARIANT_METADATA_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "tone": {"type": "STRING"},
        "key_differences": {"type": "ARRAY", "items": {"type": "STRING"}},
        "target_audience": {"type": "STRING"},
        "best_for_roles": {"type": "ARRAY", "items": {"type": "STRING"}},
        "predicted_ats_impact": {"type": "STRING"},
        "predicted_human_impact": {"type": "STRING"},
    },
    "required": ["tone", "key_differences"],
}


class DocumentVariantChain:
    """Chain for generating document tone variants."""

    VERSION = "1.0.0"

    TONE_INSTRUCTIONS = {
        "conservative": (
            "Use formal language, traditional structure, quantified achievements, no personality flair"
        ),
        "balanced": (
            "Professional but approachable, mix of quantified and narrative, moderate personality"
        ),
        "creative": (
            "Bold opening, storytelling elements, unique framing, personality-forward"
        ),
    }

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def generate_variant(
        self,
        document_content: str,
        tone: str = "balanced",
        job_title: str = "",
        company: str = "",
        **kwargs: Any,
    ) -> str:
        """Generate a tone variant of a document."""
        try:
            tone_instructions = self.TONE_INSTRUCTIONS.get(tone, self.TONE_INSTRUCTIONS["balanced"])

            prompt = VARIANT_PROMPT.format(
                tone=tone,
                document_content=document_content[:8000],
                tone_instructions=tone_instructions,
                job_title=job_title or "the target role",
                company=company or "the company",
            )

            result = await self.ai_client.complete(
                prompt=prompt,
                system=DOC_VARIANT_SYSTEM,
                temperature=0.4,
                max_tokens=4000,
                task_type="drafting",
            )

            return result
        except Exception as exc:
            logger.warning("generate_variant.failed", error=str(exc)[:200])
            return document_content  # Return original on failure

    async def generate_variant_metadata(
        self,
        original: str,
        variant: str,
        tone: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate metadata comparing two document variants."""
        try:
            prompt = VARIANT_METADATA_PROMPT.format(
                original=original[:4000],
                tone=tone,
                variant=variant[:4000],
            )

            return await self.ai_client.complete_json(
                prompt=prompt,
                system=DOC_VARIANT_SYSTEM,
                temperature=0.0,
                max_tokens=1000,
                schema=VARIANT_METADATA_SCHEMA,
                task_type="reasoning",
            )
        except Exception as exc:
            logger.warning("generate_variant_metadata.failed", error=str(exc)[:200])
            return {"tone": tone, "key_differences": []}
