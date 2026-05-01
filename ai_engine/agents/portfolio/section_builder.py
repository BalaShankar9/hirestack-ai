"""S17-P3 — Deterministic HTML section builder."""
from __future__ import annotations

from html import escape
from typing import List

from .schemas import (
    ExperienceEntry,
    PortfolioInput,
    PortfolioSection,
    ProjectEntry,
)


def _esc(s: str) -> str:
    return escape((s or "").strip(), quote=True)


def _slugify(name: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in (name or ""))
    out = "-".join(p for p in out.split("-") if p)
    return out or "portfolio"


class SectionBuilder:
    @staticmethod
    def hero(inp: PortfolioInput) -> PortfolioSection:
        name = _esc(inp.candidate_name)
        headline = _esc(inp.headline) or "Builder. Operator. Engineer."
        html = (
            '<header class="hero">'
            f'<h1>{name}</h1>'
            f'<p class="headline">{headline}</p>'
            '</header>'
        )
        return PortfolioSection(id="hero", title=name, html=html)

    @staticmethod
    def about(inp: PortfolioInput) -> PortfolioSection:
        summary = _esc(inp.summary) or (
            "Versatile professional with a track record of shipping "
            "high-impact work."
        )
        html = (
            '<section id="about"><h2>About</h2>'
            f'<p>{summary}</p></section>'
        )
        return PortfolioSection(id="about", title="About", html=html)

    @staticmethod
    def projects(items: List[ProjectEntry]) -> PortfolioSection:
        if not items:
            return PortfolioSection(
                id="projects", title="Projects",
                html='<section id="projects"><h2>Projects</h2>'
                     '<p class="meta">Coming soon.</p></section>',
            )
        cards = []
        for p in items:
            link = _esc(p.link or "")
            title = _esc(p.title)
            head = (
                f'<a href="{link}">{title}</a>' if link else title
            )
            tags = "".join(
                f'<span class="tag">{_esc(t)}</span>' for t in p.tech_stack
            )
            cards.append(
                '<div class="card">'
                f'<h3>{head}</h3>'
                f'<p>{_esc(p.description)}</p>'
                f'<div class="tags">{tags}</div>'
                '</div>'
            )
        html = (
            '<section id="projects"><h2>Projects</h2>'
            + "".join(cards) + '</section>'
        )
        return PortfolioSection(id="projects", title="Projects", html=html)

    @staticmethod
    def experience(items: List[ExperienceEntry]) -> PortfolioSection:
        if not items:
            return PortfolioSection(
                id="experience", title="Experience",
                html='<section id="experience"><h2>Experience</h2>'
                     '<p class="meta">Coming soon.</p></section>',
            )
        cards = []
        for e in items:
            span = " — ".join(filter(None, [_esc(e.start or ""),
                                            _esc(e.end or "Present")]))
            bullets = "".join(
                f'<li>{_esc(b)}</li>' for b in e.bullets
            )
            cards.append(
                '<div class="card">'
                f'<h3>{_esc(e.role)} · {_esc(e.company)}</h3>'
                f'<p class="meta">{span}</p>'
                f'<ul>{bullets}</ul>'
                '</div>'
            )
        html = (
            '<section id="experience"><h2>Experience</h2>'
            + "".join(cards) + '</section>'
        )
        return PortfolioSection(id="experience", title="Experience", html=html)

    @staticmethod
    def skills(items: List[str]) -> PortfolioSection:
        if not items:
            return PortfolioSection(
                id="skills", title="Skills",
                html='<section id="skills"><h2>Skills</h2>'
                     '<p class="meta">Coming soon.</p></section>',
            )
        tags = "".join(
            f'<span class="tag">{_esc(s)}</span>' for s in items
        )
        html = (
            '<section id="skills"><h2>Skills</h2>'
            f'<div class="tags">{tags}</div></section>'
        )
        return PortfolioSection(id="skills", title="Skills", html=html)

    @staticmethod
    def contact(inp: PortfolioInput) -> PortfolioSection:
        if not inp.contact:
            return PortfolioSection(
                id="contact", title="Contact",
                html='<section id="contact"><h2>Contact</h2>'
                     '<p class="meta">Reach out via your preferred channel.'
                     '</p></section>',
            )
        items = []
        for k, v in inp.contact.items():
            label = _esc(k.replace("_", " ").title())
            val = _esc(v)
            if val.startswith("http") or "@" in val:
                href = val if val.startswith("http") else f"mailto:{val}"
                items.append(
                    f'<li><strong>{label}:</strong> '
                    f'<a href="{href}">{val}</a></li>'
                )
            else:
                items.append(f'<li><strong>{label}:</strong> {val}</li>')
        html = (
            '<section id="contact"><h2>Contact</h2>'
            f'<ul>{"".join(items)}</ul></section>'
        )
        return PortfolioSection(id="contact", title="Contact", html=html)


def slugify(name: str) -> str:
    return _slugify(name)
