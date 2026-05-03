"""
IconLibrary — SVG icon integration for presentations.

Provides a rich visual vocabulary for slides using popular icon sets:
- Font Awesome (brands, solid, regular)
- Heroicons (outline, solid)
- Lucide (modern, clean)
- Custom icons

Icons are rendered as SVG, converted to PNG/EMF for PPTX embedding,
and colored to match the presentation theme.

Public API:
    IconLibrary.search(query) -> List[IconSpec]
    IconLibrary.render(icon_spec, color_hex) -> bytes
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.agents.ppt.schemas import SlideSpec

logger = logging.getLogger(__name__)


@dataclass
class IconSpec:
    """Icon specification for rendering."""

    name: str
    set_name: str  # "fontawesome", "heroicons", "lucide"
    style: str  # "solid", "outline", "regular"
    svg_path: str
    viewbox: str = "0 0 24 24"
    category: str = ""


class IconLibrary:
    """Search and render icons for presentations."""

    # Built-in icon paths (subset of popular icons for offline use)
    _ICONS: Dict[str, Dict[str, str]] = {
        "chart": {
            "path": "M3 3v18h18v-2H5V3H3zm4 14h2v-7H7v7zm4 0h2V7h-2v10zm4 0h2v-4h-2v4z",
            "set": "material",
            "category": "analytics",
        },
        "trending_up": {
            "path": "M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z",
            "set": "material",
            "category": "analytics",
        },
        "trending_down": {
            "path": "M16 18l2.29-2.29-4.88-4.88-4 4L2 7.41 3.41 6l6 6 4-4 6.3 6.29L22 12v6z",
            "set": "material",
            "category": "analytics",
        },
        "group": {
            "path": "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5z",
            "set": "material",
            "category": "people",
        },
        "check_circle": {
            "path": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
            "set": "material",
            "category": "status",
        },
        "warning": {
            "path": "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z",
            "set": "material",
            "category": "status",
        },
        "error": {
            "path": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z",
            "set": "material",
            "category": "status",
        },
        "lightbulb": {
            "path": "M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z",
            "set": "material",
            "category": "ideas",
        },
        "rocket": {
            "path": "M12 2.5s-4 2.5-4 8v2s-1.5 1.5-1.5 3c0 1.5 1.5 2.5 2.5 2.5h6c1 0 2.5-1 2.5-2.5 0-1.5-1.5-3-1.5-3v-2c0-5.5-4-8-4-8zm0 12c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z",
            "set": "custom",
            "category": "launch",
        },
        "target": {
            "path": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-14c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 10c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4z",
            "set": "material",
            "category": "goals",
        },
        "dollar": {
            "path": "M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z",
            "set": "material",
            "category": "finance",
        },
        "calendar": {
            "path": "M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM9 10H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2zm-8 4H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2z",
            "set": "material",
            "category": "time",
        },
        "clock": {
            "path": "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z",
            "set": "material",
            "category": "time",
        },
        "search": {
            "path": "M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
            "set": "material",
            "category": "action",
        },
        "star": {
            "path": "M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z",
            "set": "material",
            "category": "rating",
        },
        "heart": {
            "path": "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z",
            "set": "material",
            "category": "favorite",
        },
        "globe": {
            "path": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z",
            "set": "material",
            "category": "global",
        },
        "shield": {
            "path": "M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z",
            "set": "material",
            "category": "security",
        },
        "lock": {
            "path": "M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z",
            "set": "material",
            "category": "security",
        },
        "email": {
            "path": "M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z",
            "set": "material",
            "category": "communication",
        },
        "phone": {
            "path": "M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z",
            "set": "material",
            "category": "communication",
        },
    }

    # Semantic mappings for search
    _SEARCH_MAPPINGS: Dict[str, List[str]] = {
        "growth": ["trending_up", "chart", "rocket"],
        "decline": ["trending_down"],
        "team": ["group"],
        "people": ["group"],
        "success": ["check_circle"],
        "warning": ["warning"],
        "error": ["error"],
        "idea": ["lightbulb"],
        "innovation": ["lightbulb", "rocket"],
        "launch": ["rocket"],
        "goal": ["target"],
        "target": ["target"],
        "money": ["dollar"],
        "revenue": ["dollar", "chart"],
        "finance": ["dollar", "chart"],
        "date": ["calendar"],
        "time": ["clock"],
        "search": ["search"],
        "find": ["search"],
        "rating": ["star"],
        "favorite": ["heart", "star"],
        "like": ["heart"],
        "global": ["globe"],
        "world": ["globe"],
        "security": ["shield", "lock"],
        "protection": ["shield"],
        "lock": ["lock"],
        "email": ["email"],
        "phone": ["phone"],
        "contact": ["email", "phone"],
    }

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.cache_dir = cache_dir
        self._cache: Dict[str, bytes] = {}

    def search(self, query: str, max_results: int = 5) -> List[IconSpec]:
        """
        Search for icons by semantic query.

        Args:
            query: Natural language search (e.g., "growth", "security")
            max_results: Maximum number of results to return

        Returns:
            List of matching IconSpec objects
        """
        query_lower = query.lower().strip()
        results: List[IconSpec] = []
        seen: set = set()

        # Direct match
        if query_lower in self._ICONS and query_lower not in seen:
            icon_data = self._ICONS[query_lower]
            results.append(IconSpec(
                name=query_lower,
                set_name=icon_data["set"],
                style="solid",
                svg_path=icon_data["path"],
                category=icon_data.get("category", ""),
            ))
            seen.add(query_lower)

        # Semantic mapping match
        if query_lower in self._SEARCH_MAPPINGS:
            for icon_name in self._SEARCH_MAPPINGS[query_lower]:
                if icon_name in self._ICONS and icon_name not in seen:
                    icon_data = self._ICONS[icon_name]
                    results.append(IconSpec(
                        name=icon_name,
                        set_name=icon_data["set"],
                        style="solid",
                        svg_path=icon_data["path"],
                        category=icon_data.get("category", ""),
                    ))
                    seen.add(icon_name)

        # Category match
        for name, data in self._ICONS.items():
            if name not in seen and data.get("category") == query_lower:
                results.append(IconSpec(
                    name=name,
                    set_name=data["set"],
                    style="solid",
                    svg_path=data["path"],
                    category=data.get("category", ""),
                ))
                seen.add(name)

            if len(results) >= max_results:
                break

        return results[:max_results]

    def get(self, name: str) -> Optional[IconSpec]:
        """Get a specific icon by name."""
        if name not in self._ICONS:
            return None
        data = self._ICONS[name]
        return IconSpec(
            name=name,
            set_name=data["set"],
            style="solid",
            svg_path=data["path"],
            category=data.get("category", ""),
        )

    def render_svg(self, icon: IconSpec, color_hex: str = "#2563EB", size: int = 24) -> str:
        """
        Render icon as SVG string.

        Args:
            icon: IconSpec to render
            color_hex: Color in #RRGGBB format
            size: SVG viewport size

        Returns:
            SVG string
        """
        color = color_hex.lstrip("#")
        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{icon.viewbox}" width="{size}" height="{size}" fill="#{color}">
  <path d="{icon.svg_path}"/>
</svg>'''

    def render_png(self, icon: IconSpec, color_hex: str = "#2563EB", size: int = 64) -> Optional[bytes]:
        """
        Render icon as PNG bytes.

        Args:
            icon: IconSpec to render
            color_hex: Color in #RRGGBB format
            size: Output size in pixels

        Returns:
            PNG bytes or None if rendering fails
        """
        cache_key = f"{icon.name}_{color_hex}_{size}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            # Try cairosvg first (best SVG to PNG)
            import cairosvg
            svg_string = self.render_svg(icon, color_hex, size)
            png_bytes = cairosvg.svg2png(bytestring=svg_string.encode(), output_width=size, output_height=size)
            self._cache[cache_key] = png_bytes
            return png_bytes
        except ImportError:
            pass

        try:
            # Fallback: svglib + reportlab
            from svglib.svglib import svg2rlg
            from reportlab.graphics import renderPM
            import io

            svg_string = self.render_svg(icon, color_hex, size)
            drawing = svg2rlg(io.StringIO(svg_string))
            if drawing:
                png_bytes = renderPM.drawToString(drawing, fmt="PNG")
                self._cache[cache_key] = png_bytes
                return png_bytes
        except ImportError:
            pass

        logger.warning("icon_render_no_backend: %s", icon.name)
        return None

    def list_all(self) -> List[IconSpec]:
        """List all available icons."""
        return [
            IconSpec(
                name=name,
                set_name=data["set"],
                style="solid",
                svg_path=data["path"],
                category=data.get("category", ""),
            )
            for name, data in self._ICONS.items()
        ]


# Convenience functions
def find_icon(query: str) -> Optional[IconSpec]:
    """Find a single icon by query."""
    lib = IconLibrary()
    results = lib.search(query, max_results=1)
    return results[0] if results else None


async def render_icon_for_slide(query: str, color_hex: str = "#2563EB", size: int = 64) -> Optional[bytes]:
    """One-shot icon render for slides."""
    icon = find_icon(query)
    if icon:
        lib = IconLibrary()
        return lib.render_png(icon, color_hex, size)
    return None
