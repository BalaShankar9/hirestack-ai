"""
S15-P4: tests for the PPT integration layer (intent detection, tool
registry, storage helper).
"""
from __future__ import annotations

import base64

import pytest

pytest.importorskip("pptx")

from ai_engine.agents.ppt import (  # noqa: E402
    build_ppt_tools,
    detect_ppt_intent,
    generate_and_store_pptx,
)
from ai_engine.agents.ppt.integration import _safe_storage_path  # noqa: E402

async_test = pytest.mark.asyncio


# ─── intent detection ────────────────────────────────────────────────

def test_intent_basic_pitch_deck():
    out = detect_ppt_intent("Make a pitch deck about HireStack AI for investors")
    assert out is not None
    assert "hirestack ai" in out["topic"].lower()
    assert out["audience"] == "investors"


def test_intent_with_slide_count():
    out = detect_ppt_intent("Build a 12 slide PowerPoint about quarterly OKRs")
    assert out is not None
    assert out["slide_count"] == 12
    assert "okrs" in out["topic"].lower() or "okr" in out["topic"].lower()


def test_intent_clamps_slide_count():
    out = detect_ppt_intent("Make a 99 slide presentation about cats")
    assert out is not None
    assert out["slide_count"] == 30  # clamped


def test_intent_negative_for_unrelated_message():
    assert detect_ppt_intent("What is the weather today?") is None
    assert detect_ppt_intent("Refactor my code please") is None
    assert detect_ppt_intent("") is None


def test_intent_strong_noun_alone_is_enough():
    out = detect_ppt_intent("I want a pitch deck about climate tech")
    assert out is not None
    assert "climate tech" in out["topic"].lower()


# ─── safe storage path ───────────────────────────────────────────────

def test_safe_storage_path_normalizes():
    p = _safe_storage_path("HireStack AI: Investor Deck!")
    assert p.endswith(".pptx")
    assert " " not in p
    assert p.lower() == p


# ─── tool registry ───────────────────────────────────────────────────

def test_build_ppt_tools_registers_generate_ppt():
    reg = build_ppt_tools()
    tool = reg.get("generate_ppt")
    assert tool is not None
    assert tool.name == "generate_ppt"
    assert "topic" in tool.parameters["properties"]
    assert "topic" in tool.parameters["required"]


# ─── generate_and_store_pptx (no storage) ────────────────────────────

@async_test
async def test_generate_and_store_returns_b64_when_no_storage():
    out = await generate_and_store_pptx(
        topic="Test Topic", slide_count=4, inline_b64=False,
    )
    assert out["ok"] is True
    assert out["slide_count"] >= 3
    assert out["url"] is None
    # No storage was provided, so we always return bytes_b64.
    assert out["bytes_b64"] is not None
    raw = base64.b64decode(out["bytes_b64"])
    assert raw[:2] == b"PK"  # .pptx is a zip


@async_test
async def test_generate_and_store_validation_error_on_blank_topic():
    out = await generate_and_store_pptx(topic="   ")
    assert out["ok"] is False
    assert "topic" in (out["error"] or "").lower()


# ─── generate_and_store_pptx with stub storage ───────────────────────

class _StubBucket:
    def __init__(self) -> None:
        self.uploaded = None

    def upload(self, path, data, opts=None):
        self.uploaded = (path, len(data), opts)
        return {"path": path}

    def get_public_url(self, path):
        return f"https://stub.example.com/ppt/{path}"


class _StubStorage:
    def __init__(self) -> None:
        self.bucket = _StubBucket()

    def from_(self, _bucket_name):
        return self.bucket


@async_test
async def test_generate_and_store_uploads_via_supabase_style_client():
    stub = _StubStorage()
    out = await generate_and_store_pptx(
        topic="Investor Deck", slide_count=3,
        storage_client=stub, storage_bucket="ppt-exports",
    )
    assert out["ok"] is True
    assert out["url"] == "https://stub.example.com/ppt/investor_deck.pptx"
    # bytes_b64 should NOT be inlined when an upload succeeded and inline_b64=False
    assert out["bytes_b64"] is None
    assert stub.bucket.uploaded is not None
    path, n_bytes, _opts = stub.bucket.uploaded
    assert path == "investor_deck.pptx"
    assert n_bytes > 5000


@async_test
async def test_generate_and_store_inline_b64_overrides_to_include_bytes():
    stub = _StubStorage()
    out = await generate_and_store_pptx(
        topic="Inline Test", slide_count=3,
        storage_client=stub, inline_b64=True,
    )
    assert out["ok"] is True
    assert out["url"] is not None
    assert out["bytes_b64"] is not None  # inline forced even with successful upload
