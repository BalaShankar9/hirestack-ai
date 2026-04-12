"""
HTML sanitization for AI-generated content.

All HTML returned by the AI pipeline passes through ``sanitize_html()``
before reaching the frontend.  This prevents XSS from hallucinated or
injected ``<script>`` / ``on*=`` attributes in generated documents.
"""
from __future__ import annotations

import logging
import re

import nh3

logger = logging.getLogger("hirestack.sanitize")

# Maximum size (bytes) for a single generated HTML document.
# Anything larger is truncated and logged.
MAX_HTML_SIZE = 1_000_000  # 1 MB

# Tags that are legitimate in generated CVs / cover letters / portfolios.
ALLOWED_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr",
    "b", "strong", "i", "em", "u", "s", "mark", "small", "sub", "sup",
    "ul", "ol", "li",
    "a",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "div", "span", "section", "article", "header", "footer", "main", "nav", "aside",
    "blockquote", "pre", "code",
    "img",
    "figure", "figcaption",
    "details", "summary",
    "dl", "dt", "dd",
    "abbr", "cite", "time", "address",
}

# Attributes allowed per-tag.  ``class`` and ``style`` are widely used by
# structured AI output for layout.
ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "*": {"class", "style", "id", "data-section", "data-module", "role", "aria-label"},
    "a": {"href", "target", "title"},
    "img": {"src", "alt", "width", "height", "loading"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "col": {"span"},
    "time": {"datetime"},
    "abbr": {"title"},
    "blockquote": {"cite"},
    "ol": {"start", "type"},
}

# ``href`` / ``src`` schemes allowed (block ``javascript:`` URIs).
ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "data"}


def sanitize_html(html: str, *, max_size: int = MAX_HTML_SIZE) -> str:
    """Sanitize AI-generated HTML, stripping dangerous elements.

    - Removes ``<script>``, ``<iframe>``, ``<object>``, ``<embed>``, ``<form>``
    - Strips all ``on*`` event-handler attributes
    - Blocks ``javascript:`` URIs
    - Truncates to *max_size* bytes with a warning
    """
    if not isinstance(html, str) or not html:
        return ""

    if len(html) > max_size:
        logger.warning("html_truncated: original_size=%d max_size=%d", len(html), max_size)
        html = html[:max_size]

    result = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )

    # nh3 doesn't sanitize CSS — strip javascript: from style attributes
    result = re.sub(
        r'style="[^"]*javascript:[^"]*"',
        'style=""',
        result,
        flags=re.IGNORECASE,
    )

    return result
