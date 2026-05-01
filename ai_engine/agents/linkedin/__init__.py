"""LinkedIn Profile Optimizer agent — S16-P2."""
from ai_engine.agents.linkedin.schemas import (
    HeadlineVariant,
    LinkedInProfile,
    OptimizationResult,
    ProfileScore,
)
from ai_engine.agents.linkedin.ats_scorer import score_profile, score_section
from ai_engine.agents.linkedin.optimizer import LinkedInOptimizer
from ai_engine.agents.linkedin.integration import (
    build_linkedin_tools,
    detect_linkedin_intent,
)

__all__ = [
    "HeadlineVariant",
    "LinkedInProfile",
    "OptimizationResult",
    "ProfileScore",
    "score_profile",
    "score_section",
    "LinkedInOptimizer",
    "build_linkedin_tools",
    "detect_linkedin_intent",
]
