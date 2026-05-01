"""S17-P3 — Deterministic theme palette + CSS generator."""
from __future__ import annotations

from typing import Dict

_PALETTES: Dict[str, Dict[str, str]] = {
    "minimal": {
        "bg": "#ffffff", "fg": "#1a1a1a", "muted": "#6b7280",
        "accent": "#111827", "card": "#fafafa", "border": "#e5e7eb",
        "font": "'Inter', system-ui, sans-serif",
    },
    "professional": {
        "bg": "#f9fafb", "fg": "#0f172a", "muted": "#475569",
        "accent": "#2563eb", "card": "#ffffff", "border": "#e2e8f0",
        "font": "'Source Sans 3', 'Inter', system-ui, sans-serif",
    },
    "creative": {
        "bg": "#0f0f23", "fg": "#f8f8f2", "muted": "#a6acd9",
        "accent": "#ff79c6", "card": "#1a1b3a", "border": "#2a2b5e",
        "font": "'Poppins', 'Inter', sans-serif",
    },
    "developer": {
        "bg": "#0d1117", "fg": "#c9d1d9", "muted": "#8b949e",
        "accent": "#58a6ff", "card": "#161b22", "border": "#30363d",
        "font": "'JetBrains Mono', 'Menlo', monospace",
    },
}


class ThemeEngine:
    @staticmethod
    def palette(theme: str) -> Dict[str, str]:
        return _PALETTES.get(theme, _PALETTES["professional"])

    @classmethod
    def css(cls, theme: str) -> str:
        p = cls.palette(theme)
        return (
            ":root{"
            f"--bg:{p['bg']};--fg:{p['fg']};--muted:{p['muted']};"
            f"--accent:{p['accent']};--card:{p['card']};--border:{p['border']};"
            f"--font:{p['font']};"
            "}"
            "*{box-sizing:border-box}"
            "body{margin:0;font-family:var(--font);color:var(--fg);"
            "background:var(--bg);line-height:1.55;}"
            ".container{max-width:880px;margin:0 auto;padding:48px 24px;}"
            "header.hero{padding:64px 0 32px;}"
            "header.hero h1{font-size:2.5rem;margin:0 0 8px;}"
            "header.hero p.headline{color:var(--muted);font-size:1.15rem;"
            "margin:0;}"
            "section{padding:32px 0;border-top:1px solid var(--border);}"
            "section h2{font-size:1.5rem;margin:0 0 16px;}"
            ".card{background:var(--card);border:1px solid var(--border);"
            "border-radius:8px;padding:16px;margin-bottom:12px;}"
            ".card h3{margin:0 0 4px;font-size:1.1rem;}"
            ".card .meta{color:var(--muted);font-size:0.9rem;margin:0 0 8px;}"
            "a{color:var(--accent);text-decoration:none;}"
            "a:hover{text-decoration:underline;}"
            "ul{padding-left:20px;margin:8px 0;}"
            ".tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;}"
            ".tag{background:var(--bg);border:1px solid var(--border);"
            "padding:2px 8px;border-radius:4px;font-size:0.8rem;"
            "color:var(--muted);}"
            "footer{padding:32px 0;color:var(--muted);font-size:0.85rem;"
            "border-top:1px solid var(--border);text-align:center;}"
        )
