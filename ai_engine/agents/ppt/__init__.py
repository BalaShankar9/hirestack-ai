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
    TableSpec,
    SlideKind,
    ChartKind,
)
from ai_engine.agents.ppt.outline_planner import OutlinePlanner
from ai_engine.agents.ppt.slide_composer import SlideComposer

# Orchestrator (Production-grade with pipeline architecture)
try:
    from ai_engine.agents.ppt.orchestrator import (
        PresentationOrchestrator,
        GenerationResult,
        GenerationStatus,
        GenerationProgress,
        CircuitBreaker,
        PPTOrchestrator,  # Backward compatibility alias
        PPTResult,          # Backward compatibility alias
    )
except Exception as exc:  # noqa: BLE001
    logger.warning("orchestrator_unavailable: %s", exc)
    PresentationOrchestrator = None  # type: ignore[misc,assignment]
    GenerationResult = None  # type: ignore[misc,assignment]
    GenerationStatus = None  # type: ignore[misc,assignment]
    GenerationProgress = None  # type: ignore[misc,assignment]
    CircuitBreaker = None  # type: ignore[misc,assignment]
    PPTOrchestrator = None  # type: ignore[misc,assignment]
    PPTResult = None  # type: ignore[misc,assignment]

# Optional engines — guarded so the package is importable even if matplotlib
# (P2) or httpx-based image clients (P3) are unavailable.
try:
    from ai_engine.agents.ppt.chart_renderer import ChartRenderer, ChartSelector
except Exception as exc:  # noqa: BLE001
    logger.warning("ppt_chart_renderer_unavailable: %s", exc)
    ChartRenderer = None  # type: ignore[misc,assignment]
    ChartSelector = None  # type: ignore[misc,assignment]

try:
    from ai_engine.agents.ppt.image_fetcher import ImageFetcher
except Exception as exc:  # noqa: BLE001
    logger.warning("ppt_image_resolver_unavailable: %s", exc)
    ImageFetcher = None  # type: ignore[misc,assignment]

# Phase 1: Native chart renderer
try:
    from ai_engine.agents.ppt.native_chart_renderer import NativeChartRenderer
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_native_chart_renderer_unavailable: %s", exc)
    NativeChartRenderer = None  # type: ignore[misc,assignment]

# Phase 2: Template & Brand System
try:
    from ai_engine.agents.ppt.template_loader import TemplateLoader, BrandKit
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_template_loader_unavailable: %s", exc)
    TemplateLoader = None  # type: ignore[misc,assignment]
    BrandKit = None  # type: ignore[misc,assignment]

# Phase 3: Data Research
try:
    from ai_engine.agents.ppt.data_researcher import DataResearcher
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_data_researcher_unavailable: %s", exc)
    DataResearcher = None  # type: ignore[misc,assignment]

# Phase 5: Icons
try:
    from ai_engine.agents.ppt.icon_library import IconLibrary
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_icon_library_unavailable: %s", exc)
    IconLibrary = None  # type: ignore[misc,assignment]

# Phase 6: SmartArt
try:
    from ai_engine.agents.ppt.smartart_renderer import SmartArtRenderer
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_smartart_renderer_unavailable: %s", exc)
    SmartArtRenderer = None  # type: ignore[misc,assignment]

# Phase 7: Polish
try:
    from ai_engine.agents.ppt.polish_engine import PolishEngine
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_polish_engine_unavailable: %s", exc)
    PolishEngine = None  # type: ignore[misc,assignment]

# Phase 8: Quality Validation
try:
    from ai_engine.agents.ppt.quality_validator import QualityValidator
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_quality_validator_unavailable: %s", exc)
    QualityValidator = None  # type: ignore[misc,assignment]

# Phase 9: AI Image Generation
try:
    from ai_engine.agents.ppt.ai_image_generator import AIImageGenerator
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_ai_image_generator_unavailable: %s", exc)
    AIImageGenerator = None  # type: ignore[misc,assignment]

# Phase 10: Content Enhancement
try:
    from ai_engine.agents.ppt.content_enhancer import ContentEnhancer
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_content_enhancer_unavailable: %s", exc)
    ContentEnhancer = None  # type: ignore[misc,assignment]

# Phase 11: Interactive Elements
try:
    from ai_engine.agents.ppt.interactive_builder import InteractiveBuilder
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_interactive_builder_unavailable: %s", exc)
    InteractiveBuilder = None  # type: ignore[misc,assignment]

# Phase 12: i18n
try:
    from ai_engine.agents.ppt.i18n_engine import I18nEngine
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_i18n_engine_unavailable: %s", exc)
    I18nEngine = None  # type: ignore[misc,assignment]

# Phase 12: Export
try:
    from ai_engine.agents.ppt.export_manager import ExportManager
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_export_manager_unavailable: %s", exc)
    ExportManager = None  # type: ignore[misc,assignment]

# Phase 12: Analytics
try:
    from ai_engine.agents.ppt.analytics_tracker import AnalyticsTracker
except Exception as exc:  # noqa: BLE001
    logger.debug("ppt_analytics_tracker_unavailable: %s", exc)
    AnalyticsTracker = None  # type: ignore[misc,assignment]

# Integration helpers — tool registry, intent detection, storage shim.
from ai_engine.agents.ppt.integration import (
    build_ppt_tools,
    detect_ppt_intent,
    generate_and_store_pptx,
)

__all__ = [
    # Schemas
    "DeckSpec",
    "SlideSpec",
    "ChartSpec",
    "ImageSpec",
    "TableSpec",
    "SlideKind",
    "ChartKind",
    # Core
    "OutlinePlanner",
    "SlideComposer",
    # Orchestrator (Production-grade Pipeline)
    "PresentationOrchestrator",
    "GenerationResult",
    "GenerationStatus",
    "GenerationProgress",
    "CircuitBreaker",
    "PPTOrchestrator",  # Backward compatibility
    "PPTResult",        # Backward compatibility
    # Renderers
    "ChartRenderer",
    "ChartSelector",
    "NativeChartRenderer",
    "ImageFetcher",
    # Phase 1-8
    "TemplateLoader",
    "BrandKit",
    "DataResearcher",
    "IconLibrary",
    "SmartArtRenderer",
    "PolishEngine",
    "QualityValidator",
    # Phase 9-12
    "AIImageGenerator",
    "ContentEnhancer",
    "InteractiveBuilder",
    "I18nEngine",
    "ExportManager",
    "AnalyticsTracker",
    # Integration
    "build_ppt_tools",
    "detect_ppt_intent",
    "generate_and_store_pptx",
]
