"""
PR m1-pr3: Idempotency-Key middleware.

Spec:
  - Acts only on POST / PATCH / DELETE requests.
  - Caller supplies header ``Idempotency-Key``.
  - Missing header   → log WARN once per (path), pass through.
  - Same key + same request_hash + completed → return CACHED response.
  - Same key + different request_hash       → 409 conflict.
  - Same key + still in-flight (no completed_at) → 409 conflict
    (clients should retry after the first attempt finishes).
  - New key → INSERT row, dispatch handler, capture response, UPDATE row.

The store interface is pluggable so tests can use an in-memory dict and
production uses Supabase. Disable the whole feature with the env var
``IDEMPOTENCY_ENABLED=false`` (rollback path: simply do not register
the middleware).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional, Protocol, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("hirestack.idempotency")

_ALLOWED_METHODS = frozenset({"POST", "PATCH", "DELETE"})
_HEADER = "Idempotency-Key"
_ANON_ORG = "__anon__"
_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB cap on cached responses


# ───────────────────────────────────────────────── store protocol ──

@dataclass
class IdempotencyRecord:
    org_id: str
    key: str
    method: str
    path: str
    request_hash: str
    status_code: Optional[int] = None
    response_body: Optional[bytes] = None
    response_headers: Dict[str, str] = field(default_factory=dict)
    completed: bool = False


class IdempotencyStore(Protocol):
    async def get(self, org_id: str, key: str) -> Optional[IdempotencyRecord]: ...
    async def insert(self, record: IdempotencyRecord) -> bool:
        """Insert a NEW record. Return False on PK collision (race)."""
        ...
    async def complete(
        self,
        org_id: str,
        key: str,
        status_code: int,
        body: bytes,
        headers: Dict[str, str],
    ) -> None: ...


# ───────────────────────────────────────────────── in-memory store ──

class InMemoryIdempotencyStore:
    """Test-only store. NOT safe for multi-process production use."""

    def __init__(self) -> None:
        self._rows: Dict[Tuple[str, str], IdempotencyRecord] = {}
        self._lock = asyncio.Lock()

    async def get(self, org_id: str, key: str) -> Optional[IdempotencyRecord]:
        async with self._lock:
            row = self._rows.get((org_id, key))
            return None if row is None else _copy_record(row)

    async def insert(self, record: IdempotencyRecord) -> bool:
        async with self._lock:
            pk = (record.org_id, record.key)
            if pk in self._rows:
                return False
            self._rows[pk] = _copy_record(record)
            return True

    async def complete(
        self,
        org_id: str,
        key: str,
        status_code: int,
        body: bytes,
        headers: Dict[str, str],
    ) -> None:
        async with self._lock:
            row = self._rows.get((org_id, key))
            if row is None:
                return
            row.status_code = status_code
            row.response_body = body
            row.response_headers = dict(headers)
            row.completed = True

    # Test helper: total persisted rows (proves single execution).
    def __len__(self) -> int:
        return len(self._rows)


def _copy_record(r: IdempotencyRecord) -> IdempotencyRecord:
    return IdempotencyRecord(
        org_id=r.org_id,
        key=r.key,
        method=r.method,
        path=r.path,
        request_hash=r.request_hash,
        status_code=r.status_code,
        response_body=r.response_body,
        response_headers=dict(r.response_headers),
        completed=r.completed,
    )


# ────────────────────────────────────────────── supabase store ──

class SupabaseIdempotencyStore:
    """Production store backed by Supabase ``idempotency_keys`` table."""

    def __init__(self, table_name: str = "idempotency_keys") -> None:
        self._table = table_name

    def _client(self):
        from app.core.database import get_supabase
        return get_supabase()

    async def get(self, org_id: str, key: str) -> Optional[IdempotencyRecord]:
        def _q():
            return (
                self._client()
                .table(self._table)
                .select("*")
                .eq("org_id", org_id)
                .eq("key", key)
                .limit(1)
                .execute()
            )

        try:
            res = await asyncio.to_thread(_q)
        except Exception as exc:  # pragma: no cover - infra path
            logger.warning("idempotency.get failed: %s", str(exc)[:200])
            return None
        rows = getattr(res, "data", None) or []
        if not rows:
            return None
        row = rows[0]
        body_b64 = row.get("response_body")
        body = base64.b64decode(body_b64) if body_b64 else None
        return IdempotencyRecord(
            org_id=row["org_id"],
            key=row["key"],
            method=row["method"],
            path=row["path"],
            request_hash=row["request_hash"],
            status_code=row.get("status_code"),
            response_body=body,
            response_headers=row.get("response_headers") or {},
            completed=row.get("completed_at") is not None,
        )

    async def insert(self, record: IdempotencyRecord) -> bool:
        def _q():
            return (
                self._client()
                .table(self._table)
                .insert(
                    {
                        "org_id": record.org_id,
                        "key": record.key,
                        "method": record.method,
                        "path": record.path,
                        "request_hash": record.request_hash,
                    }
                )
                .execute()
            )

        try:
            await asyncio.to_thread(_q)
            return True
        except Exception as exc:  # PK collision is the expected race
            logger.debug("idempotency.insert race: %s", str(exc)[:200])
            return False

    async def complete(
        self,
        org_id: str,
        key: str,
        status_code: int,
        body: bytes,
        headers: Dict[str, str],
    ) -> None:
        def _q():
            return (
                self._client()
                .table(self._table)
                .update(
                    {
                        "status_code": status_code,
                        "response_body": base64.b64encode(body).decode("ascii"),
                        "response_headers": headers,
                        "completed_at": "now()",
                    }
                )
                .eq("org_id", org_id)
                .eq("key", key)
                .execute()
            )

        try:
            await asyncio.to_thread(_q)
        except Exception as exc:  # pragma: no cover - infra path
            logger.warning("idempotency.complete failed: %s", str(exc)[:200])


# ────────────────────────────────────────────── helpers ──

def _resolve_org_id(request: Request) -> str:
    return (request.headers.get("X-Org-Id") or _ANON_ORG).strip() or _ANON_ORG


def _request_hash(method: str, path: str, body: bytes) -> str:
    h = hashlib.sha256()
    h.update(method.encode("ascii"))
    h.update(b"\n")
    h.update(path.encode("utf-8"))
    h.update(b"\n")
    h.update(body)
    return h.hexdigest()


def _safe_response_headers(headers) -> Dict[str, str]:
    # Strip hop-by-hop and security-derived headers we shouldn't replay.
    drop = {"content-length", "date", "server", "transfer-encoding", "connection"}
    return {
        k: v for k, v in headers.items() if k.lower() not in drop
    }


# ────────────────────────────────────────────── middleware ──

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware enforcing Idempotency-Key semantics."""

    def __init__(self, app, store: Optional[IdempotencyStore] = None) -> None:
        super().__init__(app)
        # Important: do NOT use ``store or default`` — InMemoryStore overrides
        # __len__ and an empty store is falsy.
        self._store: IdempotencyStore = (
            store if store is not None else SupabaseIdempotencyStore()
        )
        self._missing_warned: set = set()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method.upper()
        if method not in _ALLOWED_METHODS:
            return await call_next(request)

        key = (request.headers.get(_HEADER) or "").strip()
        if not key:
            # Spec: pass through but warn (once per path to avoid log spam).
            path = request.url.path
            if path not in self._missing_warned:
                self._missing_warned.add(path)
                logger.warning(
                    "idempotency.missing_key method=%s path=%s", method, path
                )
            return await call_next(request)

        org_id = _resolve_org_id(request)
        body = await request.body()
        req_hash = _request_hash(method, request.url.path, body)

        existing = await self._store.get(org_id, key)
        if existing is not None:
            if existing.request_hash != req_hash:
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "Idempotency-Key reused with a different payload",
                        "key": key,
                    },
                )
            if not existing.completed:
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "Idempotent request still in flight; retry shortly",
                        "key": key,
                    },
                )
            # Replay cached response.
            return Response(
                content=existing.response_body or b"",
                status_code=existing.status_code or 200,
                headers={
                    **existing.response_headers,
                    "Idempotent-Replay": "true",
                },
            )

        record = IdempotencyRecord(
            org_id=org_id,
            key=key,
            method=method,
            path=request.url.path,
            request_hash=req_hash,
        )
        inserted = await self._store.insert(record)
        if not inserted:
            # Race lost — re-fetch and replay.
            existing = await self._store.get(org_id, key)
            if existing is not None and existing.completed:
                return Response(
                    content=existing.response_body or b"",
                    status_code=existing.status_code or 200,
                    headers={
                        **existing.response_headers,
                        "Idempotent-Replay": "true",
                    },
                )
            return JSONResponse(
                status_code=409,
                content={"detail": "Concurrent request with same Idempotency-Key", "key": key},
            )

        # Re-inject the consumed body so downstream handlers can read it.
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        request._receive = receive  # noqa: SLF001 - documented Starlette pattern

        response = await call_next(request)

        body_chunks = []
        total = 0
        too_large = False
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
            total += len(chunk)
            if total > _MAX_BODY_BYTES:
                too_large = True
        body_bytes = b"".join(body_chunks)
        safe_headers = _safe_response_headers(response.headers)

        # Only cache successful & client-error responses (never 5xx) and skip
        # caching of bodies above the size cap.
        if not too_large and 200 <= response.status_code < 500:
            try:
                await self._store.complete(
                    org_id, key, response.status_code, body_bytes, safe_headers
                )
            except Exception as exc:  # pragma: no cover - infra path
                logger.warning("idempotency.complete error: %s", str(exc)[:200])

        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
        )
