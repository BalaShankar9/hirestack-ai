"""
ImageFetcher — stock-image resolver for PPT slides.

Tries Unsplash → Pexels in order based on which API keys are present in
env (UNSPLASH_ACCESS_KEY, PEXELS_API_KEY). When neither is configured,
or every search fails, returns None so the SlideComposer's placeholder
card is drawn instead — never raises into the orchestrator.

Public API:
    ImageFetcher().resolve(image_spec: ImageSpec) -> Optional[bytes]

Caching:
    Per-process LRU on (provider, normalized_query). Same query + provider
    won't be re-hit within the process lifetime.

Network safety:
    Uses httpx.AsyncClient with a strict 8s timeout. Any HTTPError /
    JSONError / IOError is swallowed; we just fall back to the next
    provider or to None.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ai_engine.agents.ppt.schemas import ImageSpec

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
_USER_AGENT = "HireStack-AI-PPT/1.0 (+https://hirestack.ai)"


class ImageFetcher:
    """Resolve an ImageSpec to PNG/JPEG bytes via stock-image providers."""

    def __init__(
        self,
        *,
        unsplash_key: Optional[str] = None,
        pexels_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        cache_size: int = 128,
    ) -> None:
        self._unsplash_key = unsplash_key or os.getenv("UNSPLASH_ACCESS_KEY")
        self._pexels_key = pexels_key or os.getenv("PEXELS_API_KEY")
        self._owns_client = client is None
        self._client = client
        self._cache: Dict[Tuple[str, str], bytes] = {}
        self._cache_max = max(8, cache_size)

    # ─── public ───────────────────────────────────────────────────────
    async def resolve(self, image_spec: ImageSpec) -> Optional[bytes]:
        """Return image bytes for the given spec, or None on failure."""
        # 1) explicit url wins.
        if image_spec.url:
            data = await self._download(image_spec.url)
            if data:
                return data

        query = (image_spec.query or "").strip()
        if not query:
            return None

        # 2) try providers in order of available keys.
        for provider in self._provider_order():
            cache_key = (provider, query.lower())
            if cache_key in self._cache:
                return self._cache[cache_key]
            try:
                data = await self._search_one(provider, query)
            except Exception as exc:  # noqa: BLE001
                logger.debug("image_search_failed: provider=%s err=%s", provider, str(exc)[:160])
                data = None
            if data:
                self._store_cache(cache_key, data)
                return data

        return None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ─── provider routing ────────────────────────────────────────────
    def _provider_order(self) -> List[str]:
        out: List[str] = []
        if self._unsplash_key:
            out.append("unsplash")
        if self._pexels_key:
            out.append("pexels")
        return out

    def has_any_provider(self) -> bool:
        return bool(self._provider_order())

    # ─── per-provider ────────────────────────────────────────────────
    async def _search_one(self, provider: str, query: str) -> Optional[bytes]:
        if provider == "unsplash":
            url = await self._unsplash_pick_url(query)
        elif provider == "pexels":
            url = await self._pexels_pick_url(query)
        else:
            return None
        if not url:
            return None
        return await self._download(url)

    async def _unsplash_pick_url(self, query: str) -> Optional[str]:
        client = await self._get_client()
        resp = await client.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            headers={
                "Authorization": f"Client-ID {self._unsplash_key}",
                "Accept-Version": "v1",
                "User-Agent": _USER_AGENT,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        results: List[Dict[str, Any]] = payload.get("results") or []
        if not results:
            return None
        first = results[0]
        urls = first.get("urls") or {}
        return urls.get("regular") or urls.get("full") or urls.get("small")

    async def _pexels_pick_url(self, query: str) -> Optional[str]:
        client = await self._get_client()
        resp = await client.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            headers={
                "Authorization": self._pexels_key or "",
                "User-Agent": _USER_AGENT,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        photos: List[Dict[str, Any]] = payload.get("photos") or []
        if not photos:
            return None
        src = photos[0].get("src") or {}
        return src.get("large") or src.get("original") or src.get("medium")

    # ─── http helpers ────────────────────────────────────────────────
    async def _download(self, url: str) -> Optional[bytes]:
        try:
            client = await self._get_client()
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            data = resp.content
            if not data or len(data) < 200:
                return None
            return data
        except Exception as exc:  # noqa: BLE001
            logger.debug("image_download_failed: url=%s err=%s", url[:120], str(exc)[:160])
            return None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT,
                                             headers={"User-Agent": _USER_AGENT})
            self._owns_client = True
        return self._client

    # ─── cache ───────────────────────────────────────────────────────
    def _store_cache(self, key: Tuple[str, str], data: bytes) -> None:
        if len(self._cache) >= self._cache_max:
            # naive: drop one arbitrary entry
            try:
                self._cache.pop(next(iter(self._cache)))
            except StopIteration:
                pass
        self._cache[key] = data
