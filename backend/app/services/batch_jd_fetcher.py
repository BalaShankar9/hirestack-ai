"""B0.fetcher — JD HTML → plaintext.

Two layers:

1. ``extract_jd_text(html)`` — pure-fn HTML → plaintext extractor.
   Strips script/style/nav/header/footer, collapses whitespace,
   returns a clean block suitable for prompting.  Zero I/O.

2. ``make_jd_loader(*, fetcher)`` — JDLoader factory that uses an
   injected Fetcher (same protocol B1.next defined) to GET the URL
   and feed the response body through ``extract_jd_text``.

We deliberately avoid BeautifulSoup as a hard dep — most JD pages
are simple enough that a tag-aware regex pipeline gets us > 95%
quality with zero extra install weight.  The pipeline:

  1. Drop entire <script>/<style>/<noscript> blocks (incl. content).
  2. Drop <nav>/<header>/<footer>/<aside>/<form> blocks.
  3. Replace <br> and block-level openers with newlines.
  4. Strip remaining tags.
  5. Decode HTML entities.
  6. Collapse runs of whitespace; trim each line.
  7. Drop empty lines.

Resilience contract:
- Empty/whitespace input → "" (the glue layer turns this into
  ScoringResult error="jd_empty" via batch_scorer_glue).
- Non-HTML payloads (raw text, JSON, etc.) round-trip cleanly —
  no tags to strip, just whitespace collapse.
- HTTP errors / non-200 status / network failures bubble up from
  the Fetcher as exceptions; the glue layer catches them and tags
  as "jd_fetch_error:*".
"""

from __future__ import annotations

import html
import logging
import re
from typing import Callable, Awaitable, Protocol

from app.services.batch_evaluator import BatchEntry

logger = logging.getLogger(__name__)


# ── HTML strip pure-fn core ──────────────────────────────────────────

# Tags whose ENTIRE subtree we want gone (chrome, scripts, etc.).
_DROP_BLOCK_TAGS = (
    "script", "style", "noscript",
    "nav", "header", "footer", "aside", "form",
    "svg", "iframe", "object", "embed",
)

_DROP_BLOCK_RE = re.compile(
    r"<(" + "|".join(_DROP_BLOCK_TAGS) + r")\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Self-closing or unmatched chrome tags.
_DROP_SELFCLOSE_RE = re.compile(
    r"<(" + "|".join(_DROP_BLOCK_TAGS) + r")\b[^>]*/?>",
    re.IGNORECASE,
)

# Block-level elements — replace opening tag with newline before strip.
_BLOCK_OPEN_RE = re.compile(
    r"<(?:p|div|li|ul|ol|h[1-6]|tr|td|th|section|article|main|"
    r"blockquote|pre|hr|br|/p|/div|/li|/ul|/ol|/h[1-6]|/tr|/td|"
    r"/th|/section|/article|/main|/blockquote|/pre)\b[^>]*/?>",
    re.IGNORECASE,
)

_TAG_RE = re.compile(r"<[^>]+>")

# Cap output to keep prompts predictable; matches MAX_JD_CHARS in
# batch_scorer_core but enforced here too as a defence layer.
MAX_OUTPUT_CHARS = 16000  # generous; core trims further to 8000

_WS_LINE_RE = re.compile(r"[ \t\f\v]+")


def extract_jd_text(html_or_text: str) -> str:
    """Strip a JD HTML payload to clean plaintext.

    Idempotent on already-plain text.  Returns "" for empty/None input.
    """
    if not html_or_text:
        return ""

    s = html_or_text

    # 1. Drop full chrome/script subtrees.
    s = _DROP_BLOCK_RE.sub(" ", s)
    # 2. Drop self-closing chrome tags.
    s = _DROP_SELFCLOSE_RE.sub(" ", s)
    # 3. Insert newlines at block boundaries so paragraphs survive.
    s = _BLOCK_OPEN_RE.sub("\n", s)
    # 4. Strip all remaining tags.
    s = _TAG_RE.sub(" ", s)
    # 5. Decode HTML entities.
    s = html.unescape(s)
    # 6. Per-line whitespace collapse.
    lines = []
    for raw_line in s.split("\n"):
        line = _WS_LINE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)
    out = "\n".join(lines)

    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS].rstrip() + "…"
    return out


# ── glue: Fetcher → JDLoader ─────────────────────────────────────────


class Fetcher(Protocol):
    """Minimal HTTP fetch surface.

    Mirrors the protocol used by ``portal_scanner_worker`` (B1.next)
    so production wiring can share a single httpx-backed implementation.
    """

    async def __call__(self, url: str) -> str: ...


JDLoader = Callable[[BatchEntry], Awaitable[str]]


def make_jd_loader(*, fetcher: Fetcher) -> JDLoader:
    """Build a ``JDLoader`` that fetches+extracts JD text from a URL.

    The returned loader matches the JDLoader Protocol from
    ``batch_scorer_glue`` and can be passed straight to
    ``make_llm_scorer``.

    Failure semantics:
    - Fetcher raises (timeout, 4xx, 5xx) → exception bubbles up;
      ``batch_scorer_glue`` catches and tags as ``jd_fetch_error:*``.
    - Fetcher returns blank → loader returns "" → glue layer tags
      as ``jd_empty``.
    """

    async def _load(entry: BatchEntry) -> str:
        body = await fetcher(entry.canonical_url)
        return extract_jd_text(body or "")

    return _load


__all__ = [
    "MAX_OUTPUT_CHARS",
    "Fetcher",
    "JDLoader",
    "extract_jd_text",
    "make_jd_loader",
]
