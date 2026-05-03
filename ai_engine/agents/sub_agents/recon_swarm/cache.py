"""S18 — In-memory TTL cache for recon swarm results.

Protocol-based so a Redis impl can slot in (follow-up). Default
implementation is a process-local dict + monotonic-clock TTL.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Dict, Optional, Protocol


class IntelCache(Protocol):
    async def get(self, key: str) -> Optional[Dict[str, Any]]: ...
    async def set(self, key: str, value: Dict[str, Any], ttl_s: int) -> None: ...
    async def stats(self) -> Dict[str, int]: ...


class _MemoryCache:
    def __init__(self) -> None:
        self._store: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._store.get(key)
        if not entry:
            self._misses += 1
            return None
        expires, value = entry
        if time.monotonic() >= expires:
            self._store.pop(key, None)
            self._misses += 1
            return None
        self._hits += 1
        return value

    async def set(self, key: str, value: Dict[str, Any], ttl_s: int) -> None:
        self._store[key] = (time.monotonic() + max(1, ttl_s), value)

    async def stats(self) -> Dict[str, int]:
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
        }


_DEFAULT = _MemoryCache()


def get_default_cache() -> IntelCache:
    return _DEFAULT


def cache_key(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return "recon_swarm:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


# ─── Per-Provider Result Cache ────────────────────────────────────

class ProviderCache:
    """Cache for individual provider results.
    
    Caches at the provider+company level to avoid redundant API calls
    when the same company is researched multiple times.
    
    Example:
        cache = ProviderCache(default_ttl_s=3600, max_size=1000)
        
        # Check cache
        result = await cache.get("github", "Stripe")
        if result:
            return result
        
        # Fetch and cache
        result = await provider.fetch(company="Stripe")
        await cache.set("github", "Stripe", result, ttl_s=1800)
    """
    
    def __init__(self, default_ttl_s: float = 3600, max_size: int = 1000):
        """Initialize provider cache.
        
        Args:
            default_ttl_s: Default TTL in seconds for cached entries
            max_size: Maximum number of entries to store (LRU eviction)
        """
        self._default_ttl = default_ttl_s
        self._max_size = max_size
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
    
    def _make_key(self, provider: str, company: str, **ctx) -> str:
        """Create cache key from provider + company + context.
        
        Args:
            provider: Provider name
            company: Company name
            **ctx: Additional context (sorted for consistency)
            
        Returns:
            SHA256 hash as hex string (first 32 chars)
        """
        # Sort context items for consistent hashing
        ctx_str = json.dumps(sorted(ctx.items()), sort_keys=True, default=str)
        key_data = f"{provider}:{company}:{ctx_str}"
        return hashlib.sha256(key_data.encode("utf-8")).hexdigest()[:32]
    
    async def get(
        self,
        provider: str,
        company: str,
        **ctx
    ) -> Optional[Any]:
        """Get cached result if valid.
        
        Args:
            provider: Provider name
            company: Company name
            **ctx: Context (must match set() call)
            
        Returns:
            Cached result or None if not found/expired
        """
        async with self._lock:
            key = self._make_key(provider, company, **ctx)
            
            if key not in self._cache:
                self._misses += 1
                return None
            
            result, expires = self._cache[key]
            
            if time.monotonic() > expires:
                del self._cache[key]
                self._misses += 1
                return None
            
            self._hits += 1
            return result
    
    async def set(
        self,
        provider: str,
        company: str,
        result: Any,
        ttl_s: Optional[float] = None,
        **ctx,
    ):
        """Cache provider result.
        
        Args:
            provider: Provider name
            company: Company name
            result: Result to cache (typically ProviderResult)
            ttl_s: TTL in seconds (uses default if not specified)
            **ctx: Context (must match get() call)
        """
        async with self._lock:
            # LRU eviction if at capacity
            if len(self._cache) >= self._max_size:
                # Find oldest entry
                oldest_key = min(
                    self._cache.keys(),
                    key=lambda k: self._cache[k][1]
                )
                del self._cache[oldest_key]
            
            key = self._make_key(provider, company, **ctx)
            ttl = ttl_s if ttl_s is not None else self._default_ttl
            self._cache[key] = (result, time.monotonic() + ttl)
    
    async def invalidate(
        self,
        provider: Optional[str] = None,
        company: Optional[str] = None,
    ) -> int:
        """Invalidate cache entries matching criteria.
        
        Args:
            provider: If specified, invalidate only this provider
            company: If specified, invalidate only this company
            
        Returns:
            Number of entries invalidated
        """
        async with self._lock:
            if provider is None and company is None:
                # Invalidate all
                count = len(self._cache)
                self._cache.clear()
                return count
            
            # Need to check each key (keys contain provider:company prefix)
            to_delete = []
            for key, (result, _) in self._cache.items():
                match = False
                if provider and hasattr(result, "provider"):
                    if result.provider == provider:
                        match = True
                if company and hasattr(result, "raw"):
                    # This is heuristic - key contains company
                    if company.lower() in key.lower():
                        match = True
                
                if match:
                    to_delete.append(key)
            
            for key in to_delete:
                del self._cache[key]
            
            return len(to_delete)
    
    async def clear(self):
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dict with size, hits, misses, hit_ratio
        """
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": self._hits / total if total > 0 else 0.0,
            "max_size": self._max_size,
            "default_ttl_seconds": self._default_ttl,
        }
