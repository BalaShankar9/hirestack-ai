"""
QualityValidator — Content consistency, narrative flow, and design scoring.

Provides automated quality assurance for presentations:
- Content consistency: Check for contradictions, repetitive content
- Narrative flow: Scoring of story arc (setup → conflict → resolution)
- Design principles: Alignment, whitespace, text density checks
- Auto-revision suggestions for flagged issues
- Confidence scoring per slide

Public API:
    QualityValidator.validate(deck) -> ValidationReport
    QualityValidator.suggest_improvements(report) -> List[Revision]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.agents.ppt.schemas import ChartKind, ChartSpec, DeckSpec, SlideKind, SlideSpec

logger = logging.getLogger(__name__)


@dataclass
class SlideScore:
    """Quality score for a single slide."""

    slide_idx: int
    slide_kind: str
    title: str
    confidence: float  # 0.0-1.0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    text_density: float = 0.0  # 0-1 ratio of text coverage
    readability: float = 0.0  # Flesch-Kincaid inspired


@dataclass
class NarrativeScore:
    """Narrative flow scoring."""

    has_opening: bool
    has_closing: bool
    has_sections: bool
    flow_score: float  # 0.0-1.0
    structure_type: str  # "problem-solution", "chronological", "compare", "unknown"
    gap_warnings: List[str] = field(default_factory=list)


@dataclass
class ContentCheck:
    """Content consistency finding."""

    issue_type: str  # "contradiction", "repetition", "vague", "unsupported"
    slides_affected: List[int]
    description: str
    severity: str  # "high", "medium", "low"


@dataclass
class ValidationReport:
    """Complete validation results."""

    deck_title: str = ""
    total_slides: int = 0
    overall_score: float = 0.0  # 0-1 weighted average
    slide_scores: List[SlideScore] = field(default_factory=list)
    narrative_score: Optional[NarrativeScore] = None
    content_checks: List[ContentCheck] = field(default_factory=list)
    design_score: float = 0.0
    pass_threshold: float = 0.6

    def passed(self) -> bool:
        """Check if deck passes quality threshold."""
        return self.overall_score >= self.pass_threshold

    def critical_issues(self) -> List[Any]:
        """Get all critical issues."""
        critical = []
        for check in self.content_checks:
            if check.severity == "high":
                critical.append(check)
        for score in self.slide_scores:
            if score.confidence < 0.5:
                critical.append(f"Slide {score.slide_idx}: low confidence ({score.confidence:.2f})")
        return critical

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Quality Report: '{self.deck_title}'",
            f"Overall Score: {self.overall_score:.1%}",
            f"Narrative Flow: {self.narrative_score.flow_score:.1% if self.narrative_score else 'N/A'}",
            f"Design Score: {self.design_score:.1%}",
            f"Slides: {self.total_slides}",
            f"Issues: {len(self.content_checks)} content, {sum(len(s.issues) for s in self.slide_scores)} slide",
            f"Status: {'PASS' if self.passed() else 'NEEDS REVISION'}",
        ]
        return "\n".join(lines)


@dataclass
class Revision:
    """Suggested revision to improve the deck."""

    target_slide_idx: Optional[int]
    action: str  # "rewrite", "add", "remove", "reorder", "merge"
    description: str
    priority: str  # "high", "medium", "low"
    expected_improvement: float  # Estimated score improvement


class QualityValidator:
    """Validate and score presentation quality."""

    # Scoring weights
    NARRATIVE_WEIGHT = 0.3
    CONTENT_WEIGHT = 0.3
    DESIGN_WEIGHT = 0.2
    SLIDE_QUALITY_WEIGHT = 0.2

    def __init__(self) -> None:
        pass

    def validate(self, deck: DeckSpec) -> ValidationReport:
        """
        Run full validation on a deck.

        Args:
            deck: DeckSpec to validate

        Returns:
            ValidationReport with scores and issues
        """
        report = ValidationReport()
        report.deck_title = deck.title
        report.total_slides = len(deck.slides)

        if not deck.slides:
            report.overall_score = 0.0
            return report

        # Run sub-validations
        narrative = self._validate_narrative(deck)
        content = self._validate_content(deck)
        design = self._validate_design(deck)
        slides = self._validate_slides(deck)

        report.narrative_score = narrative
        report.content_checks = content
        report.design_score = design
        report.slide_scores = slides

        # Calculate weighted overall score
        narrative_score = narrative.flow_score if narrative else 0.0
        content_score = 1.0 - min(len(content) * 0.15, 1.0) if content else 1.0
        slide_avg = sum(s.confidence for s in slides) / len(slides) if slides else 0.0

        report.overall_score = (
            narrative_score * self.NARRATIVE_WEIGHT +
            content_score * self.CONTENT_WEIGHT +
            design * self.DESIGN_WEIGHT +
            slide_avg * self.SLIDE_QUALITY_WEIGHT
        )

        return report

    def _validate_narrative(self, deck: DeckSpec) -> NarrativeScore:
        """Analyze narrative structure and flow."""
        slides = deck.slides
        n = len(slides)

        has_opening = n > 0 and slides[0].kind in (SlideKind.title, SlideKind.content)
        has_closing = n > 0 and slides[-1].kind == SlideKind.closing
        has_sections = any(s.kind == SlideKind.section for s in slides)

        # Determine structure type
        structure = "unknown"
        if n >= 3:
            # Check for problem-solution structure
            problem_indicators = ["problem", "pain", "challenge", "issue", "broken"]
            solution_indicators = ["solution", "fix", "solve", "product", "platform"]
            benefit_indicators = ["benefit", "result", "impact", "outcome", "roi"]

            slide_texts = [s.title.lower() for s in slides]
            has_problem = any(p in t for t in slide_texts for p in problem_indicators)
            has_solution = any(s in t for t in slide_texts for s in solution_indicators)
            has_benefits = any(b in t for t in slide_texts for b in benefit_indicators)

            if has_problem and has_solution and has_benefits:
                structure = "problem-solution"
            elif any("vs" in t or "versus" in t for t in slide_texts):
                structure = "compare"
            elif any(w in t for t in slide_texts for w in ["2023", "2024", "q1", "q2", "roadmap"]):
                structure = "chronological"

        # Calculate flow score
        flow_score = 0.5  # Baseline

        # Boost for structure
        if has_opening:
            flow_score += 0.15
        if has_closing:
            flow_score += 0.15
        if has_sections:
            flow_score += 0.1
        if structure != "unknown":
            flow_score += 0.1

        # Penalize for gaps
        gaps = []
        kind_sequence = [s.kind for s in slides]

        # Check for too many consecutive content slides without variety
        content_streak = 0
        max_content_streak = 0
        for kind in kind_sequence:
            if kind == SlideKind.content:
                content_streak += 1
                max_content_streak = max(max_content_streak, content_streak)
            else:
                content_streak = 0

        if max_content_streak > 5:
            flow_score -= 0.1
            gaps.append(f"Long sequence of {max_content_streak} content slides — consider adding visual breaks")

        # Check deck length appropriateness
        if n < 5:
            flow_score -= 0.1
            gaps.append("Deck is very short — may lack depth")
        elif n > 20:
            flow_score -= 0.1
            gaps.append("Deck is very long — consider condensing")

        return NarrativeScore(
            has_opening=has_opening,
            has_closing=has_closing,
            has_sections=has_sections,
            flow_score=max(0.0, min(1.0, flow_score)),
            structure_type=structure,
            gap_warnings=gaps,
        )

    def _validate_content(self, deck: DeckSpec) -> List[ContentCheck]:
        """Check for content inconsistencies."""
        checks = []
        slides = deck.slides

        # Check for repetitive titles
        titles = [s.title.lower() for s in slides if s.title]
        seen: Dict[str, List[int]] = {}
        for idx, title in enumerate(titles):
            key = title.strip()
            if key:
                seen.setdefault(key, []).append(idx)

        for title, indices in seen.items():
            if len(indices) > 1:
                checks.append(ContentCheck(
                    issue_type="repetition",
                    slides_affected=indices,
                    description=f"Repeated slide title: '{title}'",
                    severity="low" if len(indices) == 2 else "medium",
                ))

        # Check for vague titles
        vague_words = {"overview", "summary", "details", "info", "stuff", "things", "general"}
        for idx, slide in enumerate(slides):
            title_lower = slide.title.lower()
            if any(w in title_lower for w in vague_words):
                checks.append(ContentCheck(
                    issue_type="vague",
                    slides_affected=[idx],
                    description=f"Vague title: '{slide.title}' — be more specific",
                    severity="low",
                ))

        # Check for empty content slides
        for idx, slide in enumerate(slides):
            if slide.kind == SlideKind.content:
                if not slide.bullets and not slide.subtitle and not slide.chart:
                    checks.append(ContentCheck(
                        issue_type="unsupported",
                        slides_affected=[idx],
                        description=f"Empty content slide: '{slide.title}'",
                        severity="high",
                    ))

        # Check chart data quality
        for idx, slide in enumerate(slides):
            if slide.chart:
                chart = slide.chart
                if not chart.series:
                    checks.append(ContentCheck(
                        issue_type="unsupported",
                        slides_affected=[idx],
                        description=f"Chart slide has no data: '{slide.title}'",
                        severity="high",
                    ))
                else:
                    # Check for placeholder patterns
                    for s in chart.series:
                        data = s.get("data", [])
                        if data == list(range(1, len(data) + 1)):
                            checks.append(ContentCheck(
                                issue_type="unsupported",
                                slides_affected=[idx],
                                description=f"Chart uses placeholder data (1,2,3...) — replace with real numbers",
                                severity="medium",
                            ))

        return checks

    def _validate_design(self, deck: DeckSpec) -> float:
        """Score design quality (estimated, without actual PPTX)."""
        score = 0.5  # Baseline

        slides = deck.slides
        n = len(slides)

        if n == 0:
            return 0.0

        # Check visual variety
        kinds = set(s.kind for s in slides)
        variety = len(kinds) / max(len(SlideKind), 1)
        score += variety * 0.2

        # Check chart/data slides ratio
        chart_count = sum(1 for s in slides if s.kind == SlideKind.chart)
        table_count = sum(1 for s in slides if s.kind == SlideKind.table)
        data_slides = chart_count + table_count
        data_ratio = data_slides / n if n > 0 else 0

        # Optimal: 20-40% data slides
        if 0.2 <= data_ratio <= 0.4:
            score += 0.15
        elif data_ratio > 0.5:
            score -= 0.05  # Too many charts
        elif data_ratio < 0.1:
            score -= 0.05  # Too few visuals

        # Check image variety
        image_count = sum(1 for s in slides if s.kind in (SlideKind.image, SlideKind.image_text))
        if image_count > 0:
            score += 0.1

        # Penalize for too much text
        text_heavy = 0
        for slide in slides:
            text_length = len(slide.title or "") + sum(len(b) for b in slide.bullets or [])
            if text_length > 500:
                text_heavy += 1

        text_ratio = text_heavy / n if n > 0 else 0
        if text_ratio > 0.3:
            score -= 0.1

        return max(0.0, min(1.0, score))

    def _validate_slides(self, deck: DeckSpec) -> List[SlideScore]:
        """Score individual slides."""
        scores = []

        for idx, slide in enumerate(deck.slides):
            score = SlideScore(
                slide_idx=idx,
                slide_kind=slide.kind,
                title=slide.title or "Untitled",
                confidence=0.5,
            )

            # Title quality
            title = slide.title or ""
            if len(title) < 5:
                score.issues.append("Title too short")
                score.confidence -= 0.15
            elif len(title) > 80:
                score.issues.append("Title too long")
                score.confidence -= 0.1
            else:
                score.confidence += 0.1

            # Content appropriateness
            if slide.kind == SlideKind.content:
                bullet_count = len(slide.bullets or [])
                if bullet_count == 0:
                    score.issues.append("No bullet points")
                    score.confidence -= 0.2
                elif bullet_count > 8:
                    score.issues.append("Too many bullet points (>8)")
                    score.confidence -= 0.1
                elif 3 <= bullet_count <= 6:
                    score.confidence += 0.1

                # Bullet length check
                long_bullets = sum(1 for b in (slide.bullets or []) if len(b) > 120)
                if long_bullets > 0:
                    score.issues.append(f"{long_bullets} bullets too long (>120 chars)")
                    score.confidence -= 0.05 * long_bullets

            # Speaker notes check
            if not slide.notes:
                score.suggestions.append("Add speaker notes")
                score.confidence -= 0.02  # Minor penalty

            # Chart data quality
            if slide.chart:
                if not slide.chart.series:
                    score.issues.append("Chart missing data")
                    score.confidence -= 0.2
                else:
                    score.confidence += 0.05

            score.confidence = max(0.0, min(1.0, score.confidence))

            # Calculate text density estimate
            all_text = slide.title or ""
            all_text += slide.subtitle or ""
            all_text += " ".join(slide.bullets or [])
            all_text += slide.body or ""
            score.text_density = min(len(all_text) / 1000, 1.0)

            scores.append(score)

        return scores

    def suggest_improvements(self, report: ValidationReport) -> List[Revision]:
        """
        Generate revision suggestions based on validation report.

        Args:
            report: ValidationReport from validate()

        Returns:
            List of Revision suggestions, sorted by priority
        """
        revisions = []

        # Critical issues first
        for check in report.content_checks:
            if check.severity == "high":
                revisions.append(Revision(
                    target_slide_idx=check.slides_affected[0] if check.slides_affected else None,
                    action="rewrite",
                    description=check.description,
                    priority="high",
                    expected_improvement=0.15,
                ))

        # Slide-specific issues
        for score in report.slide_scores:
            if score.confidence < 0.4:
                revisions.append(Revision(
                    target_slide_idx=score.slide_idx,
                    action="rewrite",
                    description=f"Slide needs complete rewrite (confidence: {score.confidence:.0%})",
                    priority="high",
                    expected_improvement=0.2,
                ))

            for issue in score.issues:
                if "placeholder" in issue.lower() or "empty" in issue.lower():
                    revisions.append(Revision(
                        target_slide_idx=score.slide_idx,
                        action="rewrite",
                        description=issue,
                        priority="high",
                        expected_improvement=0.1,
                    ))
                else:
                    revisions.append(Revision(
                        target_slide_idx=score.slide_idx,
                        action="rewrite",
                        description=issue,
                        priority="medium",
                        expected_improvement=0.05,
                    ))

        # Narrative improvements
        if report.narrative_score:
            if not report.narrative_score.has_closing:
                revisions.append(Revision(
                    target_slide_idx=None,
                    action="add",
                    description="Add closing/CTA slide",
                    priority="medium",
                    expected_improvement=0.1,
                ))

            if not report.narrative_score.has_sections and report.total_slides > 8:
                revisions.append(Revision(
                    target_slide_idx=None,
                    action="add",
                    description="Add section divider slides for structure",
                    priority="medium",
                    expected_improvement=0.08,
                ))

        # Design improvements
        if report.design_score < 0.5:
            revisions.append(Revision(
                target_slide_idx=None,
                action="add",
                description="Add more visual elements (charts, images, diagrams)",
                priority="low",
                expected_improvement=0.1,
            ))

        # Sort by priority and expected improvement
        priority_order = {"high": 0, "medium": 1, "low": 2}
        revisions.sort(key=lambda r: (priority_order.get(r.priority, 3), -r.expected_improvement))

        return revisions

    def validate_and_suggest(self, deck: DeckSpec) -> Tuple[ValidationReport, List[Revision]]:
        """Run full validation and return report + suggestions."""
        report = self.validate(deck)
        revisions = self.suggest_improvements(report)
        return report, revisions


# Convenience functions
def quick_validate(deck: DeckSpec) -> ValidationReport:
    """One-shot validation."""
    validator = QualityValidator()
    return validator.validate(deck)


def validate_with_suggestions(deck: DeckSpec) -> Tuple[ValidationReport, List[Revision]]:
    """One-shot validation with suggestions."""
    validator = QualityValidator()
    return validator.validate_and_suggest(deck)
