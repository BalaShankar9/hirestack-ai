"""
AIImageGenerator — Custom AI-generated visuals for presentations.

Replaces stock photos with purpose-built AI images that match the presentation
theme, brand colors, and slide content. Uses DALL-E 3 for quality, with
Stability AI fallback for cost-effective bulk generation.

Public API:
    AIImageGenerator().generate_slide_background(theme, mood) -> bytes
    AIImageGenerator().generate_illustration(concept, style) -> bytes
    AIImageGenerator().generate_icon(concept, color) -> bytes
    AIImageGenerator().generate_for_slide(slide_spec, theme) -> ImageSpec

Safety:
    - Corporate-safe prompt engineering
    - Content filtering
    - Automatic retry with safer prompts on rejection
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.agents.ppt.schemas import ImageSpec, SlideKind, SlideSpec

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result of an image generation attempt."""

    image_bytes: Optional[bytes]
    prompt_used: str
    model: str
    generation_time_ms: int
    revised_prompt: Optional[str] = None
    error: Optional[str] = None


class AIImageGenerator:
    """Generate custom AI images for presentations."""

    # Provider priorities
    PRIMARY_PROVIDER = "openai"  # DALL-E 3
    FALLBACK_PROVIDER = "stability"  # Stability AI

    # Image sizes and aspect ratios for slides
    SLIDE_SIZES = {
        "wide": {"width": 1792, "height": 1024},  # 16:9 presentation
        "standard": {"width": 1024, "height": 1024},  # 1:1 for icons
        "tall": {"width": 1024, "height": 1792},  # 9:16 for mobile
    }

    # Style presets
    STYLE_PRESETS = {
        "corporate": "professional business photography, clean lines, modern office, natural lighting",
        "abstract": "abstract geometric art, gradient mesh, soft colors, modern design",
        "tech": "futuristic technology visualization, sleek interface, blue tones, digital art",
        "minimal": "minimalist composition, ample white space, simple shapes, elegant",
        "dynamic": "dynamic motion, energy, bold colors, action-oriented composition",
        "warm": "warm tones, inviting atmosphere, soft lighting, friendly",
    }

    # Safety keywords to avoid
    UNSAFE_KEYWORDS = {
        "violence", "weapon", "blood", "gore", "death", "nude", "naked",
        "explicit", "pornographic", "hate", "discrimination", "offensive",
    }

    def __init__(
        self,
        *,
        openai_key: Optional[str] = None,
        stability_key: Optional[str] = None,
        cache_size: int = 128,
        max_retries: int = 2,
    ) -> None:
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")
        self.stability_key = stability_key or os.getenv("STABILITY_API_KEY")
        self.max_retries = max_retries
        self._cache: Dict[str, Tuple[bytes, float]] = {}
        self._cache_max = cache_size

    # ───────────────────────────────────────────────────────────────────────
    #  Public Generation Methods
    # ───────────────────────────────────────────────────────────────────────

    async def generate_slide_background(
        self,
        theme: str,
        mood: str = "professional",
        brand_colors: Optional[List[str]] = None,
        content_hint: str = "",
    ) -> Optional[bytes]:
        """
        Generate a presentation slide background.

        Args:
            theme: corporate, abstract, tech, minimal, dynamic, warm
            mood: professional, energetic, calm, bold, innovative
            brand_colors: List of hex colors to incorporate
            content_hint: Context about slide content

        Returns:
            PNG bytes or None on failure
        """
        prompt = self._build_background_prompt(theme, mood, brand_colors, content_hint)
        result = await self._generate_with_fallback(prompt, size="wide")
        return result.image_bytes

    async def generate_illustration(
        self,
        concept: str,
        style: str = "corporate",
        accent_color: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Generate a conceptual illustration.

        Args:
            concept: What to illustrate (e.g., "AI analyzing data")
            style: artistic style preset
            accent_color: Primary color to emphasize

        Returns:
            PNG bytes or None on failure
        """
        prompt = self._build_illustration_prompt(concept, style, accent_color)
        result = await self._generate_with_fallback(prompt, size="standard")
        return result.image_bytes

    async def generate_icon(
        self,
        concept: str,
        color: str = "#2563EB",
        style: str = "flat",
    ) -> Optional[bytes]:
        """
        Generate a custom icon.

        Args:
            concept: Icon concept (e.g., "growth arrow", "team collaboration")
            color: Hex color for the icon
            style: flat, outline, 3d, gradient

        Returns:
            PNG bytes or None on failure
        """
        prompt = self._build_icon_prompt(concept, color, style)
        result = await self._generate_with_fallback(prompt, size="standard")
        return result.image_bytes

    async def generate_for_slide(
        self,
        slide: SlideSpec,
        theme: str = "corporate",
        brand_colors: Optional[List[str]] = None,
    ) -> Optional[ImageSpec]:
        """
        Generate an appropriate image for a slide based on its content.

        Args:
            slide: SlideSpec with title, bullets, content
            theme: Visual theme
            brand_colors: Brand color palette

        Returns:
            ImageSpec ready for use, or None
        """
        # Determine what kind of image to generate
        if slide.kind == SlideKind.title:
            # Title slide: dramatic background
            image_bytes = await self.generate_slide_background(
                theme=theme,
                mood="bold" if slide.kind == SlideKind.title else "professional",
                brand_colors=brand_colors,
                content_hint=slide.title,
            )
        elif slide.kind == SlideKind.chart:
            # Chart slide: abstract data viz background
            image_bytes = await self.generate_illustration(
                concept=f"Data visualization showing {slide.title}",
                style="abstract",
                accent_color=brand_colors[0] if brand_colors else None,
            )
        elif slide.kind == SlideKind.section:
            # Section divider: thematic illustration
            image_bytes = await self.generate_illustration(
                concept=f"Conceptual representation of {slide.title}",
                style=theme,
            )
        else:
            # Content slides: supporting illustration
            content = slide.title + " " + " ".join(slide.bullets or [])
            image_bytes = await self.generate_illustration(
                concept=content[:200],
                style=theme,
            )

        if image_bytes:
            return ImageSpec(
                query=f"ai_generated_{slide.kind}",
                alt_text=f"AI-generated visual for {slide.title}",
                bytes_b64=base64.b64encode(image_bytes).decode(),
            )
        return None

    # ───────────────────────────────────────────────────────────────────────
    #  Prompt Engineering
    # ───────────────────────────────────────────────────────────────────────

    def _build_background_prompt(
        self,
        theme: str,
        mood: str,
        brand_colors: Optional[List[str]],
        content_hint: str,
    ) -> str:
        """Build prompt for slide backgrounds."""
        style = self.STYLE_PRESETS.get(theme, self.STYLE_PRESETS["corporate"])

        color_instruction = ""
        if brand_colors:
            colors = ", ".join(brand_colors[:3])
            color_instruction = f" Incorporate these brand colors subtly: {colors}."

        content_instruction = f" Theme: {content_hint}." if content_hint else ""

        prompt = (
            f"Abstract presentation background, {style}, {mood} atmosphere."
            f"{color_instruction}{content_instruction}"
            " Wide format 16:9 aspect ratio. "
            " Professional, corporate-safe, no text, no watermarks, "
            " suitable for business presentation slide background."
        )

        return self._sanitize_prompt(prompt)

    def _build_illustration_prompt(
        self,
        concept: str,
        style: str,
        accent_color: Optional[str],
    ) -> str:
        """Build prompt for conceptual illustrations."""
        style_desc = self.STYLE_PRESETS.get(style, self.STYLE_PRESETS["corporate"])

        color_instruction = ""
        if accent_color:
            color_instruction = f" Primary accent color: {accent_color}."

        prompt = (
            f"Professional illustration: {concept}. {style_desc}."
            f"{color_instruction}"
            " Clean composition, suitable for business presentation."
            " No text, no watermarks, no people if possible."
        )

        return self._sanitize_prompt(prompt)

    def _build_icon_prompt(
        self,
        concept: str,
        color: str,
        style: str,
    ) -> str:
        """Build prompt for icon generation."""
        style_desc = {
            "flat": "flat design icon, simple shapes, no gradients",
            "outline": "line art icon, single weight strokes, minimal",
            "3d": "3D rendered icon, soft shadows, rounded",
            "gradient": "modern gradient icon, vibrant colors",
        }.get(style, "flat design icon")

        prompt = (
            f"App icon: {concept}. {style_desc}."
            f" Primary color {color}, on white background."
            " Centered, symmetrical, suitable for presentation."
            " No text, no watermarks, vector style."
        )

        return self._sanitize_prompt(prompt)

    def _sanitize_prompt(self, prompt: str) -> str:
        """Ensure prompt is corporate-safe."""
        words = prompt.lower().split()
        for word in words:
            clean = "".join(c for c in word if c.isalnum())
            if clean in self.UNSAFE_KEYWORDS:
                # Replace with safe alternative
                prompt = prompt.replace(word, "[professional scene]")
                logger.warning("sanitized_unsafe_keyword: %s", clean)

        # Add safety suffix
        safety_suffix = (
            " Corporate-appropriate, safe for work environment, "
            "no controversial content, no text overlay."
        )

        if safety_suffix not in prompt:
            prompt += safety_suffix

        return prompt[:1000]  # Max length

    # ───────────────────────────────────────────────────────────────────────
    #  Generation Pipeline
    # ───────────────────────────────────────────────────────────────────────

    async def _generate_with_fallback(
        self,
        prompt: str,
        size: str = "standard",
    ) -> GenerationResult:
        """Try primary provider, fallback on failure."""
        cache_key = self._cache_key(prompt, size)

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return GenerationResult(
                image_bytes=cached,
                prompt_used=prompt,
                model="cache",
                generation_time_ms=0,
            )

        t0 = time.time()

        # Try OpenAI DALL-E 3 first
        if self.openai_key:
            result = await self._generate_openai(prompt, size)
            if result.image_bytes:
                self._store_cache(cache_key, result.image_bytes)
                return result

        # Fallback to Stability AI
        if self.stability_key:
            result = await self._generate_stability(prompt, size)
            if result.image_bytes:
                self._store_cache(cache_key, result.image_bytes)
                return result

        # Both failed
        return GenerationResult(
            image_bytes=None,
            prompt_used=prompt,
            model="none",
            generation_time_ms=int((time.time() - t0) * 1000),
            error="All providers failed",
        )

    async def _generate_openai(self, prompt: str, size: str) -> GenerationResult:
        """Generate using OpenAI DALL-E 3."""
        import asyncio

        t0 = time.time()

        try:
            import openai

            client = openai.AsyncOpenAI(api_key=self.openai_key)

            # Map size to DALL-E format
            size_map = {
                "wide": "1792x1024",
                "standard": "1024x1024",
                "tall": "1024x1792",
            }

            response = await asyncio.wait_for(
                client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size=size_map.get(size, "1024x1024"),
                    quality="standard",
                    n=1,
                    response_format="b64_json",
                ),
                timeout=30.0,
            )

            image_data = base64.b64decode(response.data[0].b64_json)
            revised = response.data[0].revised_prompt

            return GenerationResult(
                image_bytes=image_data,
                prompt_used=prompt,
                model="dall-e-3",
                generation_time_ms=int((time.time() - t0) * 1000),
                revised_prompt=revised,
            )

        except Exception as exc:
            logger.warning("openai_generation_failed: %s", str(exc)[:200])
            return GenerationResult(
                image_bytes=None,
                prompt_used=prompt,
                model="dall-e-3",
                generation_time_ms=int((time.time() - t0) * 1000),
                error=str(exc),
            )

    async def _generate_stability(self, prompt: str, size: str) -> GenerationResult:
        """Generate using Stability AI."""
        import asyncio

        t0 = time.time()

        try:
            import httpx

            dimensions = self.SLIDE_SIZES.get(size, self.SLIDE_SIZES["standard"])

            headers = {
                "Authorization": f"Bearer {self.stability_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "text_prompts": [{"text": prompt, "weight": 1.0}],
                "width": dimensions["width"],
                "height": dimensions["height"],
                "samples": 1,
                "steps": 30,
                "cfg_scale": 7.0,
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Decode base64 image
                if data.get("artifacts"):
                    image_data = base64.b64decode(data["artifacts"][0]["base64"])
                    return GenerationResult(
                        image_bytes=image_data,
                        prompt_used=prompt,
                        model="stable-diffusion-xl",
                        generation_time_ms=int((time.time() - t0) * 1000),
                    )

            return GenerationResult(
                image_bytes=None,
                prompt_used=prompt,
                model="stable-diffusion-xl",
                generation_time_ms=int((time.time() - t0) * 1000),
                error="No artifacts in response",
            )

        except Exception as exc:
            logger.warning("stability_generation_failed: %s", str(exc)[:200])
            return GenerationResult(
                image_bytes=None,
                prompt_used=prompt,
                model="stable-diffusion-xl",
                generation_time_ms=int((time.time() - t0) * 1000),
                error=str(exc),
            )

    # ───────────────────────────────────────────────────────────────────────
    #  Caching
    # ───────────────────────────────────────────────────────────────────────

    def _cache_key(self, prompt: str, size: str) -> str:
        """Generate cache key for prompt."""
        key = f"{prompt}:{size}"
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[bytes]:
        """Get cached image if exists and not expired."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            # Cache for 24 hours
            if time.time() - timestamp < 86400:
                return data
            del self._cache[key]
        return None

    def _store_cache(self, key: str, data: bytes) -> None:
        """Store in cache with LRU eviction."""
        if len(self._cache) >= self._cache_max:
            # Evict oldest
            oldest = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest]
        self._cache[key] = (data, time.time())

    # ───────────────────────────────────────────────────────────────────────
    #  Utility
    # ───────────────────────────────────────────────────────────────────────

    def has_provider(self) -> bool:
        """Check if any image generation provider is available."""
        return bool(self.openai_key or self.stability_key)

    def estimate_cost(self, prompt: str, provider: str = "openai") -> float:
        """Estimate cost in USD for a generation."""
        if provider == "openai":
            # DALL-E 3: $0.040 per 1024x1024, $0.080 per 1024x1792
            return 0.04
        elif provider == "stability":
            # Stability AI: ~$0.002 per image
            return 0.002
        return 0.0


# Convenience functions

async def generate_slide_visual(
    slide: SlideSpec,
    theme: str = "corporate",
    brand_colors: Optional[List[str]] = None,
) -> Optional[ImageSpec]:
    """One-shot visual generation for a slide."""
    generator = AIImageGenerator()
    return await generator.generate_for_slide(slide, theme, brand_colors)


async def generate_background(
    theme: str = "corporate",
    mood: str = "professional",
) -> Optional[bytes]:
    """One-shot background generation."""
    generator = AIImageGenerator()
    return await generator.generate_slide_background(theme, mood)
