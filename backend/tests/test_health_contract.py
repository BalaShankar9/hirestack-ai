"""Cross-contract pin: /health response shape matches scripts/health_check.py.

scripts/health_check.py asserts /health returns 200 with a JSON body
that has a "status" key. The deploy gate fails if either is missing.
This test pins both ends of that contract in a single assertion so a
backend refactor can't silently break the deploy gate.
"""
from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_health_endpoint_satisfies_health_check_script_contract(client) -> None:
    """The contract enforced by scripts/health_check.py for /health is:
       - HTTP 200 (DEGRADED 503 also acceptable, but PASS gate wants 200)
       - body parses as JSON
       - "status" key present
       - status value is one of the documented values.
    """
    resp = await client.get("/health")
    # health_check.py PASSES on 200; 503 is the legitimate "DEGRADED"
    # signal; both must remain valid JSON with status key for the
    # cross-contract to hold.
    assert resp.status_code in (200, 503), resp.status_code
    body = resp.text
    parsed = json.loads(body)  # must parse: health_check.py does json.loads
    assert "status" in parsed, f"contract drift: /health body missing 'status' key: {parsed!r}"
    assert parsed["status"] in ("healthy", "degraded"), (
        f"/health.status drifted to unknown value {parsed['status']!r}; "
        f"deploy-gate health_check.py only knows 'healthy'/'degraded'"
    )


@pytest.mark.asyncio
async def test_openapi_endpoint_satisfies_health_check_contract(client) -> None:
    """scripts/health_check.py asserts /openapi.json returns 200 with
    body containing the literal '"openapi"'. Any change to the FastAPI
    OpenAPI schema endpoint would break the deploy gate."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert '"openapi"' in resp.text, (
        "contract drift: /openapi.json body no longer contains "
        "'\"openapi\"' literal expected by scripts/health_check.py"
    )
