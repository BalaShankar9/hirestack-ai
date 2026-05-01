"""S17-P3 — End-to-end site generator (LLM hero copy + deterministic build)."""
from __future__ import annotations

import json
import logging
from html import escape
from typing import Any, Optional

from .schemas import PortfolioInput, PortfolioSite
from .section_builder import SectionBuilder, slugify
from .theme_engine import ThemeEngine

logger = logging.getLogger(__name__)


class SiteGenerator:
    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self.ai_client = ai_client

    async def _polish_headline(self, inp: PortfolioInput) -> Optional[str]:
        if not self.ai_client or inp.headline:
            return None
        prompt = (
            "Write a single concise portfolio headline (max 90 chars, "
            "no quotes) for this person. Return JSON: {\"headline\": ...}.\n"
            f"Name: {inp.candidate_name}\n"
            f"Summary: {inp.summary}\n"
            f"Skills: {', '.join(inp.skills[:8])}\n"
        )
        try:
            payload = await self.ai_client.complete_json(
                prompt=prompt,
                system="You write tasteful, factual portfolio copy.",
                schema={
                    "type": "object",
                    "properties": {"headline": {"type": "string"}},
                    "required": ["headline"],
                },
                temperature=0.4,
                task_type="portfolio_headline",
            )
            head = (payload or {}).get("headline", "").strip()
            if head and len(head) <= 120:
                return head
        except Exception as exc:  # pragma: no cover - defensive
            logger.info("portfolio headline LLM fallback: %s", exc)
        return None

    async def generate(self, inp: PortfolioInput) -> PortfolioSite:
        if not inp.candidate_name.strip():
            raise ValueError("candidate_name is required")

        polished = await self._polish_headline(inp)
        if polished:
            inp = inp.model_copy(update={"headline": polished})

        sb = SectionBuilder()
        sections = [
            sb.hero(inp),
            sb.about(inp),
            sb.projects(inp.projects),
            sb.experience(inp.experience),
            sb.skills(inp.skills),
            sb.contact(inp),
        ]
        css = ThemeEngine.css(inp.theme)
        body = "".join(s.html for s in sections)
        title = escape(inp.candidate_name + " — Portfolio")
        html = (
            "<!doctype html><html lang=\"en\"><head>"
            "<meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,"
            "initial-scale=1\">"
            f"<title>{title}</title>"
            f"<style>{css}</style>"
            "</head><body>"
            "<div class=\"container\">"
            f"{body}"
            "<footer>Built with HireStack Portfolio Generator.</footer>"
            "</div></body></html>"
        )
        return PortfolioSite(
            theme=inp.theme,
            slug=slugify(inp.candidate_name),
            html=html,
            css=css,
            sections=sections,
            metadata={
                "section_count": str(len(sections)),
                "project_count": str(len(inp.projects)),
                "experience_count": str(len(inp.experience)),
                "skill_count": str(len(inp.skills)),
            },
        )


def _ensure_input(payload: Any) -> PortfolioInput:
    if isinstance(payload, PortfolioInput):
        return payload
    if isinstance(payload, str):
        return PortfolioInput(**json.loads(payload))
    return PortfolioInput(**(payload or {}))
