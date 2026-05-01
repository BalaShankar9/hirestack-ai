"""
PPT schemas — Pydantic models that flow from the LLM planner into the
deterministic composer.

Design notes:
- DeckSpec is fully self-describing — given one, SlideComposer can produce
  a .pptx without any additional context.
- ChartSpec.kind is an open string with a recommended enum (ChartKind) — new
  renderers can be added without breaking existing decks.
- ImageSpec carries either a remote URL (P3 fetcher resolves to bytes) OR a
  pre-fetched bytes blob — keeps the composer offline-testable.
- All fields have sensible defaults so the LLM planner can omit visuals and
  still produce a valid deck.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SlideKind(str, Enum):
    """Layout family for a slide. Composer picks a python-pptx layout from this."""

    title = "title"            # cover slide: big title + subtitle
    section = "section"        # divider: section header + accent bar
    content = "content"        # standard: title + bullet list
    two_column = "two_column"  # title + two bullet columns (compare/contrast)
    quote = "quote"            # large pull-quote with attribution
    chart = "chart"            # title + chart (optional caption)
    image = "image"            # title + full-bleed image (optional caption)
    image_text = "image_text"  # half image / half bullets
    closing = "closing"        # thank-you / CTA / contact


class ChartKind(str, Enum):
    """The chart galaxy. Renderer chooses matplotlib backend per kind."""

    line = "line"
    area = "area"
    bar = "bar"
    column = "column"
    stacked_bar = "stacked_bar"
    scatter = "scatter"
    bubble = "bubble"
    pie = "pie"
    donut = "donut"
    histogram = "histogram"
    box = "box"
    heatmap = "heatmap"
    waterfall = "waterfall"
    radar = "radar"
    funnel = "funnel"


class ChartSpec(BaseModel):
    """Data + style for a single chart. Renderer turns this into a PNG."""

    model_config = ConfigDict(extra="ignore")

    kind: str = Field(..., description="ChartKind value or any registered renderer key.")
    title: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    # Series: each entry is {"name": str, "data": list[number] | list[[x,y]]}
    series: List[Dict[str, Any]] = Field(default_factory=list)
    # Categorical labels for x-axis (bar/column/stacked/heatmap rows etc.)
    categories: List[str] = Field(default_factory=list)
    # Optional matrix payload for heatmaps: list[list[float]]
    matrix: Optional[List[List[float]]] = None
    # Free-form annotations (peaks/valleys/highlights) — renderer best-effort.
    annotations: List[Dict[str, Any]] = Field(default_factory=list)


class ImageSpec(BaseModel):
    """Image source for a slide. Composer resolves URL → bytes if needed."""

    model_config = ConfigDict(extra="ignore")

    query: Optional[str] = Field(None, description="Semantic search query for stock-photo lookup.")
    url: Optional[str] = Field(None, description="Pre-resolved image URL.")
    alt_text: Optional[str] = Field(None, description="Accessibility caption.")
    credit: Optional[str] = Field(None, description="Photographer / source attribution.")
    # Caller may inject pre-fetched bytes to keep composer offline-deterministic.
    bytes_b64: Optional[str] = None


class SlideSpec(BaseModel):
    """A single slide's full intent. Composer renders this deterministically."""

    model_config = ConfigDict(extra="ignore")

    kind: SlideKind = SlideKind.content
    title: str = ""
    subtitle: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)
    bullets_right: List[str] = Field(default_factory=list)  # used by two_column
    body: Optional[str] = None        # used by quote / closing
    attribution: Optional[str] = None  # used by quote
    notes: Optional[str] = None       # speaker notes
    chart: Optional[ChartSpec] = None
    image: Optional[ImageSpec] = None
    caption: Optional[str] = None     # caption under chart/image


class DeckSpec(BaseModel):
    """A full presentation. Self-contained — composer needs nothing else."""

    model_config = ConfigDict(extra="ignore")

    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    audience: Optional[str] = None
    theme: str = Field("modern", description="Theme key — composer maps to colors/fonts.")
    accent_color: Optional[str] = Field(None, description="#RRGGBB override; else theme default.")
    slides: List[SlideSpec] = Field(default_factory=list)

    @property
    def slide_count(self) -> int:
        return len(self.slides)
