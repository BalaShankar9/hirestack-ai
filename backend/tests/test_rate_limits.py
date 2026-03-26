"""Rate limiting tests"""
import pytest


@pytest.mark.asyncio
async def test_pipeline_input_validation(client):
    """Pipeline should validate input sizes."""
    # Missing required field
    resp = await client.post("/api/generate/pipeline", json={})
    assert resp.status_code == 422

    # Empty job title
    resp = await client.post("/api/generate/pipeline", json={
        "job_title": "",
        "jd_text": "Some JD text here for testing",
    })
    assert resp.status_code == 400

    # Empty JD
    resp = await client.post("/api/generate/pipeline", json={
        "job_title": "Engineer",
        "jd_text": "",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resume_parse_requires_file(client):
    """Resume parse should require a file upload."""
    resp = await client.post("/api/resume/parse")
    assert resp.status_code == 422
