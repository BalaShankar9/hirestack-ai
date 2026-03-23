"""
Document Variant Chain
Generates multiple tone variants of the same document for A/B comparison
"""
from typing import Dict, Any

from ai_engine.client import AIClient


VARIANT_SYSTEM = """You are an elite document strategist who creates multiple versions of the same document,
each with a distinctly different tone and approach. All variants must be factually identical
(same experience, same achievements) but presented with different energy levels."""

VARIANT_PROMPT = """Create a {tone} variant of this {document_type}.

TONE: {tone}
{tone_instructions}

ORIGINAL DOCUMENT:
{original_content}

TARGET ROLE: {job_title} at {company}

REQUIREMENTS:
- Keep ALL factual information identical (dates, companies, achievements, metrics)
- Change ONLY the tone, word choice, sentence structure, and presentation style
- Maintain ATS compatibility (semantic HTML, clear sections)
- The variant should feel distinctly different when read side-by-side with other variants

Return the complete document as clean HTML. No explanations, no markdown fences."""

TONE_INSTRUCTIONS = {
    "conservative": """CONSERVATIVE TONE:
- Formal, traditional corporate language
- Short, declarative sentences
- Focus on stability, reliability, proven track record
- Minimal adjectives, let metrics speak
- Professional and understated
- Think: Fortune 500 executive resume""",

    "balanced": """BALANCED TONE:
- Professional but approachable
- Mix of formal and conversational
- Balanced emphasis on achievements and personality
- Moderate use of action verbs and power words
- Confident without being aggressive
- Think: Well-polished LinkedIn profile""",

    "creative": """CREATIVE TONE:
- Dynamic, energetic language
- Storytelling approach — narrative flow
- Bold action verbs and vivid descriptions
- Personality shines through
- Emphasizes innovation, creativity, impact
- Think: Startup pitch meets professional resume""",
}

VARIANT_ANALYSIS_PROMPT = """Analyze and compare these document variants.

VARIANT 1 ({tone1}):
{variant1}

VARIANT 2 ({tone2}):
{variant2}

VARIANT 3 ({tone3}):
{variant3}

TARGET ROLE: {job_title} at {company}

Return ONLY valid JSON:
```json
{{
    "comparison": [
        {{
            "variant": "conservative",
            "ats_score": 0-100,
            "readability_score": 0-100,
            "keyword_density": 0-100,
            "word_count": 500,
            "best_for": "When to use this variant",
            "strengths": ["Strength 1"],
            "weaknesses": ["Weakness 1"]
        }}
    ],
    "recommendation": {{
        "best_variant": "conservative|balanced|creative",
        "reasoning": "Why this variant is best for this specific role",
        "suggested_hybrid": "Optional: suggest combining elements from multiple variants"
    }}
}}
```"""


class DocumentVariantChain:
    """Generates multiple tone variants of documents."""

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client

    async def generate_variant(
        self,
        original_content: str,
        document_type: str,
        tone: str,
        job_title: str = "",
        company: str = "",
    ) -> str:
        """Generate a single tone variant of a document."""
        tone_inst = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["balanced"])
        prompt = VARIANT_PROMPT.format(
            tone=tone,
            tone_instructions=tone_inst,
            document_type=document_type,
            original_content=original_content,
            job_title=job_title or "Target Role",
            company=company or "Target Company",
        )
        return await self.ai.complete(
            prompt=prompt,
            system=VARIANT_SYSTEM,
            max_tokens=8192,
            temperature=0.6,
        )

    async def compare_variants(
        self,
        variants: dict,
        job_title: str = "",
        company: str = "",
    ) -> Dict[str, Any]:
        """Compare multiple variants and recommend the best one."""
        tones = list(variants.keys())
        prompt = VARIANT_ANALYSIS_PROMPT.format(
            tone1=tones[0] if len(tones) > 0 else "variant1",
            variant1=variants.get(tones[0], "") if len(tones) > 0 else "",
            tone2=tones[1] if len(tones) > 1 else "variant2",
            variant2=variants.get(tones[1], "") if len(tones) > 1 else "",
            tone3=tones[2] if len(tones) > 2 else "variant3",
            variant3=variants.get(tones[2], "") if len(tones) > 2 else "",
            job_title=job_title or "Target Role",
            company=company or "Target Company",
        )
        return await self.ai.complete_json(
            prompt=prompt,
            system=VARIANT_SYSTEM,
            max_tokens=2048,
            temperature=0.3,
        )
