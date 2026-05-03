"""
ContentEnhancer — AI-optimized text for presentations.

Transforms draft content into punchy, impactful presentation text:
- Title enhancement (passive → active, generic → specific)
- Bullet compression (auto-shorten to target length)
- Speaker note generation from slide content
- Impact scoring and A/B variant generation
- Readability optimization

Public API:
    ContentEnhancer().enhance_title(title, context) -> EnhancedTitle
    ContentEnhancer().compress_bullets(bullets, max_chars=120) -> List[str]
    ContentEnhancer().generate_speaker_notes(slide) -> str
    ContentEnhancer().score_impact(text) -> ImpactScore
    ContentEnhancer().enhance_slide(slide) -> SlideSpec

Integration:
    Works with OutlinePlanner for pre-rendering enhancement
    or post-generation refinement of existing decks.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.agents.ppt.schemas import SlideKind, SlideSpec

logger = logging.getLogger(__name__)


@dataclass
class EnhancedTitle:
    """Result of title enhancement."""

    original: str
    enhanced: str
    variants: List[str]
    score_original: float
    score_enhanced: float
    improvements: List[str]


@dataclass
class ImpactScore:
    """Text impact analysis."""

    overall: float  # 0-1
    specificity: float
    action_orientation: float
    brevity: float
    emotional_appeal: float
    suggestions: List[str]


class ContentEnhancer:
    """Enhance presentation content for maximum impact."""

    # Target constraints
    DEFAULT_MAX_BULLET_CHARS = 120
    DEFAULT_MAX_BULLETS = 6
    TARGET_READABILITY = 60  # Flesch Reading Ease score

    # Power words for titles
    POWER_WORDS = {
        "action": ["boost", "drive", "accelerate", "transform", "unlock", "maximize",
                   "dominate", "crush", "skyrocket", "supercharge"],
        "results": ["proven", "guaranteed", "rapid", "massive", "explosive",
                   "extraordinary", "breakthrough", "pioneering"],
        "exclusivity": ["exclusive", "limited", "premium", "vip", "elite",
                       "insider", "secret", "proprietary"],
        "safety": ["secure", "safe", "protected", "guaranteed", "risk-free",
                  "bulletproof", "proven"],
    }

    # Weak words to replace
    WEAK_PATTERNS = {
        r"\bgood\b": "exceptional",
        r"\bbad\b": "problematic",
        r"\bbig\b": "substantial",
        r"\bsmall\b": "minimal",
        r"\bmany\b": "numerous",
        r"\bfew\b": "limited",
        r"\bvery\b": "",  # Remove entirely
        r"\breally\b": "",
        r"\bquite\b": "",
        r"\bjust\b": "",
        r"\bsimply\b": "",
        r"\bbasically\b": "",
        r"\bactually\b": "",
        r"\bkind of\b": "",
        r"\bsort of\b": "",
        r"\bin my opinion\b": "",
        r"\bi think\b": "",
        r"\bi believe\b": "",
    }

    # Passive voice indicators
    PASSIVE_INDICATORS = [
        "was", "were", "been", "being", "is being", "are being",
        "has been", "have been", "had been", "will be", "would be",
    ]

    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self.ai_client = ai_client

    def _get_client(self) -> Any:
        """Lazy load AI client."""
        if self.ai_client is not None:
            return self.ai_client
        from ai_engine.client import get_ai_client
        return get_ai_client()

    # ───────────────────────────────────────────────────────────────────────
    #  Public Enhancement Methods
    # ───────────────────────────────────────────────────────────────────────

    async def enhance_title(
        self,
        title: str,
        context: str = "",
        generate_variants: bool = True,
    ) -> EnhancedTitle:
        """
        Enhance a slide title for maximum impact.

        Args:
            title: Original title text
            context: Additional context about slide content
            generate_variants: Whether to generate A/B variants

        Returns:
            EnhancedTitle with improved version and variants
        """
        score_original = self._score_title(title)

        # Apply rule-based improvements first
        enhanced = self._improve_title_rules(title)

        # If AI available, further enhance
        try:
            enhanced = await self._ai_enhance_title(enhanced, context)
        except Exception as exc:
            logger.debug("ai_title_enhance_failed: %s", str(exc)[:200])

        score_enhanced = self._score_title(enhanced)

        variants = []
        if generate_variants:
            variants = self._generate_title_variants(title, enhanced)

        improvements = self._identify_improvements(title, enhanced)

        return EnhancedTitle(
            original=title,
            enhanced=enhanced,
            variants=variants,
            score_original=score_original,
            score_enhanced=score_enhanced,
            improvements=improvements,
        )

    def compress_bullets(
        self,
        bullets: List[str],
        max_chars: int = 120,
        max_bullets: int = 6,
    ) -> List[str]:
        """
        Compress bullets to meet length constraints.

        Args:
            bullets: Original bullet points
            max_chars: Maximum characters per bullet
            max_bullets: Maximum number of bullets

        Returns:
            Compressed bullet list
        """
        if not bullets:
            return []

        compressed = []
        for bullet in bullets[:max_bullets]:
            # Strip to max length intelligently
            if len(bullet) <= max_chars:
                compressed.append(self._polish_bullet(bullet))
            else:
                compressed.append(self._truncate_bullet(bullet, max_chars))

        return [b for b in compressed if b]

    async def generate_speaker_notes(
        self,
        slide: SlideSpec,
        tone: str = "professional",
        detail_level: str = "medium",
    ) -> str:
        """
        Generate speaker notes from slide content.

        Args:
            slide: SlideSpec to generate notes for
            tone: casual, professional, executive
            detail_level: brief, medium, detailed

        Returns:
            Generated speaker notes
        """
        content = self._extract_slide_content(slide)

        if not content:
            return ""

        try:
            return await self._ai_generate_notes(content, tone, detail_level)
        except Exception as exc:
            logger.debug("ai_notes_generation_failed: %s", str(exc)[:200])
            return self._generate_notes_rule_based(content, detail_level)

    def score_impact(self, text: str) -> ImpactScore:
        """
        Score text for presentation impact.

        Args:
            text: Text to analyze

        Returns:
            ImpactScore with component scores
        """
        specificity = self._score_specificity(text)
        action = self._score_action_orientation(text)
        brevity = self._score_brevity(text)
        emotional = self._score_emotional_appeal(text)

        overall = (specificity + action + brevity + emotional) / 4

        suggestions = []
        if specificity < 0.5:
            suggestions.append("Add specific numbers or examples")
        if action < 0.5:
            suggestions.append("Use active voice and action verbs")
        if brevity < 0.5:
            suggestions.append("Shorten or break into smaller chunks")
        if emotional < 0.3:
            suggestions.append("Add emotional resonance or urgency")

        return ImpactScore(
            overall=overall,
            specificity=specificity,
            action_orientation=action,
            brevity=brevity,
            emotional_appeal=emotional,
            suggestions=suggestions,
        )

    async def enhance_slide(self, slide: SlideSpec) -> SlideSpec:
        """
        Apply all enhancements to a slide.

        Args:
            slide: Original SlideSpec

        Returns:
            Enhanced SlideSpec
        """
        updates = {}

        # Enhance title
        if slide.title:
            enhanced = await self.enhance_title(slide.title)
            if enhanced.score_enhanced > enhanced.score_original + 0.1:
                updates["title"] = enhanced.enhanced

        # Compress bullets
        if slide.bullets:
            compressed = self.compress_bullets(slide.bullets)
            if compressed != slide.bullets:
                updates["bullets"] = compressed

        # Generate notes if missing
        if not slide.notes:
            notes = await self.generate_speaker_notes(slide)
            if notes:
                updates["notes"] = notes

        if updates:
            return slide.model_copy(update=updates)
        return slide

    async def enhance_deck(self, slides: List[SlideSpec]) -> List[SlideSpec]:
        """Enhance all slides in a deck."""
        enhanced = []
        for slide in slides:
            enhanced.append(await self.enhance_slide(slide))
        return enhanced

    # ───────────────────────────────────────────────────────────────────────
    #  Rule-Based Improvements
    # ───────────────────────────────────────────────────────────────────────

    def _improve_title_rules(self, title: str) -> str:
        """Apply rule-based title improvements."""
        enhanced = title

        # Replace weak words
        for pattern, replacement in self.WEAK_PATTERNS.items():
            enhanced = re.sub(pattern, replacement, enhanced, flags=re.IGNORECASE)

        # Remove extra spaces from deletions
        enhanced = " ".join(enhanced.split())

        # Capitalize properly
        enhanced = enhanced.strip()
        if enhanced and not enhanced[0].isupper():
            enhanced = enhanced[0].upper() + enhanced[1:]

        return enhanced

    def _polish_bullet(self, bullet: str) -> str:
        """Clean up and polish a bullet point."""
        # Remove weak words
        polished = bullet
        for pattern, replacement in self.WEAK_PATTERNS.items():
            polished = re.sub(pattern, replacement, polished, flags=re.IGNORECASE)

        # Clean up extra spaces
        polished = " ".join(polished.split())

        # Ensure consistent ending (no period for fragments)
        if "." not in polished[:len(polished)//2]:  # No early period = fragment
            polished = polished.rstrip(".")

        return polished.strip()

    def _truncate_bullet(self, bullet: str, max_chars: int) -> str:
        """Intelligently truncate a bullet."""
        if len(bullet) <= max_chars:
            return bullet

        # Try to break at sentence boundary
        truncated = bullet[:max_chars]

        # Find last good break point
        for break_char in ['. ', '; ', ', ', ' ']:
            last_break = truncated.rfind(break_char, 0, max_chars - 3)
            if last_break > max_chars * 0.6:  # At least 60% of text
                truncated = truncated[:last_break] + '...'
                return truncated

        # Hard break with ellipsis
        return truncated[:max_chars-3].rstrip() + '...'

    def _generate_title_variants(self, original: str, enhanced: str) -> List[str]:
        """Generate A/B test variants for a title."""
        variants = []

        # Variant 1: Question format
        if '?' not in original:
            variants.append(f"How {enhanced.lower()}?")

        # Variant 2: Number prefix
        variants.append(f"3 Ways to {enhanced.lower()}")

        # Variant 3: Benefit-focused
        variants.append(f"The Secret to {enhanced}")

        # Variant 4: Urgency
        variants.append(f"Why {enhanced} Matters Now")

        return variants[:3]  # Return top 3

    def _identify_improvements(self, original: str, enhanced: str) -> List[str]:
        """List specific improvements made."""
        improvements = []

        # Check word count reduction
        orig_words = len(original.split())
        new_words = len(enhanced.split())
        if new_words < orig_words:
            improvements.append(f"Reduced from {orig_words} to {new_words} words")

        # Check for power words added
        for category, words in self.POWER_WORDS.items():
            for word in words:
                if word.lower() in enhanced.lower() and word.lower() not in original.lower():
                    improvements.append(f"Added {category} power word: '{word}'")
                    break

        # Check for passive voice removal
        orig_passive = sum(1 for p in self.PASSIVE_INDICATORS if p in original.lower())
        new_passive = sum(1 for p in self.PASSIVE_INDICATORS if p in enhanced.lower())
        if new_passive < orig_passive:
            improvements.append("Converted to active voice")

        return improvements

    # ───────────────────────────────────────────────────────────────────────
    #  Scoring Methods
    # ───────────────────────────────────────────────────────────────────────

    def _score_title(self, title: str) -> float:
        """Score a title 0-1."""
        if not title:
            return 0.0

        score = 0.5  # Base score

        # Length check (optimal: 30-60 chars)
        length = len(title)
        if 30 <= length <= 60:
            score += 0.15
        elif length > 80:
            score -= 0.1

        # Power words
        power_count = sum(1 for cat in self.POWER_WORDS.values()
                         for word in cat if word.lower() in title.lower())
        score += min(power_count * 0.05, 0.15)

        # Numbers (specificity)
        if re.search(r'\d', title):
            score += 0.1

        # Active voice
        passive_count = sum(1 for p in self.PASSIVE_INDICATORS if p in title.lower())
        score -= passive_count * 0.05

        # No weak words
        weak_count = sum(1 for p in self.WEAK_PATTERNS if re.search(p, title, re.I))
        score -= weak_count * 0.03

        return max(0.0, min(1.0, score))

    def _score_specificity(self, text: str) -> float:
        """Score specificity 0-1."""
        if not text:
            return 0.0

        score = 0.3  # Base

        # Numbers indicate specificity
        if re.search(r'\d+%?', text):
            score += 0.3

        # Time references
        if re.search(r'\b(202[0-9]|Q[1-4]|January|February|March|April|May|June|'
                    r'July|August|September|October|November|December)\b', text, re.I):
            score += 0.2

        # Named entities (capitalized words)
        caps = len(re.findall(r'\b[A-Z][a-z]+\b', text))
        score += min(caps * 0.05, 0.2)

        return min(1.0, score)

    def _score_action_orientation(self, text: str) -> float:
        """Score action orientation 0-1."""
        if not text:
            return 0.0

        text_lower = text.lower()

        # Check for action verbs
        action_verbs = ['drive', 'boost', 'achieve', 'deliver', 'create', 'build',
                       'launch', 'grow', 'increase', 'improve', 'transform']
        action_count = sum(1 for v in action_verbs if v in text_lower)

        # Check for passive indicators
        passive_count = sum(1 for p in self.PASSIVE_INDICATORS if p in text_lower)

        score = 0.3 + (action_count * 0.1) - (passive_count * 0.1)
        return max(0.0, min(1.0, score))

    def _score_brevity(self, text: str) -> float:
        """Score brevity 0-1."""
        if not text:
            return 0.0

        word_count = len(text.split())
        char_count = len(text)

        # Optimal: 5-15 words, under 120 chars
        if 5 <= word_count <= 15 and char_count <= 120:
            return 1.0
        elif word_count <= 20 and char_count <= 150:
            return 0.8
        elif word_count <= 30:
            return 0.5
        else:
            return 0.3

    def _score_emotional_appeal(self, text: str) -> float:
        """Score emotional appeal 0-1."""
        if not text:
            return 0.0

        text_lower = text.lower()

        # Emotional indicators
        positive = ['success', 'win', 'triumph', 'breakthrough', 'revolutionary',
                   'transformative', 'game-changing']
        urgency = ['now', 'today', 'urgent', 'critical', 'essential', 'must']
        exclusivity = ['exclusive', 'limited', 'unique', 'secret', 'insider']

        score = 0.2
        score += sum(0.1 for p in positive if p in text_lower)
        score += sum(0.08 for u in urgency if u in text_lower)
        score += sum(0.08 for e in exclusivity if e in text_lower)

        return min(1.0, score)

    # ───────────────────────────────────────────────────────────────────────
    #  AI Integration
    # ───────────────────────────────────────────────────────────────────────

    async def _ai_enhance_title(self, title: str, context: str) -> str:
        """Use AI to further enhance a title."""
        client = self._get_client()

        prompt = f"""Rewrite this presentation title to be more impactful and specific.
Original: "{title}"
Context: {context}

Requirements:
- Keep it under 60 characters
- Use active voice
- Include a number or specific metric if possible
- Make it punchy and memorable
- Output ONLY the improved title, nothing else"""

        response = await client.complete(
            prompt=prompt,
            system="You are an expert presentation copywriter.",
            max_tokens=50,
            temperature=0.4,
        )

        return response.strip().strip('"')

    async def _ai_generate_notes(
        self,
        content: str,
        tone: str,
        detail_level: str,
    ) -> str:
        """Use AI to generate speaker notes."""
        client = self._get_client()

        length_guide = {
            "brief": "2-3 sentences",
            "medium": "1 paragraph (4-5 sentences)",
            "detailed": "2 paragraphs with context and examples",
        }

        prompt = f"""Generate speaker notes for this slide content.

Content: {content}

Requirements:
- Tone: {tone}
- Length: {length_guide.get(detail_level, "medium")}
- Include key talking points
- Add transition to next slide
- Output ONLY the speaker notes"""

        response = await client.complete(
            prompt=prompt,
            system="You are a presentation coach helping speakers deliver impactful talks.",
            max_tokens=200,
            temperature=0.5,
        )

        return response.strip()

    # ───────────────────────────────────────────────────────────────────────
    #  Utility Methods
    # ───────────────────────────────────────────────────────────────────────

    def _extract_slide_content(self, slide: SlideSpec) -> str:
        """Extract all content from a slide."""
        parts = [slide.title or ""]
        parts.extend(slide.bullets or [])
        if slide.body:
            parts.append(slide.body)
        return " ".join(filter(None, parts))

    def _generate_notes_rule_based(
        self,
        content: str,
        detail_level: str,
    ) -> str:
        """Generate basic notes without AI."""
        if not content:
            return ""

        bullets = content.split(".")
        bullets = [b.strip() for b in bullets if len(b.strip()) > 10]

        if detail_level == "brief":
            return f"Key point: {bullets[0] if bullets else 'Discuss main topic'}."
        elif detail_level == "detailed":
            return " ".join(bullets[:3])
        else:
            return bullets[0] if bullets else ""


# Convenience functions

async def enhance_title(title: str, context: str = "") -> str:
    """One-shot title enhancement."""
    enhancer = ContentEnhancer()
    result = await enhancer.enhance_title(title, context)
    return result.enhanced


def compress_bullets(bullets: List[str], max_chars: int = 120) -> List[str]:
    """One-shot bullet compression."""
    enhancer = ContentEnhancer()
    return enhancer.compress_bullets(bullets, max_chars)


async def generate_notes(slide: SlideSpec) -> str:
    """One-shot speaker notes generation."""
    enhancer = ContentEnhancer()
    return await enhancer.generate_speaker_notes(slide)
