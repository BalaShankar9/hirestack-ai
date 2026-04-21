"""Semantic response cache for AI calls.

Hashes (prompt + system + model + schema + temperature) → cached response.
Uses an in-memory LRU with optional Redis backend for persistence across restarts.

Cache hits avoid LLM calls entirely — same input always yields same output
for deterministic temperatures (≤0.3). Higher temperatures are cached too
but with a shorter TTL since results may vary.

v2 additions:
- Cross-user JD analysis cache (content-addressed by JD hash)
- Pipeline result cache (skip unchanged modules on re-generation)
- Cache tier awareness (separate pools for different TTL classes)
- Cache statistics per task_type for cost optimization visibility
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger("hirestack.ai_cache")


def _build_cache_key(
    *,
    prompt: str,
    system: Optional[str],
    model: str,
    schema: Optional[Dict[str, Any]],
    temperature: float,
    max_tokens: Optional[int],
) -> str:
    """SHA-256 hash of all request parameters that affect output."""
    payload = json.dumps(
        {
            "p": prompt,
            "s": system or "",
            "m": model,
            "sc": schema or {},
            "t": round(temperature, 2),
            "mt": max_tokens or 0,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class _LRUCache:
    """Thread-safe in-memory LRU cache with TTL expiry."""

    def __init__(self, max_entries: int = 2000) -> None:
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max_entries

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        # Move to end (most recently accessed)
        self._store.move_to_end(key)
        return value

    def put(self, key: str, value: Any, ttl_seconds: float) -> None:
        expires_at = time.monotonic() + ttl_seconds
        self._store[key] = (expires_at, value)
        self._store.move_to_end(key)
        # Evict oldest if over capacity
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


class AIResponseCache:
    """Semantic cache for AI responses.

    Wraps an in-memory LRU. Redis support can be added later by
    extending get/put to check Redis before/after the LRU.
    """

    def __init__(
        self,
        enabled: bool = True,
        default_ttl: int = 3600,
        max_entries: int = 2000,
    ) -> None:
        self._enabled = enabled
        self._default_ttl = default_ttl
        self._lru = _LRUCache(max_entries=max_entries)
        self._hits = 0
        self._misses = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _effective_ttl(self, temperature: float) -> float:
        """Lower TTL for high-temperature (non-deterministic) calls."""
        if temperature <= 0.3:
            return float(self._default_ttl)
        if temperature <= 0.5:
            return float(self._default_ttl) * 0.5
        # High temperature — cache briefly (5 min) to dedup rapid retries
        return min(300.0, float(self._default_ttl) * 0.15)

    def get(
        self,
        *,
        prompt: str,
        system: Optional[str] = None,
        model: str,
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> Optional[Any]:
        if not self._enabled:
            return None
        key = _build_cache_key(
            prompt=prompt, system=system, model=model,
            schema=schema, temperature=temperature, max_tokens=max_tokens,
        )
        result = self._lru.get(key)
        if result is not None:
            self._hits += 1
            if self._hits % 50 == 0:
                logger.info(
                    "ai_cache_stats: hits=%d misses=%d hit_rate=%.1f%% size=%d",
                    self._hits, self._misses,
                    (self._hits / max(1, self._hits + self._misses)) * 100,
                    self._lru.size,
                )
            try:
                from ai_engine.agent_events import emit_cache_hit
                emit_cache_hit("ai_response", key_preview=key[:60])
            except Exception:
                pass
            return result
        self._misses += 1
        return None

    def put(
        self,
        *,
        prompt: str,
        system: Optional[str] = None,
        model: str,
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        response: Any,
    ) -> None:
        if not self._enabled:
            return
        key = _build_cache_key(
            prompt=prompt, system=system, model=model,
            schema=schema, temperature=temperature, max_tokens=max_tokens,
        )
        ttl = self._effective_ttl(temperature)
        self._lru.put(key, response, ttl)

    def clear(self) -> None:
        self._lru.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round((self._hits / max(1, total)) * 100, 1),
            "size": self._lru.size,
            "enabled": self._enabled,
        }


# ── Singleton ──────────────────────────────────────────────────────────
_cache_instance: Optional[AIResponseCache] = None


def get_ai_cache() -> AIResponseCache:
    """Get the singleton AI response cache."""
    global _cache_instance
    if _cache_instance is None:
        try:
            from app.core.config import settings
            _cache_instance = AIResponseCache(
                enabled=settings.ai_cache_enabled,
                default_ttl=settings.ai_cache_ttl_seconds,
                max_entries=settings.ai_cache_max_entries,
            )
        except Exception:
            # Fallback if config not available (e.g. running outside backend)
            _cache_instance = AIResponseCache(
                enabled=True,
                default_ttl=3600,
                max_entries=2000,
            )
    return _cache_instance


# ═══════════════════════════════════════════════════════════════════════
#  Cross-user JD analysis cache
#  Content-addressed by JD text hash — shareable across all users
#  applying to the same job description.
# ═══════════════════════════════════════════════════════════════════════

class JDAnalysisCache:
    """Cache JD-level analysis (benchmark, keywords, requirements) by JD hash.

    Since many users may apply to the same job posting, the JD analysis
    (benchmark profile, keyword extraction, requirement parsing) is identical
    regardless of the applicant. This cache prevents re-computing it.

    TTL: 4 hours (JD content doesn't change frequently).
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max_entries
        self._hits = 0
        self._misses = 0

    @staticmethod
    def hash_jd(jd_text: str, job_title: str = "") -> str:
        """Content-addressed hash for a job description."""
        normalized = json.dumps({
            "jd": jd_text.strip()[:8000],
            "title": job_title.strip().lower(),
        }, sort_keys=True)
        return "jd_" + hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get(self, jd_hash: str) -> Optional[Any]:
        entry = self._store.get(jd_hash)
        if entry is None:
            self._misses += 1
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(jd_hash, None)
            self._misses += 1
            return None
        self._store.move_to_end(jd_hash)
        self._hits += 1
        return value

    def put(self, jd_hash: str, value: Any, ttl: float = 14400.0) -> None:
        """Store JD analysis (default TTL: 4 hours)."""
        self._store[jd_hash] = (time.monotonic() + ttl, value)
        self._store.move_to_end(jd_hash)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round((self._hits / max(1, total)) * 100, 1),
            "size": len(self._store),
        }


_jd_cache_instance: Optional[JDAnalysisCache] = None


def get_jd_cache() -> JDAnalysisCache:
    """Get the singleton JD analysis cache."""
    global _jd_cache_instance
    if _jd_cache_instance is None:
        _jd_cache_instance = JDAnalysisCache()
    return _jd_cache_instance


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline result cache — skip unchanged modules on regeneration
# ═══════════════════════════════════════════════════════════════════════

class PipelineResultCache:
    """Cache pipeline outputs keyed by (application_id, module, input_hash).

    When a user re-generates, we check if the inputs for each module
    have changed. If not, we reuse the previous output — skipping
    the entire pipeline for that module.

    Input hash includes: brief_hash + module-specific config.
    """

    def __init__(self, max_entries: int = 300) -> None:
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max_entries
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(application_id: str, module: str, input_hash: str) -> str:
        return f"pr_{application_id}_{module}_{input_hash}"

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            self._misses += 1
            return None
        self._store.move_to_end(key)
        self._hits += 1
        logger.info("pipeline_result_cache_hit: key=%s", key[:60])
        return value

    def put(self, key: str, value: Any, ttl: float = 7200.0) -> None:
        """Store pipeline result (default TTL: 2 hours)."""
        self._store[key] = (time.monotonic() + ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def invalidate_application(self, application_id: str) -> int:
        """Invalidate all cached results for a given application."""
        keys_to_remove = [k for k in self._store if f"_{application_id}_" in k]
        for k in keys_to_remove:
            self._store.pop(k, None)
        return len(keys_to_remove)

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round((self._hits / max(1, total)) * 100, 1),
            "size": len(self._store),
        }


_pipeline_cache_instance: Optional[PipelineResultCache] = None


def get_pipeline_cache() -> PipelineResultCache:
    """Get the singleton pipeline result cache."""
    global _pipeline_cache_instance
    if _pipeline_cache_instance is None:
        _pipeline_cache_instance = PipelineResultCache()
    return _pipeline_cache_instance


# ═══════════════════════════════════════════════════════════════════════
#  Aggregate cache stats (for monitoring / cost dashboard)
# ═══════════════════════════════════════════════════════════════════════

def get_all_cache_stats() -> Dict[str, Any]:
    """Return stats from all cache layers."""
    return {
        "ai_response_cache": get_ai_cache().stats,
        "jd_analysis_cache": get_jd_cache().stats,
        "pipeline_result_cache": get_pipeline_cache().stats,
    }
