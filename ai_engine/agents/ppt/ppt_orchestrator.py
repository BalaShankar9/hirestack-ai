"""
PPTOrchestrator — top-level "topic → .pptx bytes" entrypoint.

Pipeline:
    OutlinePlanner.plan(topic, audience, ...) -> DeckSpec
    SlideComposer.compose(deck) -> .pptx bytes

Designed so that:
- The endpoint layer (backend/app/api/routes/ppt.py) only sees this class.
- The pipeline orchestrator (ai_engine/agents/orchestrator.py) can call it
  as a tool when the user's intent is "make me a deck".
- ChartRenderer / ImageResolver are pluggable so P2/P3 layers can extend it
  without modifying this orchestrator.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from ai_engine.agents.ppt.outline_planner import OutlinePlanner
from ai_engine.agents.ppt.schemas import DeckSpec
from ai_engine.agents.ppt.slide_composer import SlideComposer

logger = logging.getLogger(__name__)


@dataclass
class PPTResult:
    """Container for a generated deck."""

    pptx_bytes: bytes
    deck: DeckSpec
    latency_ms: int

    @property
    def slide_count(self) -> int:
        return self.deck.slide_count

    @property
    def size_bytes(self) -> int:
        return len(self.pptx_bytes)


class PPTOrchestrator:
    """Top-level PPT generation orchestrator."""

    def __init__(
        self,
        *,
        ai_client: Optional[object] = None,
        chart_renderer: Optional[object] = None,
        image_resolver: Optional[object] = None,
    ) -> None:
        # Default to the matplotlib chart galaxy if no renderer was provided.
        # We import lazily so a missing matplotlib install (optional dep) doesn't
        # break the planner-only / text-only code paths.
        if chart_renderer is None:
            try:
                from ai_engine.agents.ppt.chart_renderer import ChartRenderer
                chart_renderer = ChartRenderer()
            except Exception as exc:  # noqa: BLE001
                logger.warning("ppt_chart_renderer_unavailable: %s", exc)
                chart_renderer = None
        self.planner = OutlinePlanner(ai_client=ai_client)
        self.composer = SlideComposer(
            chart_renderer=chart_renderer,
            image_resolver=image_resolver,
        )

    async def generate(
        self,
        *,
        topic: str,
        audience: Optional[str] = None,
        slide_count: int = 10,
        tone: Optional[str] = None,
        theme: str = "modern",
        extra_context: Optional[str] = None,
    ) -> PPTResult:
        """Generate a presentation from a topic prompt."""
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")

        t0 = time.monotonic()
        deck = await self.planner.plan(
            topic=topic.strip(),
            audience=audience,
            slide_count=slide_count,
            tone=tone,
            theme=theme,
            extra_context=extra_context,
        )
        pptx_bytes = await self.composer.compose(deck)
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "ppt_generated: topic=%s slides=%d size=%dKB latency_ms=%d",
            topic[:80], deck.slide_count, len(pptx_bytes) // 1024, latency_ms,
        )
        return PPTResult(pptx_bytes=pptx_bytes, deck=deck, latency_ms=latency_ms)

    async def generate_from_deck(self, deck: DeckSpec) -> PPTResult:
        """Render an already-planned DeckSpec straight to .pptx bytes."""
        t0 = time.monotonic()
        pptx_bytes = await self.composer.compose(deck)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return PPTResult(pptx_bytes=pptx_bytes, deck=deck, latency_ms=latency_ms)
