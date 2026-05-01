"""S18 — In-memory TTL cache for recon swarm results.

Protocol-based so a Redis impl can slot in (follow-up). Default
implementation is a process-local dict + monotonic-clock TTL.
"""
from __future__ import annotations

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
