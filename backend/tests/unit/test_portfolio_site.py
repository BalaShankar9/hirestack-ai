"""S17-P3 — Portfolio Site Generator tests."""
from __future__ import annotations

import pytest

from ai_engine.agents.portfolio import (
    PortfolioInput,
    SiteGenerator,
    build_portfolio_tools,
    detect_portfolio_intent,
    generate_portfolio_site,
)
from ai_engine.agents.portfolio.schemas import (
    ExperienceEntry,
    ProjectEntry,
)
from ai_engine.agents.portfolio.section_builder import SectionBuilder, slugify
from ai_engine.agents.portfolio.theme_engine import ThemeEngine


# ─── stub LLM ──────────────────────────────────────────────────────

class _StubClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def complete_json(self, **kwargs):
        self.calls += 1
        return self._payload


class _RaisingClient:
    async def complete_json(self, **kwargs):
        raise RuntimeError("no llm")


def _sample_input(theme="professional", **overrides) -> PortfolioInput:
    base = dict(
        candidate_name="Ada Lovelace",
        headline="Engineer of analytical machines",
        summary="Mathematician shipping early algorithms.",
        contact={"email": "ada@example.com", "github": "https://github.com/ada"},
        projects=[
            ProjectEntry(
                title="Analytical Engine notes",
                description="First algorithm intended for a machine.",
                tech_stack=["math", "punch cards"],
                link="https://example.com/notes",
            ),
        ],
        experience=[
            ExperienceEntry(
                company="Royal Society",
                role="Analyst",
                start="1840",
                end="1843",
                bullets=["Translated Menabrea memoir", "Authored Note G"],
            ),
        ],
        skills=["analysis", "writing", "algorithms"],
        theme=theme,
    )
    base.update(overrides)
    return PortfolioInput(**base)


# ─── intent ────────────────────────────────────────────────────────

def test_intent_positive():
    assert detect_portfolio_intent("Generate a portfolio site for me")
    assert detect_portfolio_intent("Build my personal website")


def test_intent_negative():
    assert detect_portfolio_intent("How do I write a cover letter?") is None
    assert detect_portfolio_intent("") is None


# ─── theme engine ─────────────────────────────────────────────────

def test_theme_engine_known_palette():
    p = ThemeEngine.palette("developer")
    assert p["bg"] == "#0d1117"
    css = ThemeEngine.css("developer")
    assert "--bg:#0d1117" in css


def test_theme_engine_falls_back_for_unknown():
    p = ThemeEngine.palette("nonexistent")
    assert p == ThemeEngine.palette("professional")


# ─── section builder ──────────────────────────────────────────────

def test_section_builder_escapes_html():
    inp = _sample_input(candidate_name="<script>alert(1)</script>")
    s = SectionBuilder.hero(inp)
    assert "<script>" not in s.html
    assert "&lt;script&gt;" in s.html


def test_section_builder_handles_empty_collections():
    inp = _sample_input(projects=[], experience=[], skills=[], contact={})
    sb = SectionBuilder()
    for sec in [sb.projects([]), sb.experience([]), sb.skills([]),
                sb.contact(inp)]:
        assert "Coming soon" in sec.html or "preferred channel" in sec.html


def test_slugify_basic():
    assert slugify("Ada Lovelace") == "ada-lovelace"
    assert slugify("  ") == "portfolio"


# ─── site generator ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_site_deterministic_no_llm():
    inp = _sample_input()
    site = await SiteGenerator().generate(inp)
    assert site.theme == "professional"
    assert site.slug == "ada-lovelace"
    assert "<!doctype html>" in site.html
    assert "Ada Lovelace" in site.html
    assert "Analytical Engine notes" in site.html
    assert "Royal Society" in site.html
    # All six sections present
    assert len(site.sections) == 6
    assert site.metadata["project_count"] == "1"


@pytest.mark.asyncio
async def test_generate_site_uses_llm_headline_when_blank():
    inp = _sample_input(headline="")
    client = _StubClient({"headline": "LLM-CRAFTED HEADLINE"})
    site = await SiteGenerator(ai_client=client).generate(inp)
    assert client.calls == 1
    assert "LLM-CRAFTED HEADLINE" in site.html


@pytest.mark.asyncio
async def test_generate_site_skips_llm_when_headline_present():
    inp = _sample_input(headline="Fixed headline")
    client = _StubClient({"headline": "should-not-appear"})
    site = await SiteGenerator(ai_client=client).generate(inp)
    assert client.calls == 0
    assert "Fixed headline" in site.html


@pytest.mark.asyncio
async def test_generate_site_falls_back_when_llm_raises():
    inp = _sample_input(headline="")
    site = await SiteGenerator(ai_client=_RaisingClient()).generate(inp)
    # Falls back to deterministic default headline
    assert "Builder. Operator. Engineer." in site.html


@pytest.mark.asyncio
async def test_generate_rejects_empty_name():
    inp = _sample_input(candidate_name="   ")
    with pytest.raises(ValueError):
        await SiteGenerator().generate(inp)


# ─── e2e + tool registry ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_portfolio_site_helper_accepts_dict():
    site = await generate_portfolio_site(
        {"candidate_name": "Grace Hopper", "skills": ["compilers"]}
    )
    assert site.slug == "grace-hopper"


def test_build_portfolio_tools_registers():
    reg = build_portfolio_tools()
    tool = reg.get("generate_portfolio_site")
    assert tool is not None
    assert "input" in tool.parameters["required"]
