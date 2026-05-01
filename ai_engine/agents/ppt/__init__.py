"""
HireStack AI — Elite PPT Generation Package.

Public API:
    PPTOrchestrator: top-level "topic + audience -> .pptx bytes" generator.
    DeckSpec, SlideSpec, ChartSpec, ImageSpec: structured deck schemas.
    OutlinePlanner: LLM-driven deck outline generator (testable in isolation).
    SlideComposer: deterministic .pptx assembler from a DeckSpec.

Optional engines (P2/P3 layers):
    ChartRenderer: matplotlib renderer for the 15+ chart galaxy.
    ImageFetcher: stock-image search (Unsplash/Pexels) with offline fallback.

Everything is import-safe even when optional API keys (Unsplash/Pexels) are
missing — the package degrades gracefully to text-only or icon-only slides.
"""
from ai_engine.agents.ppt.schemas import (
    DeckSpec,
    SlideSpec,
    ChartSpec,
    ImageSpec,
    SlideKind,
    ChartKind,
)
from ai_engine.agents.ppt.outline_planner import OutlinePlanner
from ai_engine.agents.ppt.slide_composer import SlideComposer
from ai_engine.agents.ppt.ppt_orchestrator import PPTOrchestrator

__all__ = [
    "DeckSpec",
    "SlideSpec",
    "ChartSpec",
    "ImageSpec",
    "SlideKind",
    "ChartKind",
    "OutlinePlanner",
    "SlideComposer",
    "PPTOrchestrator",
]
