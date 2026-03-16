"""Shared test fixtures for HireStack AI backend tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_ai_client():
    """Mock AIClient that returns configurable responses."""
    client = MagicMock()
    client.complete = AsyncMock(return_value="mock response")
    client.complete_json = AsyncMock(return_value={"result": "mock"})
    client.chat = AsyncMock(return_value="mock chat response")
    client.provider_name = "mock"
    client.model = "mock-model"
    client.max_tokens = 4096
    return client
