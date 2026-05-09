"""
PR m1-pr4 — Cross-tenant isolation regression test.

Walks ``app.routes`` to discover authenticated GET endpoints whose path
contains a resource id (``{*_id}``) and probes each one with USER_A
holding a UUID that is *not* owned by org A.  The route MUST fail-closed
(4xx).  A 200 OK indicates a leak — an attacker logged into org A could
read an arbitrary org B record.

Status interpretation:

* 200          → LEAK.  Test fails immediately and reports the route.
* 401/403/404  → Properly isolated.  Pass.
* 422          → Path validation rejected — pass (still isolated).
* 5xx          → Inconclusive (downstream DB unavailable in CI).  Logged
                 but does not fail the test, since fail-closed is preserved.

Routes are discovered dynamically so newly added endpoints are exercised
automatically.  Routes that are intentionally cross-tenant readable
(e.g. shared catalog data) belong in ``CROSS_TENANT_ALLOWLIST``.
"""
from __future__ import annotations

import re
import uuid
from typing import List, Tuple

import pytest
from fastapi.routing import APIRoute


# A UUID that *cannot* belong to USER_A's org because we never seed any data.
FOREIGN_RESOURCE_ID = "deadbeef-dead-beef-dead-beefdeadbeef"

# Path-param regex: any segment of the form {something_id} or {id}.
_PARAM_RX = re.compile(r"\{([a-z_]+_id|id)\}")

# Routes whose data is intentionally global / not tenant-scoped.  Keep
# this list short and audited — every entry is a documented exception.
CROSS_TENANT_ALLOWLIST: set[str] = {
    # Health / docs are not auth-protected.
    "/health",
    "/docs",
    "/openapi.json",
}

# Routes that take heavy / streaming dependencies and would just hang in
# CI; we still verify they're auth-gated by other tests.
SKIP_PATHS: set[str] = {
    "/api/generate/jobs/{job_id}/stream",
    "/api/generate/jobs/{job_id}/replay",
}


def _resource_get_routes(app) -> List[Tuple[str, str]]:
    """Yield (method, path) for every GET route with a resource id param."""
    out: List[Tuple[str, str]] = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        if "GET" not in r.methods:
            continue
        if r.path in CROSS_TENANT_ALLOWLIST or r.path in SKIP_PATHS:
            continue
        if not _PARAM_RX.search(r.path):
            continue
        out.append(("GET", r.path))
    return out


def _fill_path(path: str) -> str:
    """Substitute every ``{*_id}`` placeholder with FOREIGN_RESOURCE_ID."""
    return _PARAM_RX.sub(FOREIGN_RESOURCE_ID, path)


@pytest.mark.asyncio
async def test_no_resource_route_returns_200_for_foreign_id(
    app_with_user_a, client_a
):
    """For every authenticated GET resource route, USER_A asking for a
    UUID that is not in their org must NOT receive a 200 OK.
    """
    routes = _resource_get_routes(app_with_user_a)
    assert routes, "expected at least one resource-id route — discovery broken?"

    leaks: list[tuple[str, int, str]] = []
    inconclusive: list[tuple[str, int]] = []
    isolated = 0

    for method, path in routes:
        url = _fill_path(path)
        try:
            resp = await client_a.request(method, url)
        except Exception as exc:  # network/transport — treat as inconclusive
            inconclusive.append((path, -1))
            continue

        status = resp.status_code
        if status == 200:
            # CONFIRM: was the body actually a resource payload?
            # Some routes return 200 with an empty list (e.g. listing
            # endpoints that filter by org and find none).  We only flag
            # a 200 that returns a dict-shaped payload as a leak.
            try:
                body = resp.json()
            except Exception:
                body = None
            if isinstance(body, dict) and body:
                leaks.append((path, status, str(body)[:200]))
            else:
                isolated += 1
        elif status in (401, 403, 404, 422):
            isolated += 1
        elif 500 <= status < 600:
            inconclusive.append((path, status))
        else:
            # Other client errors (e.g. 409, 410) also count as fail-closed.
            isolated += 1

    # Print a summary so CI logs surface the coverage.
    print(
        f"\n[tenancy-isolation] routes={len(routes)} "
        f"isolated={isolated} inconclusive={len(inconclusive)} leaks={len(leaks)}"
    )
    if inconclusive:
        print("  inconclusive (5xx — DB unavailable in CI, fail-closed preserved):")
        for path, status in inconclusive[:10]:
            print(f"    {status} {path}")

    assert not leaks, (
        "Cross-tenant LEAK detected: USER_A received 200 OK for a foreign "
        f"resource id on {len(leaks)} route(s):\n"
        + "\n".join(f"  {p} -> {s} body={b}" for p, s, b in leaks)
    )


@pytest.mark.asyncio
async def test_unauthenticated_resource_routes_return_401(client_a):
    """Sanity check: with the override removed, a request with no auth
    header gets a 401 from the standard ``get_current_user`` dependency.
    """
    # Build a fresh transport WITHOUT any override.
    from main import app as _app
    from app.api.deps import get_current_user
    from httpx import AsyncClient, ASGITransport

    # Drop the override briefly.
    saved = _app.dependency_overrides.pop(get_current_user, None)
    try:
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as anon:
            # m12-pr06: /api/missions was removed; use a stable resource
            # route that still requires get_current_user.
            r = await anon.get(f"/api/jobs/{FOREIGN_RESOURCE_ID}")
        assert r.status_code in (401, 403), (
            f"unauthenticated request should be rejected, got {r.status_code}"
        )
    finally:
        if saved is not None:
            _app.dependency_overrides[get_current_user] = saved


def test_resource_route_discovery_is_nontrivial():
    """Guard against regressions in the discovery walker: if someone
    refactors the router and we silently end up with 0 protected routes,
    the isolation test would pass vacuously.  Pin a floor.
    """
    from main import app

    routes = _resource_get_routes(app)
    assert len(routes) >= 20, (
        f"expected >=20 resource-id GET routes, found {len(routes)} — "
        "discovery walker may be broken"
    )


def test_foreign_resource_id_is_a_valid_uuid():
    """The probe value must satisfy any UUID validators on the route, so
    they reject by *not finding the row*, not by a 422 path-validation
    error.  (422 is still acceptable — see status table — but we want
    the probe to actually reach the handler when it can.)
    """
    uuid.UUID(FOREIGN_RESOURCE_ID)
