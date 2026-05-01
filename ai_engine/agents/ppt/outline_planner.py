"""
OutlinePlanner — turns (topic, audience, slide_count, ...) into a DeckSpec.

Strategy:
1. Build a single LLM prompt asking for a STRICT JSON deck outline.
2. Use AIClient.complete_json with a JSON schema for validation.
3. Defensively coerce the JSON into our pydantic DeckSpec.
4. If the LLM is unavailable (e.g. unit-test environment with no API key),
   produce a deterministic stub deck so callers can still smoke-test the
   composer end-to-end. Production should never hit this fallback.

The planner is intentionally self-contained — no SubAgent dependencies — so
it can be unit-tested against a fake AIClient.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ai_engine.agents.ppt.schemas import (
    ChartSpec,
    DeckSpec,
    ImageSpec,
    SlideKind,
    SlideSpec,
)

logger = logging.getLogger(__name__)


_OUTLINE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["title", "slides"],
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "theme": {"type": "string"},
        "accent_color": {"type": "string"},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["kind", "title"],
                "properties": {
                    "kind": {"type": "string"},
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                    "bullets_right": {"type": "array", "items": {"type": "string"}},
                    "body": {"type": "string"},
                    "attribution": {"type": "string"},
                    "notes": {"type": "string"},
                    "caption": {"type": "string"},
                    "chart": {"type": "object"},
                    "image": {"type": "object"},
                },
            },
        },
    },
}


_SYSTEM_PROMPT = (
    "You are an elite presentation designer. Produce structured JSON for a "
    "professional, narrative-driven deck. Rules:\n"
    " - First slide: kind='title' with a punchy title and one-line subtitle.\n"
    " - Last slide: kind='closing' with a clear call to action.\n"
    " - Mix slide kinds: section, content, two_column, quote, chart, image, image_text.\n"
    " - Use ≤6 bullets per slide; each bullet ≤120 chars; punchy, no fluff.\n"
    " - When data is implied (metrics, trends, market share, comparisons), include "
    "a chart slide with a populated chart object.\n"
    " - For chart objects: kind ∈ "
    "{line,area,bar,column,stacked_bar,scatter,bubble,pie,donut,histogram,box,heatmap,waterfall,radar,funnel}, "
    "include series=[{name, data:[number,...]}] and (when applicable) categories=[label,...].\n"
    " - For image slides: include image.query (semantic search phrase) and alt_text.\n"
    " - Provide concise speaker notes for every slide.\n"
    " - Output JSON only — no prose, no markdown fences."
)


class OutlinePlanner:
    """LLM-driven deck planner producing a validated DeckSpec."""

    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self.ai_client = ai_client  # lazy-loaded to keep imports cheap

    def _get_client(self) -> Any:
        if self.ai_client is not None:
            return self.ai_client
        from ai_engine.client import get_ai_client
        return get_ai_client()

    async def plan(
        self,
        *,
        topic: str,
        audience: Optional[str] = None,
        slide_count: int = 10,
        tone: Optional[str] = None,
        theme: str = "modern",
        extra_context: Optional[str] = None,
    ) -> DeckSpec:
        """Generate a DeckSpec for the given topic."""
        slide_count = max(3, min(int(slide_count or 10), 30))
        prompt_lines: List[str] = [
            f"Topic: {topic}",
            f"Target slide count: {slide_count}",
        ]
        if audience:
            prompt_lines.append(f"Audience: {audience}")
        if tone:
            prompt_lines.append(f"Tone: {tone}")
        if extra_context:
            prompt_lines.append(f"Extra context:\n{extra_context}")
        prompt_lines.append(
            "\nReturn a JSON object matching this rough shape: "
            '{"title": str, "subtitle": str, "theme": str, "accent_color": "#RRGGBB", '
            '"slides": [SlideSpec, ...]}. Aim for exactly the requested slide count.'
        )
        prompt = "\n".join(prompt_lines)

        try:
            client = self._get_client()
            payload = await client.complete_json(
                prompt=prompt,
                system=_SYSTEM_PROMPT,
                schema=_OUTLINE_SCHEMA,
                temperature=0.6,
                task_type="ppt_outline",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ppt_outline_llm_failed: %s — using deterministic stub", str(exc)[:200])
            payload = self._stub_payload(topic=topic, audience=audience, slide_count=slide_count)

        return self._coerce(payload, theme=theme, audience=audience)

    # ────────────────────────────────────────────────────────────────────
    #  Coercion: defensive payload → DeckSpec mapping
    # ────────────────────────────────────────────────────────────────────

    def _coerce(self, payload: Any, *, theme: str, audience: Optional[str]) -> DeckSpec:
        if not isinstance(payload, dict):
            payload = {"title": "Untitled", "slides": []}
        slides_raw = payload.get("slides") or []
        slides: List[SlideSpec] = []
        for raw in slides_raw:
            if not isinstance(raw, dict):
                continue
            slides.append(self._coerce_slide(raw))
        if not slides:
            slides = [SlideSpec(kind=SlideKind.title, title=str(payload.get("title", "Untitled")))]
        return DeckSpec(
            title=str(payload.get("title") or "Untitled"),
            subtitle=payload.get("subtitle"),
            theme=str(payload.get("theme") or theme),
            accent_color=payload.get("accent_color"),
            audience=audience,
            slides=slides,
        )

    def _coerce_slide(self, raw: Dict[str, Any]) -> SlideSpec:
        kind_raw = str(raw.get("kind") or "content").lower().strip()
        try:
            kind = SlideKind(kind_raw)
        except ValueError:
            kind = SlideKind.content

        chart_raw = raw.get("chart")
        chart_spec: Optional[ChartSpec] = None
        if isinstance(chart_raw, dict) and chart_raw.get("kind"):
            try:
                chart_spec = ChartSpec.model_validate(chart_raw)
            except Exception as exc:  # noqa: BLE001
                logger.debug("ppt_chart_coerce_failed: %s", str(exc)[:200])

        image_raw = raw.get("image")
        image_spec: Optional[ImageSpec] = None
        if isinstance(image_raw, dict) and (image_raw.get("query") or image_raw.get("url")):
            try:
                image_spec = ImageSpec.model_validate(image_raw)
            except Exception as exc:  # noqa: BLE001
                logger.debug("ppt_image_coerce_failed: %s", str(exc)[:200])

        bullets = [str(b) for b in (raw.get("bullets") or []) if b]
        bullets_right = [str(b) for b in (raw.get("bullets_right") or []) if b]

        return SlideSpec(
            kind=kind,
            title=str(raw.get("title") or "")[:200],
            subtitle=raw.get("subtitle"),
            bullets=bullets[:8],
            bullets_right=bullets_right[:8],
            body=raw.get("body"),
            attribution=raw.get("attribution"),
            notes=raw.get("notes"),
            chart=chart_spec,
            image=image_spec,
            caption=raw.get("caption"),
        )

    # ────────────────────────────────────────────────────────────────────
    #  Deterministic stub (used when LLM unavailable)
    # ────────────────────────────────────────────────────────────────────

    def _stub_payload(
        self, *, topic: str, audience: Optional[str], slide_count: int,
    ) -> Dict[str, Any]:
        slides: List[Dict[str, Any]] = [
            {
                "kind": "title",
                "title": topic,
                "subtitle": f"For {audience}" if audience else "An overview",
                "notes": "Cover slide.",
            }
        ]
        for i in range(1, slide_count - 1):
            slides.append({
                "kind": "content",
                "title": f"{topic} — section {i}",
                "bullets": [
                    f"Key point {i}.1",
                    f"Key point {i}.2",
                    f"Key point {i}.3",
                ],
                "notes": f"Speaker notes for section {i}.",
            })
        slides.append({
            "kind": "closing",
            "title": "Thank you",
            "body": "Questions?",
            "notes": "Closing slide.",
        })
        return {"title": topic, "subtitle": audience, "slides": slides}
