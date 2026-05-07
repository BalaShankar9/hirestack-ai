"""
Fixtures for cross-tenant isolation tests (PR m1-pr4).

We never hit a real database — every test injects a fake authenticated user
via FastAPI's ``dependency_overrides`` and asserts the route's authorization
logic *fails closed*, i.e. an attacker holding org A's credentials cannot
read a resource UUID that belongs to org B.
"""
from __future__ import annotations

import os
from typing import Any, Dict

import pytest
from httpx import AsyncClient, ASGITransport


# Fake users for the two tenants. ``org_id`` mirrors the field shape that
# downstream services read off the authenticated user object.
ORG_A_ID = "00000000-0000-0000-0000-00000000000a"
ORG_B_ID = "00000000-0000-0000-0000-00000000000b"

USER_A: Dict[str, Any] = {
    "id": "11111111-1111-1111-1111-11111111111a",
    "email": "alice@org-a.test",
    "is_active": True,
    "org_id": ORG_A_ID,
    "active_org_id": ORG_A_ID,
}


@pytest.fixture
def app_with_user_a():
    """Return the production app with ``get_current_user`` short-circuited
    to USER_A.  The override is reverted on teardown so other test files are
    unaffected.
    """
    # Test env defaults already set by backend/tests/conftest.py.
    from main import app as _app
    from app.api.deps import get_current_user, get_current_user_optional

    async def _user_a():
        return USER_A

    _app.dependency_overrides[get_current_user] = _user_a
    _app.dependency_overrides[get_current_user_optional] = _user_a
    try:
        yield _app
    finally:
        _app.dependency_overrides.pop(get_current_user, None)
        _app.dependency_overrides.pop(get_current_user_optional, None)


@pytest.fixture
async def client_a(app_with_user_a):
    transport = ASGITransport(app=app_with_user_a)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
