"""
Test configuration and fixtures
"""
import os
import pytest
from httpx import AsyncClient, ASGITransport

# Set test environment before importing app
os.environ["DEBUG"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["SUPABASE_URL"] = os.environ.get("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ["SUPABASE_ANON_KEY"] = os.environ.get("SUPABASE_ANON_KEY", "placeholder")
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "placeholder")


@pytest.fixture
def app():
    """Create a fresh app instance for testing."""
    from main import app as _app
    return _app


@pytest.fixture
async def client(app):
    """Async HTTP client for testing endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
