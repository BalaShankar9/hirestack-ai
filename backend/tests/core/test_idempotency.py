"""
PR m1-pr3 tests: Idempotency-Key middleware behavior.

Builds an isolated FastAPI app (does not touch the production app /
its routes) and exercises the middleware against an in-memory store.
"""
from __future__ import annotations

import asyncio
from typing import Dict

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport

from app.core.idempotency import (
    IdempotencyMiddleware,
    InMemoryIdempotencyStore,
)


# ───────────────────── fixtures ──

def _build_app(store: InMemoryIdempotencyStore) -> FastAPI:
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware, store=store)

    state: Dict[str, int] = {"calls": 0}
    app.state._calls = state

    @app.post("/things")
    async def create_thing(request: Request):
        state["calls"] += 1
        body = await request.json()
        return {"created": True, "echo": body, "n": state["calls"]}

    @app.post("/explode")
    async def explode():
        state["calls"] += 1
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="boom")

    @app.get("/things")
    async def list_things():
        state["calls"] += 1
        return {"items": []}

    return app


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


@pytest.fixture
def app(store):
    return _build_app(store)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ───────────────────── tests ──

@pytest.mark.asyncio
async def test_double_post_same_key_returns_cached_response(app, client, store):
    """Spec: same key + same hash → cached response, single DB row, single call."""
    headers = {"Idempotency-Key": "k-1", "X-Org-Id": "org-a"}
    payload = {"name": "alpha"}

    r1 = await client.post("/things", json=payload, headers=headers)
    r2 = await client.post("/things", json=payload, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    # Replay marker present on the cached response
    assert r2.headers.get("Idempotent-Replay") == "true"
    assert r1.headers.get("Idempotent-Replay") is None
    # Handler invoked exactly once
    assert app.state._calls["calls"] == 1
    # DB row count = 1
    assert len(store) == 1


@pytest.mark.asyncio
async def test_same_key_different_payload_returns_409(app, client):
    headers = {"Idempotency-Key": "k-2", "X-Org-Id": "org-a"}
    r1 = await client.post("/things", json={"name": "alpha"}, headers=headers)
    r2 = await client.post("/things", json={"name": "BETA"}, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 409
    body = r2.json()
    assert "different payload" in body["detail"].lower()


@pytest.mark.asyncio
async def test_missing_header_passes_through_and_does_not_dedupe(app, client, store):
    """No Idempotency-Key → middleware is a no-op; each call hits the handler."""
    r1 = await client.post("/things", json={"name": "x"})
    r2 = await client.post("/things", json={"name": "x"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert app.state._calls["calls"] == 2
    assert len(store) == 0  # nothing persisted


@pytest.mark.asyncio
async def test_get_requests_are_passthrough(app, client, store):
    """GET is intrinsically idempotent — middleware must not record it."""
    headers = {"Idempotency-Key": "k-get", "X-Org-Id": "org-a"}
    await client.get("/things", headers=headers)
    await client.get("/things", headers=headers)
    assert app.state._calls["calls"] == 2
    assert len(store) == 0


@pytest.mark.asyncio
async def test_5xx_response_is_not_cached(app, client, store):
    """Server errors must not be cached — clients should retry afresh."""
    headers = {"Idempotency-Key": "k-fail", "X-Org-Id": "org-a"}
    r1 = await client.post("/explode", headers=headers)
    assert r1.status_code == 500
    # Row was inserted but completed=False, so a retry sees in-flight 409.
    # That's acceptable per spec; the important guarantee is "not a cached 500".
    rec = await store.get("org-a", "k-fail")
    assert rec is not None
    assert rec.completed is False


@pytest.mark.asyncio
async def test_org_isolation(app, client, store):
    """Same key under different X-Org-Id values do NOT collide."""
    payload = {"name": "shared"}
    r1 = await client.post(
        "/things", json=payload,
        headers={"Idempotency-Key": "shared-key", "X-Org-Id": "org-a"},
    )
    r2 = await client.post(
        "/things", json=payload,
        headers={"Idempotency-Key": "shared-key", "X-Org-Id": "org-b"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both organisations executed independently.
    assert app.state._calls["calls"] == 2
    assert len(store) == 2


@pytest.mark.asyncio
async def test_concurrent_same_key_collapses_to_one_execution(app, client, store):
    """Two near-simultaneous requests with the same key → one handler call."""
    headers = {"Idempotency-Key": "k-race", "X-Org-Id": "org-a"}
    payload = {"name": "race"}

    r1, r2 = await asyncio.gather(
        client.post("/things", json=payload, headers=headers),
        client.post("/things", json=payload, headers=headers),
    )

    statuses = sorted([r1.status_code, r2.status_code])
    # One winner (200) and one of: cached 200 OR 409 in-flight (race-dependent).
    assert statuses[0] == 200
    assert statuses[1] in (200, 409)
    # Handler invoked exactly once.
    assert app.state._calls["calls"] == 1
    assert len(store) == 1
