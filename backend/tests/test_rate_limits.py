"""Rate limiting and input validation tests"""
import pytest


@pytest.mark.asyncio
async def test_pipeline_requires_auth(client):
    """Pipeline should require authentication."""
    resp = await client.post("/api/generate/pipeline", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resume_parse_requires_auth(client):
    """Resume parse should require authentication."""
    resp = await client.post("/api/resume/parse")
    assert resp.status_code == 401
