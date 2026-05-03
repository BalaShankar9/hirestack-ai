"""
PPT integration layer — tool wrapper + intent detection + storage helper.

This is the connective tissue between the elite PPT engine
(ai_engine/agents/ppt/*) and the rest of the platform:

1) detect_ppt_intent(text) → Optional[dict]
   Light heuristic that lets the chat / orchestrator decide
   "is this user asking for a deck?" without hauling in an LLM call.

2) build_ppt_tools() → ToolRegistry
   Exposes PPT generation as an agent-callable tool so future agentic
   flows can request a deck via the same registry pattern as researcher
   / optimizer tools.

3) generate_and_store_pptx(...) → dict
   High-level helper that (a) runs PPTOrchestrator, (b) optionally
   uploads the bytes to Supabase Storage when a client is provided,
   and (c) returns a structured payload with bytes_b64 OR a public URL.

All functions are import-safe even when python-pptx / matplotlib /
supabase are missing — they degrade to {"ok": False, "error": ...}
rather than raising.
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any, Dict, Optional, Tuple

from ai_engine.agents.tools import AgentTool, ToolRegistry

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Intent detection
# ────────────────────────────────────────────────────────────────────

_PPT_KEYWORDS = (
    "powerpoint", "power point", "ppt", "pptx", "slide deck", "slides",
    "presentation", "pitch deck", "investor deck", "keynote deck",
    "sales deck", "deck about", "deck on",
)

_VERB_HINTS = (
    "make", "build", "create", "generate", "produce", "draft", "design",
    "give me a", "i need a",
)

# Capture the topic phrase after "about/on/for".
_TOPIC_RE = re.compile(
    r"\b(?:about|on|for|covering|titled|called)\s+(.{3,200})$",
    re.IGNORECASE,
)


def detect_ppt_intent(text: str) -> Optional[Dict[str, Any]]:
    """
    Classify whether a user message is asking for a PPT deck.

    Returns None when the intent is not detected, otherwise a dict:
        {"topic": str, "slide_count": int|None, "audience": str|None}
    """
    if not text or not isinstance(text, str):
        return None
    lowered = text.lower()
    has_keyword = any(k in lowered for k in _PPT_KEYWORDS)
    has_verb = any(v in lowered for v in _VERB_HINTS)
    if not (has_keyword and has_verb):
        # Be permissive: keyword alone is enough if it's a strong noun.
        if not any(k in lowered for k in ("pitch deck", "slide deck", "powerpoint", "pptx")):
            return None

    topic = _extract_topic(text)
    if not topic:
        return None
    slide_count = _extract_slide_count(lowered)
    audience = _extract_audience(lowered)
    return {
        "topic": topic.strip().rstrip(".!? "),
        "slide_count": slide_count,
        "audience": audience,
    }


def _extract_topic(text: str) -> Optional[str]:
    m = _TOPIC_RE.search(text)
    if m:
        return m.group(1).strip()
    # Fallback: strip the leading verb phrase and keyword and use the rest.
    cleaned = text.strip()
    for kw in _PPT_KEYWORDS:
        cleaned = re.sub(rf"\b{re.escape(kw)}\b", " ", cleaned, flags=re.IGNORECASE)
    for verb in _VERB_HINTS:
        cleaned = re.sub(rf"\b{re.escape(verb)}\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:?!")
    return cleaned or None


_SLIDE_COUNT_RE = re.compile(r"(\d{1,2})\s*(?:slide|page)s?", re.IGNORECASE)


def _extract_slide_count(lowered: str) -> Optional[int]:
    m = _SLIDE_COUNT_RE.search(lowered)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    return max(3, min(30, n))


_AUDIENCE_RE = re.compile(
    r"\bfor\s+(investors?|executives?|engineers?|customers?|the board|"
    r"vcs?|sales|marketing|the team|stakeholders?|leadership)\b",
    re.IGNORECASE,
)


def _extract_audience(lowered: str) -> Optional[str]:
    m = _AUDIENCE_RE.search(lowered)
    if m:
        return m.group(1).lower()
    return None


# ────────────────────────────────────────────────────────────────────
#  Storage helper
# ────────────────────────────────────────────────────────────────────

async def generate_and_store_pptx(
    *,
    topic: str,
    audience: Optional[str] = None,
    slide_count: int = 10,
    tone: Optional[str] = None,
    theme: str = "modern",
    extra_context: Optional[str] = None,
    # Elite features (Phase 3-12)
    enable_data_research: bool = False,
    enable_content_enhancement: bool = False,
    enable_ai_images: bool = False,
    enable_interactive_elements: bool = False,
    target_language: str = "en",
    # Storage
    storage_client: Optional[Any] = None,
    storage_bucket: str = "ppt-exports",
    storage_path: Optional[str] = None,
    inline_b64: bool = False,
) -> Dict[str, Any]:
    """
    Run the PresentationOrchestrator with optional elite features and upload.
    """
    try:
        from ai_engine.agents.ppt import PresentationOrchestrator
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"ppt_engine_unavailable: {exc}"}

    try:
        # Use factory method for configured pipeline
        orch = PresentationOrchestrator.create_with_defaults(
            enable_data_research=enable_data_research,
            enable_content_enhancement=enable_content_enhancement,
            enable_ai_images=enable_ai_images,
            enable_interactive=enable_interactive_elements,
            target_language=target_language,
        )
        result = await orch.generate(
            topic=topic,
            audience=audience,
            slide_count=slide_count,
            tone=tone,
            theme=theme,
            extra_context=extra_context,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("ppt_generate_failed")
        return {"ok": False, "error": f"ppt_generate_failed: {exc}"}

    payload: Dict[str, Any] = {
        "ok": True,
        "topic": topic,
        "slide_count": result.slide_count,
        "size_bytes": result.size_bytes,
        "latency_ms": result.latency_ms,
        "quality_score": result.quality_score,
        "generation_metadata": result.metadata,
        "url": None,
        "bytes_b64": None,
        "error": None,
    }

    uploaded_url = await _upload_if_possible(
        result.pptx_bytes,
        storage_client=storage_client,
        bucket=storage_bucket,
        path=storage_path or _safe_storage_path(topic),
    )
    if uploaded_url:
        payload["url"] = uploaded_url
    if inline_b64 or not uploaded_url:
        payload["bytes_b64"] = base64.b64encode(result.pptx_bytes).decode("ascii")
    return payload


async def _upload_if_possible(
    data: bytes,
    *,
    storage_client: Optional[Any],
    bucket: str,
    path: str,
) -> Optional[str]:
    if storage_client is None:
        return None
    try:
        # Supabase-py-style: storage_client.from_(bucket).upload(path, data, ...)
        if hasattr(storage_client, "from_"):
            uploader = storage_client.from_(bucket)
            res = uploader.upload(
                path, data,
                {"content-type":
                 "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                 "upsert": "true"},
            )
            # Try to read a public url
            if hasattr(uploader, "get_public_url"):
                pub = uploader.get_public_url(path)
                if isinstance(pub, dict):
                    return pub.get("publicURL") or pub.get("data", {}).get("publicUrl")
                return pub
            return getattr(res, "url", None)
        # Generic ".upload(bucket, path, data)" surrogate
        if hasattr(storage_client, "upload"):
            return await _maybe_await(storage_client.upload(bucket, path, data))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ppt_storage_upload_failed: %s", exc)
        return None
    return None


async def _maybe_await(value: Any) -> Any:
    import inspect
    if inspect.isawaitable(value):
        return await value
    return value


_SAFE_FNAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_storage_path(topic: str) -> str:
    base = _SAFE_FNAME.sub("_", topic.strip())[:60].strip("_") or "deck"
    return f"{base.lower()}.pptx"


# ────────────────────────────────────────────────────────────────────
#  Tool registry
# ────────────────────────────────────────────────────────────────────

async def _generate_ppt_tool_fn(**kwargs: Any) -> dict:
    """Tool fn shim — strips storage args by default for safe LLM use."""
    return await generate_and_store_pptx(
        topic=kwargs.get("topic", ""),
        audience=kwargs.get("audience"),
        slide_count=int(kwargs.get("slide_count") or 10),
        tone=kwargs.get("tone"),
        theme=kwargs.get("theme") or "modern",
        extra_context=kwargs.get("extra_context"),
        enable_data_research=bool(kwargs.get("enable_data_research", False)),
        enable_content_enhancement=bool(kwargs.get("enable_content_enhancement", False)),
        enable_ai_images=bool(kwargs.get("enable_ai_images", False)),
        storage_client=kwargs.get("storage_client"),
        storage_bucket=kwargs.get("storage_bucket", "ppt-exports"),
        storage_path=kwargs.get("storage_path"),
        inline_b64=bool(kwargs.get("inline_b64", False)),
    )


def build_ppt_tools() -> ToolRegistry:
    """Tool registry exposing PPT generation to agent flows."""
    reg = ToolRegistry()
    reg.register(AgentTool(
        name="generate_ppt",
        description=(
            "Generate a polished PowerPoint deck about a topic. "
            "Returns metadata plus a URL (when storage configured) or "
            "base64-encoded .pptx bytes. "
            "Elite features: enable_data_research, enable_content_enhancement, enable_ai_images."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Deck subject"},
                "audience": {"type": "string", "description": "Intended audience"},
                "slide_count": {"type": "integer", "description": "3-30 slides", "default": 10},
                "tone": {"type": "string", "description": "Optional tone hint"},
                "theme": {"type": "string", "description": "modern|midnight|warm|minimal|vibrant|corporate", "default": "modern"},
                "extra_context": {"type": "string", "description": "Optional facts/details to include"},
                "enable_data_research": {"type": "boolean", "description": "Enrich charts with real data", "default": False},
                "enable_content_enhancement": {"type": "boolean", "description": "AI-optimize titles and bullets", "default": False},
                "enable_ai_images": {"type": "boolean", "description": "Generate custom AI visuals", "default": False},
            },
            "required": ["topic"],
        },
        fn=_generate_ppt_tool_fn,
    ))
    return reg
