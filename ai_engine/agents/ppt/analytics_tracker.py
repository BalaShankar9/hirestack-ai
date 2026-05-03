"""
AnalyticsTracker — Presentation performance insights.

Tracks and analyzes presentation engagement:
- View duration per slide
- Most/least viewed slides
- Drop-off points
- Heatmap of attention
- A/B testing results
- Comparative analysis with competitor decks

Public API:
    AnalyticsTracker().track_view(deck_id, slide_idx, duration) -> None
    AnalyticsTracker().get_insights(deck_id) -> DeckInsights
    AnalyticsTracker().compare_decks(deck1, deck2) -> ComparisonReport
    AnalyticsTracker().generate_heatmap(deck_id) -> HeatmapData

Note: This module provides tracking infrastructure. Actual data collection
happens via embedded pixels, webhooks, or client-side SDK.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.agents.ppt.schemas import DeckSpec

logger = logging.getLogger(__name__)


@dataclass
class SlideMetrics:
    """Metrics for a single slide."""

    slide_idx: int
    view_count: int = 0
    total_duration_ms: int = 0
    avg_duration_ms: float = 0.0
    completion_rate: float = 0.0  # % who viewed to end
    engagement_score: float = 0.0  # 0-100


@dataclass
class DeckInsights:
    """Complete analytics for a presentation."""

    deck_id: str
    total_views: int = 0
    unique_viewers: int = 0
    avg_completion_rate: float = 0.0
    avg_view_duration_ms: int = 0
    slide_metrics: List[SlideMetrics] = field(default_factory=list)
    top_performing_slides: List[int] = field(default_factory=list)
    drop_off_slides: List[int] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Analytics Report: {self.deck_id}",
            f"Total Views: {self.total_views}",
            f"Unique Viewers: {self.unique_viewers}",
            f"Completion Rate: {self.avg_completion_rate:.1%}",
            f"Avg Duration: {self.avg_view_duration_ms // 1000}s",
            f"Top Slides: {self.top_performing_slides[:3]}",
            f"Drop-off Points: {self.drop_off_slides}",
        ]
        return "\n".join(lines)


@dataclass
class ComparisonResult:
    """Comparison between two decks."""

    metric: str
    deck1_value: float
    deck2_value: float
    difference_pct: float
    winner: str


@dataclass
class ComparisonReport:
    """Full comparison report."""

    deck1_id: str
    deck2_id: str
    results: List[ComparisonResult] = field(default_factory=list)
    overall_winner: str = ""
    key_differences: List[str] = field(default_factory=list)


@dataclass
class HeatmapData:
    """Heatmap coordinates and intensity."""

    slide_idx: int
    coordinates: List[Tuple[float, float, float]]  # (x, y, intensity)
    hotspots: List[Tuple[float, float]]  # (x, y) of high-intensity areas


class AnalyticsTracker:
    """Track and analyze presentation performance."""

    def __init__(self, storage_backend: Optional[Any] = None) -> None:
        self.storage = storage_backend
        self._memory_store: Dict[str, List[Dict]] = {}  # In-memory fallback

    # ───────────────────────────────────────────────────────────────────────
    #  Data Collection
    # ───────────────────────────────────────────────────────────────────────

    def track_view(
        self,
        deck_id: str,
        slide_idx: int,
        duration_ms: int,
        viewer_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """
        Record a slide view event.

        Args:
            deck_id: Presentation identifier
            slide_idx: Slide number viewed
            duration_ms: Time spent on slide
            viewer_id: Optional unique viewer identifier
            timestamp: Event timestamp (defaults to now)
        """
        event = {
            "deck_id": deck_id,
            "slide_idx": slide_idx,
            "duration_ms": duration_ms,
            "viewer_id": viewer_id or "anonymous",
            "timestamp": timestamp or time.time(),
        }

        if self.storage:
            try:
                self.storage.store_event(event)
            except Exception as exc:
                logger.warning("storage_failed_fallback_to_memory: %s", str(exc)[:200])
                self._store_in_memory(deck_id, event)
        else:
            self._store_in_memory(deck_id, event)

    def _store_in_memory(self, deck_id: str, event: Dict) -> None:
        """Store event in memory cache."""
        if deck_id not in self._memory_store:
            self._memory_store[deck_id] = []
        self._memory_store[deck_id].append(event)

        # Limit memory usage
        if len(self._memory_store[deck_id]) > 10000:
            self._memory_store[deck_id] = self._memory_store[deck_id][-5000:]

    def track_engagement(
        self,
        deck_id: str,
        slide_idx: int,
        event_type: str,  # "click", "hover", "zoom", "share"
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Track engagement event.

        Args:
            deck_id: Presentation identifier
            slide_idx: Slide number
            event_type: Type of engagement
            metadata: Additional event data
        """
        event = {
            "deck_id": deck_id,
            "slide_idx": slide_idx,
            "event_type": event_type,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }

        if self.storage:
            try:
                self.storage.store_event(event)
            except Exception as exc:
                logger.debug("engagement_tracking_failed: %s", str(exc)[:200])

    # ───────────────────────────────────────────────────────────────────────
    #  Insights Generation
    # ───────────────────────────────────────────────────────────────────────

    def get_insights(self, deck_id: str) -> DeckInsights:
        """
        Generate insights for a presentation.

        Args:
            deck_id: Presentation identifier

        Returns:
            DeckInsights with metrics and recommendations
        """
        events = self._get_events(deck_id)

        if not events:
            return DeckInsights(deck_id=deck_id)

        # Calculate metrics
        total_views = len(events)
        unique_viewers = len(set(e.get("viewer_id", "") for e in events))

        # Group by slide
        slide_events: Dict[int, List[Dict]] = {}
        for event in events:
            idx = event.get("slide_idx", 0)
            slide_events.setdefault(idx, []).append(event)

        slide_metrics = []
        for idx in sorted(slide_events.keys()):
            slide_events_list = slide_events[idx]
            durations = [e.get("duration_ms", 0) for e in slide_events_list]

            total_dur = sum(durations)
            avg_dur = total_dur / len(durations) if durations else 0

            # Engagement score: based on duration vs expected
            expected_duration = 10000  # 10 seconds baseline
            engagement = min(100, (avg_dur / expected_duration) * 100)

            metrics = SlideMetrics(
                slide_idx=idx,
                view_count=len(slide_events_list),
                total_duration_ms=total_dur,
                avg_duration_ms=avg_dur,
                engagement_score=engagement,
            )
            slide_metrics.append(metrics)

        # Find patterns
        top_slides = sorted(
            slide_metrics,
            key=lambda x: x.engagement_score,
            reverse=True,
        )[:3]
        top_performing = [s.slide_idx for s in top_slides]

        # Drop-off detection (slides with low engagement after high ones)
        drop_offs = []
        for i, metric in enumerate(slide_metrics[1:], 1):
            prev_score = slide_metrics[i-1].engagement_score
            if prev_score > 50 and metric.engagement_score < 30:
                drop_offs.append(metric.slide_idx)

        # Completion rate (viewers who reached last slide)
        last_slide_idx = max(slide_events.keys()) if slide_events else 0
        last_slide_views = len(slide_events.get(last_slide_idx, []))
        completion_rate = last_slide_views / unique_viewers if unique_viewers > 0 else 0

        # Generate recommendations
        recommendations = self._generate_recommendations(
            slide_metrics, drop_offs, completion_rate
        )

        return DeckInsights(
            deck_id=deck_id,
            total_views=total_views,
            unique_viewers=unique_viewers,
            avg_completion_rate=completion_rate,
            avg_view_duration_ms=int(sum(m.avg_duration_ms for m in slide_metrics) / len(slide_metrics)) if slide_metrics else 0,
            slide_metrics=slide_metrics,
            top_performing_slides=top_performing,
            drop_off_slides=drop_offs,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        slide_metrics: List[SlideMetrics],
        drop_offs: List[int],
        completion_rate: float,
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        if completion_rate < 0.5:
            recommendations.append(
                "Low completion rate. Consider shortening the deck or adding engagement hooks."
            )

        if drop_offs:
            recommendations.append(
                f"High drop-off at slides {drop_offs}. Review content relevance and visual appeal."
            )

        # Check for slides that are too long
        long_slides = [m for m in slide_metrics if m.avg_duration_ms > 30000]
        if len(long_slides) > len(slide_metrics) * 0.3:
            recommendations.append(
                "Many slides have high view duration. Consider splitting complex content."
            )

        # Check for slides that are too short
        short_slides = [m for m in slide_metrics if m.avg_duration_ms < 3000]
        if len(short_slides) > len(slide_metrics) * 0.3:
            recommendations.append(
                "Many slides viewed too quickly. Content may be too dense or unengaging."
            )

        return recommendations

    # ───────────────────────────────────────────────────────────────────────
    #  Deck Comparison
    # ───────────────────────────────────────────────────────────────────────

    def compare_decks(
        self,
        deck1_id: str,
        deck2_id: str,
    ) -> ComparisonReport:
        """
        Compare two presentations performance.

        Args:
            deck1_id: First deck identifier
            deck2_id: Second deck identifier

        Returns:
            ComparisonReport with detailed comparison
        """
        insights1 = self.get_insights(deck1_id)
        insights2 = self.get_insights(deck2_id)

        results = []

        # Compare metrics
        comparisons = [
            ("Total Views", insights1.total_views, insights2.total_views),
            ("Unique Viewers", insights1.unique_viewers, insights2.unique_viewers),
            ("Completion Rate", insights1.avg_completion_rate, insights2.avg_completion_rate),
            ("Avg Duration", insights1.avg_view_duration_ms, insights2.avg_view_duration_ms),
        ]

        for metric, val1, val2 in comparisons:
            if val2 > 0:
                diff_pct = ((val1 - val2) / val2) * 100
            else:
                diff_pct = 100 if val1 > 0 else 0

            winner = deck1_id if val1 > val2 else deck2_id if val2 > val1 else "tie"

            results.append(ComparisonResult(
                metric=metric,
                deck1_value=val1,
                deck2_value=val2,
                difference_pct=diff_pct,
                winner=winner,
            ))

        # Determine overall winner
        deck1_wins = sum(1 for r in results if r.winner == deck1_id)
        deck2_wins = sum(1 for r in results if r.winner == deck2_id)

        overall_winner = deck1_id if deck1_wins > deck2_wins else deck2_id if deck2_wins > deck1_wins else "tie"

        # Key differences
        key_diffs = []
        for result in results:
            if abs(result.difference_pct) > 20:
                direction = "higher" if result.difference_pct > 0 else "lower"
                key_diffs.append(
                    f"{result.metric}: {deck1_id} is {abs(result.difference_pct):.1f}% {direction} than {deck2_id}"
                )

        return ComparisonReport(
            deck1_id=deck1_id,
            deck2_id=deck2_id,
            results=results,
            overall_winner=overall_winner,
            key_differences=key_diffs,
        )

    # ───────────────────────────────────────────────────────────────────────
    #  Heatmap Generation
    # ───────────────────────────────────────────────────────────────────────

    def generate_heatmap(self, deck_id: str, slide_idx: int) -> HeatmapData:
        """
        Generate attention heatmap for a slide.

        Args:
            deck_id: Presentation identifier
            slide_idx: Slide number

        Returns:
            HeatmapData with coordinate intensity
        """
        events = self._get_events(deck_id)
        slide_events = [e for e in events if e.get("slide_idx") == slide_idx]

        coordinates = []
        hotspots = []

        for event in slide_events:
            meta = event.get("metadata", {})
            clicks = meta.get("clicks", [])

            for click in clicks:
                x = click.get("x", 0)
                y = click.get("y", 0)
                coordinates.append((x, y, 1.0))

        # Identify hotspots (clusters of activity)
        if coordinates:
            # Simple clustering: group by proximity
            threshold = 0.1  # 10% of slide dimensions
            hotspots = self._cluster_hotspots(coordinates, threshold)

        return HeatmapData(
            slide_idx=slide_idx,
            coordinates=coordinates,
            hotspots=hotspots,
        )

    def _cluster_hotspots(
        self,
        coordinates: List[Tuple[float, float, float]],
        threshold: float,
    ) -> List[Tuple[float, float]]:
        """Cluster coordinates into hotspots."""
        if not coordinates:
            return []

        hotspots = []
        used = set()

        for i, (x1, y1, _) in enumerate(coordinates):
            if i in used:
                continue

            cluster_x, cluster_y = [x1], [y1]
            used.add(i)

            for j, (x2, y2, _) in enumerate(coordinates[i+1:], i+1):
                if j in used:
                    continue

                distance = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
                if distance < threshold:
                    cluster_x.append(x2)
                    cluster_y.append(y2)
                    used.add(j)

            if len(cluster_x) >= 3:  # Minimum cluster size
                avg_x = sum(cluster_x) / len(cluster_x)
                avg_y = sum(cluster_y) / len(cluster_y)
                hotspots.append((avg_x, avg_y))

        return hotspots

    # ───────────────────────────────────────────────────────────────────────
    #  A/B Testing
    # ───────────────────────────────────────────────────────────────────────

    def create_ab_test(
        self,
        deck_a: DeckSpec,
        deck_b: DeckSpec,
        test_name: str,
        traffic_split: float = 0.5,
    ) -> str:
        """
        Set up A/B test for two deck variants.

        Args:
            deck_a: Control variant
            deck_b: Test variant
            test_name: Identifier for the test
            traffic_split: % of traffic to variant B

        Returns:
            Test ID
        """
        test_id = f"ab_test_{test_name}_{int(time.time())}"

        test_config = {
            "test_id": test_id,
            "deck_a_id": deck_a.title,
            "deck_b_id": deck_b.title,
            "traffic_split": traffic_split,
            "created_at": time.time(),
        }

        if self.storage:
            try:
                self.storage.store_test_config(test_id, test_config)
            except Exception as exc:
                logger.warning("ab_test_storage_failed: %s", str(exc)[:200])

        logger.info("ab_test_created: %s", test_id)
        return test_id

    def get_ab_test_results(self, test_id: str) -> Optional[ComparisonReport]:
        """Get results for an A/B test."""
        # Extract deck IDs from test
        if self.storage:
            try:
                config = self.storage.get_test_config(test_id)
                if config:
                    return self.compare_decks(
                        config["deck_a_id"],
                        config["deck_b_id"],
                    )
            except Exception as exc:
                logger.warning("ab_test_results_failed: %s", str(exc)[:200])

        return None

    # ───────────────────────────────────────────────────────────────────────
    #  Competitor Analysis
    # ───────────────────────────────────────────────────────────────────────

    def analyze_competitor_deck(
        self,
        competitor_deck: DeckSpec,
        our_deck: DeckSpec,
    ) -> Dict[str, Any]:
        """
        Analyze competitor deck for gaps and opportunities.

        Args:
            competitor_deck: Competitor's deck
            our_deck: Our deck

        Returns:
            Analysis report
        """
        analysis = {
            "competitor_strengths": [],
            "our_advantages": [],
            "content_gaps": [],
            "structural_differences": {},
        }

        # Compare slide counts
        comp_slides = len(competitor_deck.slides)
        our_slides = len(our_deck.slides)

        analysis["structural_differences"]["slide_count"] = {
            "competitor": comp_slides,
            "ours": our_slides,
            "difference": our_slides - comp_slides,
        }

        # Compare slide variety
        comp_kinds = set(s.kind for s in competitor_deck.slides)
        our_kinds = set(s.kind for s in our_deck.slides)

        if len(comp_kinds) > len(our_kinds):
            analysis["competitor_strengths"].append(
                f"More slide variety ({len(comp_kinds)} vs {len(our_kinds)} types)"
            )
        elif len(our_kinds) > len(comp_kinds):
            analysis["our_advantages"].append(
                f"More slide variety ({len(our_kinds)} vs {len(comp_kinds)} types)"
            )

        # Compare content density
        comp_bullets = sum(len(s.bullets or []) for s in competitor_deck.slides)
        our_bullets = sum(len(s.bullets or []) for s in our_deck.slides)

        if comp_bullets > our_bullets * 1.5:
            analysis["competitor_strengths"].append("Higher information density")
        elif our_bullets > comp_bullets * 1.5:
            analysis["our_advantages"].append("Higher information density")

        # Check for visual content
        comp_visuals = sum(1 for s in competitor_deck.slides if s.chart or s.image)
        our_visuals = sum(1 for s in our_deck.slides if s.chart or s.image)

        if comp_visuals > our_visuals:
            analysis["content_gaps"].append(
                f"Consider adding more visual content ({comp_visuals} vs {our_visuals})"
            )

        return analysis

    # ───────────────────────────────────────────────────────────────────────
    #  Utility Methods
    # ───────────────────────────────────────────────────────────────────────

    def _get_events(self, deck_id: str) -> List[Dict]:
        """Get all events for a deck."""
        if self.storage:
            try:
                return self.storage.get_events(deck_id)
            except Exception as exc:
                logger.warning("storage_get_failed: %s", str(exc)[:200])

        return self._memory_store.get(deck_id, [])


# Convenience functions

def track_slide_view(
    deck_id: str,
    slide_idx: int,
    duration_ms: int,
    viewer_id: Optional[str] = None,
) -> None:
    """One-shot slide view tracking."""
    tracker = AnalyticsTracker()
    tracker.track_view(deck_id, slide_idx, duration_ms, viewer_id)


def get_deck_insights(deck_id: str) -> DeckInsights:
    """One-shot insights retrieval."""
    tracker = AnalyticsTracker()
    return tracker.get_insights(deck_id)


def compare_presentations(deck1_id: str, deck2_id: str) -> ComparisonReport:
    """One-shot comparison."""
    tracker = AnalyticsTracker()
    return tracker.compare_decks(deck1_id, deck2_id)
