"""
Document Variant Chain
Generates tone-varied document variants for A/B testing
"""
import re
from typing import Any, Dict, List, Optional

import structlog

from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.chains.doc_variant")


# Composite-score weights for winner selection. Sum = 1.0.
# evidence_coverage carries the most weight because Brief 3 (evidence
# graph) made evidence-grounding the platform's differentiator. ATS is
# table-stakes; readability is a tiebreaker.
WINNER_WEIGHTS = {
    "evidence_coverage": 0.45,
    "ats_score": 0.35,
    "readability_score": 0.20,
}


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+\-]{2,}")


def _tokens(text: str) -> List[str]:
    """Lowercase tokens of length >= 3, alphanumeric + a few symbols."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


def _keyword_density(content: str, keywords: List[str]) -> float:
    """Percent of distinct keywords that appear in content. 0.0 - 100.0."""
    if not keywords:
        return 0.0
    body = " ".join(_tokens(content))
    if not body:
        return 0.0
    hits = sum(1 for kw in keywords if kw and kw.lower() in body)
    return round((hits / len(keywords)) * 100.0, 2)


def _readability_score(content: str) -> float:
    """Lightweight Flesch-style score on a 0-100 scale.

    Deterministic heuristic so tests don't need an AI roundtrip.
    Higher = easier to read. Falls back to 60.0 on empty input.
    """
    sentences = max(1, content.count(".") + content.count("!") + content.count("?"))
    words = _tokens(content)
    if not words:
        return 60.0
    avg_sentence_len = len(words) / sentences
    # Penalise long sentences: every word over 18 drops score by 1, capped.
    penalty = max(0.0, min(40.0, (avg_sentence_len - 18.0) * 1.5))
    return round(max(0.0, min(100.0, 80.0 - penalty)), 2)


def _ats_score(content: str, keywords: List[str]) -> int:
    """Lightweight ATS proxy: 50 baseline + keyword coverage + length sanity."""
    base = 50
    coverage = _keyword_density(content, keywords)  # 0-100
    word_count = len(_tokens(content))
    length_bonus = 20 if 250 <= word_count <= 1200 else 5
    score = int(base + (coverage * 0.30) + length_bonus)
    return max(0, min(100, score))


def _composite(per_variant: Dict[str, float]) -> float:
    """Weighted composite of evidence_coverage, ats_score, readability_score."""
    return round(
        WINNER_WEIGHTS["evidence_coverage"] * per_variant.get("evidence_coverage", 0.0)
        + WINNER_WEIGHTS["ats_score"] * per_variant.get("ats_score", 0.0)
        + WINNER_WEIGHTS["readability_score"] * per_variant.get("readability_score", 0.0),
        2,
    )


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


WINNER_REASONING_PROMPT = """You are picking the strongest of these document variants for {job_title} at {company}.

The CANDIDATE has already been chosen by a deterministic composite score
(evidence-coverage 45%, ATS 35%, readability 20%). Your job is ONLY to
write 1-2 sentences explaining WHY this variant suits the role best,
grounded in the variant's tone and the role context. Do NOT second-guess
the score; do NOT pick a different winner.

CANDIDATE TONE: {winner_tone}
CANDIDATE EXCERPT (first 800 chars):
{winner_excerpt}

OTHER TONES CONSIDERED: {other_tones}

Return ONLY valid MINIFIED JSON: {{"reasoning": "..."}}.
"""

WINNER_REASONING_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {"reasoning": {"type": "STRING"}},
    "required": ["reasoning"],
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
        document_content: str = "",
        tone: str = "balanced",
        job_title: str = "",
        company: str = "",
        **kwargs: Any,
    ) -> str:
        """Generate a tone variant of a document.

        Accepts ``document_content`` or legacy alias ``original_content``.
        """
        if not document_content:
            document_content = kwargs.pop("original_content", "") or ""
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

    async def compare_variants(
        self,
        variants: Dict[str, str],
        job_title: str = "",
        company: str = "",
        job_keywords: Optional[List[str]] = None,
        original_content: str = "",
    ) -> Dict[str, Any]:
        """Score every variant, recommend a winner, and explain why.

        Returns a dict shaped::

            {
              "comparison": [
                {"variant": "balanced", "tone": "balanced",
                 "ats_score": 78, "readability_score": 72.5,
                 "keyword_density": 65.0, "evidence_coverage": 65.0,
                 "composite_score": 71.4, "delta_vs_original": {...}},
                ...
              ],
              "winner": {"variant": "balanced",
                         "composite_score": 71.4,
                         "reasoning": "...",
                         "weights": {...}},
              "weights": {...},
            }

        Scoring is deterministic. Only the winner's *reasoning* string
        is AI-generated, and only after the winner is fixed. The AI is
        explicitly forbidden from overriding the score-based pick.
        """
        # Derive keyword list from job_title if caller didn't supply one.
        keywords = job_keywords or [t for t in _tokens(job_title) if len(t) > 2]

        # Baseline scores against the original (if provided) for delta calc.
        base_scores: Dict[str, float] = {}
        if original_content:
            base_scores = {
                "ats_score": float(_ats_score(original_content, keywords)),
                "readability_score": _readability_score(original_content),
                "evidence_coverage": _keyword_density(original_content, keywords),
            }

        comparison: List[Dict[str, Any]] = []
        per_tone_composite: Dict[str, float] = {}

        for tone, content in variants.items():
            ats = _ats_score(content, keywords)
            readability = _readability_score(content)
            coverage = _keyword_density(content, keywords)
            scores = {
                "ats_score": float(ats),
                "readability_score": readability,
                "evidence_coverage": coverage,
            }
            composite = _composite(scores)
            per_tone_composite[tone] = composite

            row: Dict[str, Any] = {
                "variant": tone,
                "tone": tone,
                "ats_score": ats,
                "readability_score": readability,
                "keyword_density": coverage,
                "evidence_coverage": coverage,
                "composite_score": composite,
            }
            if base_scores:
                row["delta_vs_original"] = {
                    k: round(scores[k] - base_scores[k], 2) for k in scores
                }
            comparison.append(row)

        if not per_tone_composite:
            return {
                "comparison": [],
                "winner": None,
                "weights": dict(WINNER_WEIGHTS),
            }

        # Highest composite wins. Ties broken by tone order in the input
        # dict (Python 3.7+ preserves insertion order), which means callers
        # control the tiebreak by ordering tones in their preferred fallback.
        winner_tone = max(per_tone_composite, key=lambda t: per_tone_composite[t])
        winner_excerpt = (variants.get(winner_tone) or "")[:800]
        other_tones = [t for t in per_tone_composite if t != winner_tone]

        reasoning = await self._winner_reasoning(
            winner_tone=winner_tone,
            winner_excerpt=winner_excerpt,
            other_tones=other_tones,
            job_title=job_title,
            company=company,
        )

        return {
            "comparison": comparison,
            "winner": {
                "variant": winner_tone,
                "composite_score": per_tone_composite[winner_tone],
                "reasoning": reasoning,
                "weights": dict(WINNER_WEIGHTS),
            },
            "weights": dict(WINNER_WEIGHTS),
        }

    async def _winner_reasoning(
        self,
        winner_tone: str,
        winner_excerpt: str,
        other_tones: List[str],
        job_title: str,
        company: str,
    ) -> str:
        """Ask the AI to justify the score-picked winner. Failure is non-fatal."""
        try:
            prompt = WINNER_REASONING_PROMPT.format(
                winner_tone=winner_tone,
                winner_excerpt=winner_excerpt,
                other_tones=", ".join(other_tones) or "none",
                job_title=job_title or "the target role",
                company=company or "the company",
            )
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=DOC_VARIANT_SYSTEM,
                temperature=0.2,
                max_tokens=200,
                schema=WINNER_REASONING_SCHEMA,
                task_type="reasoning",
            )
            text = (result or {}).get("reasoning", "").strip()
            return text or _fallback_reasoning(winner_tone)
        except Exception as exc:
            logger.warning("winner_reasoning.failed", error=str(exc)[:200])
            return _fallback_reasoning(winner_tone)


def _fallback_reasoning(tone: str) -> str:
    """Deterministic fallback used when the LLM call fails or returns empty."""
    blurbs = {
        "conservative": "Highest composite score: strongest keyword coverage and crisp readability suit a formal screen.",
        "balanced": "Highest composite score: best mix of evidence coverage, ATS-friendliness, and readability.",
        "creative": "Highest composite score: distinctive framing without sacrificing keyword coverage.",
    }
    return blurbs.get(tone, f"Highest composite score across the {tone} variant.")
