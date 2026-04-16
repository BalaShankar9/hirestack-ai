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

# supabase-py validates that the API keys are JWT-format strings.
# Using bare strings like "placeholder" causes create_client() to fail before
# any test logic runs.  Always force a valid JWT-format dummy here so the
# client initialises successfully; actual network calls are avoided because
# all protected routes return 401 before touching the database.
_DUMMY_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJ0ZXN0Iiwicm9sZSI6ImFub24ifQ"
    ".ZGVhZGJlZWY"
)
os.environ["SUPABASE_ANON_KEY"] = _DUMMY_JWT
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = _DUMMY_JWT


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
