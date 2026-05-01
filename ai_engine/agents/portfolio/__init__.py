"""S17-P3 — Portfolio Site Generator package surface."""
from __future__ import annotations

from .integration import (
    build_portfolio_tools,
    detect_portfolio_intent,
    generate_portfolio_site,
)
from .schemas import (
    ExperienceEntry,
    PortfolioInput,
    PortfolioSection,
    PortfolioSite,
    ProjectEntry,
)
from .section_builder import SectionBuilder
from .site_generator import SiteGenerator
from .theme_engine import ThemeEngine

__all__ = [
    "ExperienceEntry",
    "PortfolioInput",
    "PortfolioSection",
    "PortfolioSite",
    "ProjectEntry",
    "SectionBuilder",
    "SiteGenerator",
    "ThemeEngine",
    "build_portfolio_tools",
    "detect_portfolio_intent",
    "generate_portfolio_site",
]
