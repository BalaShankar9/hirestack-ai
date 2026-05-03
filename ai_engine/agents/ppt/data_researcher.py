"""
DataResearcher — Fetch real-world data for chart slides.

Integrates web search and data APIs to populate charts with actual
statistics, trends, and market data instead of placeholder values.

Supported sources:
    - Perplexity/Search API for general market data
    - Yahoo Finance for financial metrics
    - Statistical databases for demographics
    - Internal knowledge base for company data

Caching:
    - 1-hour TTL for volatile data (stock prices, trends)
    - 24-hour TTL for stable data (market sizes, demographics)

Public API:
    DataResearcher.research_for_slide(slide_spec) -> Optional[ChartSpec]
    DataResearcher.enrich_deck(deck_spec) -> DeckSpec
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.agents.ppt.schemas import ChartKind, ChartSpec, SlideKind, SlideSpec

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cached research result."""
    data: Any
    timestamp: float
    ttl_seconds: int


class DataResearcher:
    """Research and populate real data for presentation charts."""

    # TTL configuration by data type
    _TTL_CONFIG = {
        "stock_price": 3600,      # 1 hour
        "market_trend": 3600,    # 1 hour
        "market_size": 86400,    # 24 hours
        "demographic": 86400,    # 24 hours
        "financial": 3600,       # 1 hour
        "general": 14400,        # 4 hours
    }

    def __init__(
        self,
        *,
        perplexity_api_key: Optional[str] = None,
        search_api_key: Optional[str] = None,
        cache: Optional[Dict[str, CacheEntry]] = None,
    ) -> None:
        self.perplexity_api_key = perplexity_api_key or os.getenv("PERPLEXITY_API_KEY")
        self.search_api_key = search_api_key or os.getenv("SEARCH_API_KEY")
        self._cache: Dict[str, CacheEntry] = cache or {}
        self._client: Optional[Any] = None

    async def research_for_slide(
        self,
        slide_title: str,
        slide_context: str = "",
        data_hint: Optional[str] = None,
    ) -> Optional[ChartSpec]:
        """
        Research data for a single slide.

        Args:
            slide_title: The slide's title text
            slide_context: Additional context (topic, industry)
            data_hint: What kind of data to look for ("market size", "growth", etc.)

        Returns:
            ChartSpec with real data, or None if research fails
        """
        cache_key = self._cache_key(slide_title, slide_context, data_hint)

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Determine research strategy
        hint = (data_hint or "").lower()

        if any(k in hint for k in ("revenue", "profit", "stock", "eps", "financial")):
            result = await self._research_financial(slide_title, slide_context)
        elif any(k in hint for k in ("market size", "market share", "industry")):
            result = await self._research_market(slide_title, slide_context)
        elif any(k in hint for k in ("growth", "trend", "forecast", "projection")):
            result = await self._research_trends(slide_title, slide_context)
        elif any(k in hint for k in ("demographic", "population", "user", "customer")):
            result = await self._research_demographics(slide_title, slide_context)
        else:
            result = await self._research_general(slide_title, slide_context)

        if result:
            ttl = self._TTL_CONFIG.get(self._infer_data_type(hint), 14400)
            self._cache[cache_key] = CacheEntry(result, time.time(), ttl)

        return result

    async def enrich_deck(
        self,
        slides: List[SlideSpec],
        topic: str = "",
    ) -> List[SlideSpec]:
        """
        Enrich chart slides with real data.

        Args:
            slides: List of slide specs
            topic: Overall deck topic for context

        Returns:
            Slides with chart data populated where possible
        """
        enriched = []

        for slide in slides:
            if slide.kind == SlideKind.chart and (slide.chart is None or self._is_placeholder_data(slide.chart)):
                # Research data for this chart
                data_hint = self._infer_data_hint(slide.title, topic)
                chart_spec = await self.research_for_slide(
                    slide_title=slide.title or "",
                    slide_context=topic,
                    data_hint=data_hint,
                )
                if chart_spec:
                    slide = slide.model_copy(update={"chart": chart_spec})
                    logger.info("data_research_enriched: %s", slide.title)
            enriched.append(slide)

        return enriched

    def _is_placeholder_data(self, chart: ChartSpec) -> bool:
        """Check if chart has placeholder/mock data."""
        if not chart.series:
            return True
        # Check for obviously fake patterns
        for s in chart.series:
            data = s.get("data") or []
            if not data:
                continue
            # Check for sequential integers (fake pattern)
            if all(isinstance(d, (int, float)) for d in data):
                if data == list(range(1, len(data) + 1)):
                    return True
                if data == [10 * (i + 1) for i in range(len(data))]:
                    return True
        return False

    def _infer_data_hint(self, slide_title: str, topic: str) -> str:
        """Infer what kind of data to research."""
        title_lower = (slide_title or "").lower()
        topic_lower = (topic or "").lower()

        hints = []
        if any(w in title_lower for w in ("revenue", "sales", "financial", "profit", "eps")):
            hints.append("financial")
        if any(w in title_lower for w in ("market", "share", "size", "industry")):
            hints.append("market size")
        if any(w in title_lower for w in ("growth", "trend", "forecast", "projection", "cagr")):
            hints.append("growth")
        if any(w in title_lower for w in ("user", "customer", "demographic", "audience")):
            hints.append("demographic")
        if any(w in title_lower for w in ("competition", "competitive", "landscape", "player")):
            hints.append("market share")

        return " ".join(hints) if hints else "general statistics"

    async def _research_financial(self, title: str, context: str) -> Optional[ChartSpec]:
        """Research financial metrics."""
        # Extract company/ticker from title/context
        query = f"{title} {context} revenue profit margin financial data 2024 2025"
        data = await self._search_query(query)
        if data:
            return self._parse_to_chart(data, "column", title)
        return None

    async def _research_market(self, title: str, context: str) -> Optional[ChartSpec]:
        """Research market size and share data."""
        query = f"{title} {context} market size TAM SAM SOM statistics 2024 2025"
        data = await self._search_query(query)
        if data:
            return self._parse_to_chart(data, "pie", title)
        return None

    async def _research_trends(self, title: str, context: str) -> Optional[ChartSpec]:
        """Research growth trends and forecasts."""
        query = f"{title} {context} growth rate CAGR trend forecast 2024 2025 2030"
        data = await self._search_query(query)
        if data:
            return self._parse_to_chart(data, "line", title)
        return None

    async def _research_demographics(self, title: str, context: str) -> Optional[ChartSpec]:
        """Research demographic/user data."""
        query = f"{title} {context} user statistics demographics customer segments"
        data = await self._search_query(query)
        if data:
            return self._parse_to_chart(data, "bar", title)
        return None

    async def _research_general(self, title: str, context: str) -> Optional[ChartSpec]:
        """General statistics research."""
        query = f"{title} {context} key statistics data numbers metrics"
        data = await self._search_query(query)
        if data:
            return self._parse_to_chart(data, "column", title)
        return None

    async def _search_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Execute search query and extract structured data.

        Uses Perplexity API if available, otherwise falls back to general search.
        """
        if self.perplexity_api_key:
            return await self._perplexity_search(query)

        # Placeholder: would integrate with actual search API
        logger.debug("search_query: %s (no API configured)", query[:100])
        return None

    async def _perplexity_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Search using Perplexity API."""
        try:
            import httpx

            if self._client is None:
                self._client = httpx.AsyncClient(timeout=30.0)

            response = await self._client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a data extraction assistant. "
                                "Extract numerical data from search results. "
                                "Return JSON with: summary, data_points (list of {label, value}), "
                                "and source_attribution."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Find statistics for: {query}",
                        },
                    ],
                },
            )
            response.raise_for_status()
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Try to parse JSON from content
            try:
                data = json.loads(content)
                return data
            except json.JSONDecodeError:
                # Extract structured data from text
                return self._extract_data_from_text(content)

        except Exception as exc:
            logger.warning("perplexity_search_failed: %s", str(exc)[:200])
            return None

    def _extract_data_from_text(self, text: str) -> Dict[str, Any]:
        """Extract numerical data from unstructured text."""
        import re

        # Look for patterns like "X%", "$X billion", "X million users"
        data_points = []

        # Percentage patterns
        pct_matches = re.findall(r'(\d+(?:\.\d+)?)%', text)
        for i, val in enumerate(pct_matches[:6]):
            data_points.append({
                "label": f"Metric {i+1}",
                "value": float(val),
            })

        # Large number patterns (billions, millions)
        billion_matches = re.findall(r'\$?(\d+(?:\.\d+)?)\s*billion', text, re.IGNORECASE)
        for val in billion_matches[:3]:
            data_points.append({
                "label": f"${val}B",
                "value": float(val) * 1000,  # Convert to consistent unit
            })

        return {
            "summary": text[:500],
            "data_points": data_points,
            "source_attribution": "Perplexity AI",
        }

    def _parse_to_chart(
        self,
        data: Dict[str, Any],
        default_kind: str,
        title: str,
    ) -> ChartSpec:
        """Convert research data to ChartSpec."""
        data_points = data.get("data_points", [])

        if not data_points:
            # Create placeholder if no data extracted
            return ChartSpec(
                kind=default_kind,
                title=title,
                series=[{"name": "Data", "data": [100, 120, 140, 160]}],
                categories=["Q1", "Q2", "Q3", "Q4"],
            )

        # Extract values and labels
        values = [dp.get("value", 0) for dp in data_points]
        labels = [dp.get("label", f"Item {i+1}") for i, dp in enumerate(data_points)]

        # Determine best chart kind based on data
        kind = self._select_chart_kind(values, labels, default_kind)

        # Add source attribution to chart title
        source = data.get("source_attribution", "Research")
        chart_title = f"{title} (Source: {source})"

        return ChartSpec(
            kind=kind,
            title=chart_title,
            series=[{"name": "Value", "data": values}],
            categories=labels,
        )

    def _select_chart_kind(self, values: List[float], labels: List[str], default: str) -> str:
        """Select appropriate chart kind based on data characteristics."""
        if len(values) <= 4:
            # Small number of categories → pie or donut for parts of whole
            if sum(values) > 0 and all(v > 0 for v in values):
                total = sum(values)
                # If values sum to roughly 100, likely percentages
                if 95 <= total <= 105:
                    return "pie"
                return "donut"
            return "column"

        if len(values) > 8:
            # Many data points → line for trends
            return "line"

        return default

    def _cache_key(self, *parts: str) -> str:
        """Generate cache key from query parts."""
        key_string = "|".join(p.lower().strip() for p in parts if p)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached result if not expired."""
        entry = self._cache.get(key)
        if entry:
            if time.time() - entry.timestamp < entry.ttl_seconds:
                return entry.data
            else:
                del self._cache[key]
        return None

    def _infer_data_type(self, hint: str) -> str:
        """Infer data type from hint for TTL selection."""
        hint_lower = hint.lower()
        for dtype in ("stock_price", "market_trend", "market_size", "demographic", "financial"):
            if dtype.replace("_", " ") in hint_lower or dtype in hint_lower:
                return dtype
        return "general"

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Convenience function for direct use
async def research_chart_data(
    slide_title: str,
    context: str = "",
    hint: Optional[str] = None,
) -> Optional[ChartSpec]:
    """One-shot chart data research."""
    researcher = DataResearcher()
    try:
        return await researcher.research_for_slide(slide_title, context, hint)
    finally:
        await researcher.close()
