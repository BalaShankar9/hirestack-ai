"""
S15-P3: tests for the stock-image fetcher.

Strategy: never hit the real network. Use httpx.MockTransport to stub
search and download endpoints, and verify:
- No-key configuration -> resolve() returns None and has_any_provider() is False.
- Unsplash search hit -> bytes returned, cached on second call.
- Unsplash empty results -> falls through to Pexels.
- Both providers fail -> returns None (graceful, no raise).
- Direct image_spec.url path bypasses provider search.
- Tiny / empty download bodies are rejected.
"""
from __future__ import annotations

from typing import Callable, Dict

import httpx
import pytest

pytestmark = pytest.mark.asyncio

from ai_engine.agents.ppt.image_fetcher import ImageFetcher  # noqa: E402
from ai_engine.agents.ppt.ai_image_generator import (  # noqa: E402
    AIImageGenerator,
    GenerationResult,
)
from ai_engine.agents.ppt.schemas import ImageSpec  # noqa: E402


PNG_SIG = b"\x89PNG\r\n\x1a\n"
FAKE_PNG = PNG_SIG + b"\x00" * 1024  # comfortably > 200 bytes


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ─── no providers configured ──────────────────────────────────────────

async def test_no_keys_returns_none(monkeypatch):
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    fetcher = ImageFetcher()
    assert fetcher.has_any_provider() is False
    out = await fetcher.resolve(ImageSpec(query="diverse engineering team"))
    assert out is None


# ─── Unsplash happy path + cache ──────────────────────────────────────

async def test_unsplash_search_returns_bytes_and_caches():
    calls: Dict[str, int] = {"search": 0, "download": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if "api.unsplash.com" in req.url.host:
            calls["search"] += 1
            return httpx.Response(200, json={"results": [
                {"urls": {"regular": "https://images.example.com/p.jpg"}}
            ]})
        if "images.example.com" in req.url.host:
            calls["download"] += 1
            return httpx.Response(200, content=FAKE_PNG,
                                  headers={"content-type": "image/png"})
        return httpx.Response(404)

    fetcher = ImageFetcher(unsplash_key="UK", client=_make_client(handler))
    spec = ImageSpec(query="engineering team")

    a = await fetcher.resolve(spec)
    assert a == FAKE_PNG
    assert calls == {"search": 1, "download": 1}

    # second call must be served from cache — no extra network hits.
    b = await fetcher.resolve(spec)
    assert b == FAKE_PNG
    assert calls == {"search": 1, "download": 1}

    await fetcher.aclose()


# ─── Unsplash empty -> Pexels fallback ────────────────────────────────

async def test_unsplash_empty_falls_back_to_pexels():
    def handler(req: httpx.Request) -> httpx.Response:
        if "api.unsplash.com" in req.url.host:
            return httpx.Response(200, json={"results": []})
        if "api.pexels.com" in req.url.host:
            return httpx.Response(200, json={"photos": [
                {"src": {"large": "https://cdn.pexels.com/x.jpg"}}
            ]})
        if "cdn.pexels.com" in req.url.host:
            return httpx.Response(200, content=FAKE_PNG)
        return httpx.Response(404)

    fetcher = ImageFetcher(unsplash_key="UK", pexels_key="PK",
                           client=_make_client(handler))
    out = await fetcher.resolve(ImageSpec(query="modern dashboard"))
    assert out == FAKE_PNG
    await fetcher.aclose()


# ─── both providers error -> graceful None ────────────────────────────

async def test_both_providers_error_returns_none():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    fetcher = ImageFetcher(unsplash_key="UK", pexels_key="PK",
                           client=_make_client(handler))
    out = await fetcher.resolve(ImageSpec(query="anything"))
    assert out is None
    await fetcher.aclose()


# ─── explicit url short-circuits ─────────────────────────────────────

async def test_explicit_url_bypasses_search():
    def handler(req: httpx.Request) -> httpx.Response:
        if "api.unsplash.com" in req.url.host or "api.pexels.com" in req.url.host:
            raise AssertionError("search should not be called when url is given")
        if "direct.example.com" in req.url.host:
            return httpx.Response(200, content=FAKE_PNG)
        return httpx.Response(404)

    fetcher = ImageFetcher(unsplash_key="UK", client=_make_client(handler))
    out = await fetcher.resolve(ImageSpec(query="ignored", url="https://direct.example.com/p.png"))
    assert out == FAKE_PNG
    await fetcher.aclose()


# ─── trivially small bodies are rejected ─────────────────────────────

async def test_tiny_body_rejected():
    def handler(req: httpx.Request) -> httpx.Response:
        if "api.unsplash.com" in req.url.host:
            return httpx.Response(200, json={"results": [
                {"urls": {"regular": "https://images.example.com/tiny.jpg"}}
            ]})
        return httpx.Response(200, content=b"x")  # 1-byte body
    fetcher = ImageFetcher(unsplash_key="UK", client=_make_client(handler))
    out = await fetcher.resolve(ImageSpec(query="x"))
    assert out is None
    await fetcher.aclose()


# ─── empty query + no url returns None ────────────────────────────────

async def test_empty_query_returns_none():
    fetcher = ImageFetcher(unsplash_key="UK", client=_make_client(lambda r: httpx.Response(404)))
    out = await fetcher.resolve(ImageSpec(query="   "))
    assert out is None
    await fetcher.aclose()


# ─── orchestrator default wires ImageFetcher in ───────────────────────

async def test_orchestrator_default_image_resolver_wired():
    from ai_engine.agents.ppt import PPTOrchestrator
    orch = PPTOrchestrator()
    assert orch.composer.image_resolver is not None


async def test_ai_image_generator_stability_fallback_caches_image_bytes():
    class StabilityOnlyGenerator(AIImageGenerator):
        def __init__(self):
            super().__init__(openai_key=None, stability_key="stability-test-key")
            self.calls = 0

        async def _generate_stability(self, prompt: str, size: str) -> GenerationResult:
            self.calls += 1
            return GenerationResult(
                image_bytes=FAKE_PNG,
                prompt_used=prompt,
                model="stable-diffusion-xl",
                generation_time_ms=5,
            )

    generator = StabilityOnlyGenerator()

    first = await generator.generate_illustration("academic poster concept", style="minimal")
    second = await generator.generate_illustration("academic poster concept", style="minimal")

    assert first == FAKE_PNG
    assert second == FAKE_PNG
    assert generator.calls == 1
