"""S18 — Report Quality Scoring for Recon Swarm.

Provides comprehensive quality metrics for recon reports to enable
comparisons and track improvements over time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from .schemas import CompanyIntelV2, IntelField, ReconSwarmReport


@dataclass(frozen=True)
class QualityScore:
    """Comprehensive quality score for a recon report.
    
    Attributes:
        overall_score: Weighted composite score (0-1)
        completeness: Field coverage ratio (0-1)
        confidence_ratio: High confidence fields ratio (0-1)
        source_diversity: Unique sources ratio (0-1)
        provider_success_rate: Successful provider calls ratio (0-1)
        reliability_tier: Human-readable tier (high/medium/low)
        field_breakdown: Per-category field counts
        recommendations: Suggestions for improvement
    """
    overall_score: float
    completeness: float
    confidence_ratio: float
    source_diversity: float
    provider_success_rate: float
    reliability_tier: Literal["high", "medium", "low", "unknown"]
    field_breakdown: Dict[str, int]
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall_score": round(self.overall_score, 3),
            "completeness": round(self.completeness, 3),
            "confidence_ratio": round(self.confidence_ratio, 3),
            "source_diversity": round(self.source_diversity, 3),
            "provider_success_rate": round(self.provider_success_rate, 3),
            "reliability_tier": self.reliability_tier,
            "field_breakdown": self.field_breakdown,
            "recommendations": self.recommendations,
        }


class QualityScorer:
    """Score the quality of recon reports.
    
    Calculates multiple quality dimensions:
    1. Completeness: How many fields have data
    2. Confidence: Ratio of high-confidence fields
    3. Source Diversity: Number of unique sources
    4. Provider Success: Call success rate
    
    Example:
        scorer = QualityScorer()
        score = scorer.score(report)
        print(f"Quality: {score.overall_score:.1%} ({score.reliability_tier})")
    """
    
    # Weights for composite score calculation
    DEFAULT_WEIGHTS = {
        "completeness": 0.30,
        "confidence": 0.30,
        "source_diversity": 0.20,
        "provider_success": 0.20,
    }
    
    # Field categories for breakdown
    FIELD_CATEGORIES = {
        "overview": [
            "legal_name", "website", "description", "industry",
            "sub_industries", "headquarters", "founded_year", "company_stage",
        ],
        "funding": [
            "total_funding_usd", "last_round", "last_round_date",
            "investors", "valuation_usd", "is_public", "ticker",
        ],
        "people": [
            "headcount", "eng_headcount", "leadership",
            "hiring_managers", "open_roles_count",
        ],
        "tech": [
            "tech_stack", "products", "github_orgs",
            "repo_count", "languages",
        ],
        "market": [
            "competitors", "recent_news", "product_launches",
            "patents_count", "research_papers",
        ],
        "reputation": [
            "glassdoor_rating", "glassdoor_themes",
            "twitter_handle", "twitter_sentiment",
        ],
        "culture": [
            "values", "benefits", "work_style",
        ],
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize quality scorer.
        
        Args:
            weights: Optional custom weights for scoring components
        """
        self._weights = weights or self.DEFAULT_WEIGHTS
    
    def score(self, report: ReconSwarmReport) -> QualityScore:
        """Calculate quality score for a report.
        
        Args:
            report: The recon swarm report to score
            
        Returns:
            QualityScore with comprehensive metrics
        """
        intel = report.intel
        
        # Calculate component scores
        completeness = self._calculate_completeness(intel)
        confidence_ratio = self._calculate_confidence(intel)
        source_diversity = self._calculate_source_diversity(intel)
        provider_success = self._calculate_provider_success(report)
        
        # Weighted overall score
        overall = (
            completeness * self._weights["completeness"] +
            confidence_ratio * self._weights["confidence"] +
            source_diversity * self._weights["source_diversity"] +
            provider_success * self._weights["provider_success"]
        )
        
        # Determine reliability tier
        tier = self._determine_tier(
            overall, completeness, confidence_ratio
        )
        
        # Field breakdown by category
        breakdown = self._calculate_breakdown(intel)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            completeness, confidence_ratio, source_diversity,
            provider_success, intel
        )
        
        return QualityScore(
            overall_score=round(overall, 3),
            completeness=round(completeness, 3),
            confidence_ratio=round(confidence_ratio, 3),
            source_diversity=round(source_diversity, 3),
            provider_success_rate=round(provider_success, 3),
            reliability_tier=tier,
            field_breakdown=breakdown,
            recommendations=recommendations,
        )
    
    def _calculate_completeness(self, intel: CompanyIntelV2) -> float:
        """Calculate field coverage ratio.
        
        Returns:
            Ratio of populated fields (0-1)
        """
        # Get all IntelField attributes
        fields = [
            getattr(intel, attr) for attr in dir(intel)
            if isinstance(getattr(intel, attr, None), IntelField)
        ]
        
        if not fields:
            return 0.0
        
        populated = 0
        for field in fields:
            value = field.value
            if value is not None:
                if isinstance(value, (list, dict)) and not value:
                    continue  # Empty list/dict doesn't count
                populated += 1
        
        return populated / len(fields)
    
    def _calculate_confidence(self, intel: CompanyIntelV2) -> float:
        """Calculate high confidence field ratio.
        
        Returns:
            Ratio of fields with high confidence (0-1)
        """
        fields = [
            getattr(intel, attr) for attr in dir(intel)
            if isinstance(getattr(intel, attr, None), IntelField)
        ]
        
        if not fields:
            return 0.0
        
        high_confidence = sum(
            1 for f in fields
            if f.confidence == "high" and f.value is not None
        )
        
        # Only count fields that have values
        valued_fields = sum(
            1 for f in fields
            if f.value is not None and (
                not isinstance(f.value, (list, dict)) or f.value
            )
        )
        
        return high_confidence / valued_fields if valued_fields > 0 else 0.0
    
    def _calculate_source_diversity(self, intel: CompanyIntelV2) -> float:
        """Calculate source diversity score.
        
        Returns:
            Normalized unique source count (0-1, maxes at 5+ sources)
        """
        sources = set()
        
        fields = [
            getattr(intel, attr) for attr in dir(intel)
            if isinstance(getattr(intel, attr, None), IntelField)
        ]
        
        for field in fields:
            sources.update(field.sources)
        
        # Normalize: 5+ sources = 1.0
        return min(len(sources) / 5.0, 1.0)
    
    def _calculate_provider_success(self, report: ReconSwarmReport) -> float:
        """Calculate provider call success rate.
        
        Returns:
            Ratio of successful provider calls (0-1)
        """
        results = report.provider_results
        if not results:
            return 0.0
        
        successful = sum(1 for r in results if r.success)
        return successful / len(results)
    
    def _determine_tier(
        self,
        overall: float,
        completeness: float,
        confidence: float,
    ) -> Literal["high", "medium", "low", "unknown"]:
        """Determine reliability tier.
        
        Criteria:
        - High: overall >= 0.8, completeness >= 0.7
        - Medium: overall >= 0.5
        - Low: overall < 0.5
        - Unknown: no data
        """
        if overall == 0 and completeness == 0:
            return "unknown"
        
        if overall >= 0.8 and completeness >= 0.7:
            return "high"
        
        if overall >= 0.5:
            return "medium"
        
        return "low"
    
    def _calculate_breakdown(self, intel: CompanyIntelV2) -> Dict[str, int]:
        """Calculate field counts per category.
        
        Returns:
            Dict mapping category to populated field count
        """
        breakdown = {}
        
        for category, fields in self.FIELD_CATEGORIES.items():
            count = 0
            for field_name in fields:
                field = getattr(intel, field_name, None)
                if isinstance(field, IntelField):
                    value = field.value
                    if value is not None:
                        if isinstance(value, (list, dict)) and not value:
                            continue
                        count += 1
            breakdown[category] = count
        
        return breakdown
    
    def _generate_recommendations(
        self,
        completeness: float,
        confidence: float,
        source_diversity: float,
        provider_success: float,
        intel: CompanyIntelV2,
    ) -> List[str]:
        """Generate improvement recommendations.
        
        Returns:
            List of actionable recommendations
        """
        recommendations = []
        
        if completeness < 0.5:
            recommendations.append(
                "Low field coverage: Consider enabling additional provider sources"
            )
        
        if confidence < 0.3:
            recommendations.append(
                "Low confidence: Multiple conflicting sources detected; "
                "verify key facts manually"
            )
        
        if source_diversity < 0.4:
            recommendations.append(
                "Limited source diversity: Add more provider types for cross-validation"
            )
        
        if provider_success < 0.7:
            recommendations.append(
                f"Provider failures ({(1-provider_success):.0%}): "
                "Check provider health and API keys"
            )
        
        # Check for specific missing critical fields
        if not intel.description.value:
            recommendations.append("Missing company description: Enable description synthesis")
        
        if not intel.headcount.value:
            recommendations.append("Missing headcount: Enable LinkedIn or similar provider")
        
        if not intel.tech_stack.value:
            recommendations.append("Missing tech stack: Enable BuiltWith or GitHub provider")
        
        return recommendations
