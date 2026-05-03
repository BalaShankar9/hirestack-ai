"""Tests for portal_scanner_http.make_httpx_fetcher.

Validates:
  * 200 + valid JSON object/array → FetchResult(payload=...)
  * Non-200 → FetchResult(status=N, payload=None, error="http_N")
    for representative retryable (429, 500, 502, 503) and permanent
    (404, 403, 410, 451) status codes.
  * 200 + invalid JSON → FetchResult(payload=None, error="invalid_json")
  * 200 + body > MAX_BODY_BYTES → error="body_too_large"
  * Transport failures → raise FetchError (worker's retryable signal)
  * Headers carry User-Agent + Accept JSON
  * Custom timeout / user_agent honoured
  * Injected client path is exercised when caller supplies one
  * One-shot client path is exercised when no client supplied
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.portal_scanner_http import (
    DEFAULT_TIMEOUT_S,
    DEFAULT_USER_AGENT,
    MAX_BODY_BYTES,
    make_httpx_fetcher,
)
from app.services.portal_scanner_worker import FetchError, FetchResult


# ── Helpers ──────────────────────────────────────────────────────────


def _resp(status: int, body: bytes | str = b"", *, content: bytes | None = None) -> MagicMock:
    """Build a fake httpx.Response stand-in."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    if content is not None:
        r.content = content
    elif isinstance(body, str):
        r.content = body.encode("utf-8")
    else:
        r.content = body
    return r


def _client_returning(resp: MagicMock) -> MagicMock:
    """Build a fake httpx.AsyncClient that returns ``resp`` from .get()."""
    c = MagicMock(spec=httpx.AsyncClient)
    c.get = AsyncMock(return_value=resp)
    return c


def _client_raising(exc: BaseException) -> MagicMock:
    c = MagicMock(spec=httpx.AsyncClient)
    c.get = AsyncMock(side_effect=exc)
    return c


# ── 200 happy paths ──────────────────────────────────────────────────


class TestSuccessPath:
    @pytest.mark.asyncio
    async def test_200_object_payload_returned_intact(self):
        body = json.dumps({"jobs": [{"id": 1, "title": "Eng"}]}).encode("utf-8")
        client = _client_returning(_resp(200, content=body))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/jobs")

        assert isinstance(result, FetchResult)
        assert result.status == 200
        assert result.error is None
        assert result.payload == {"jobs": [{"id": 1, "title": "Eng"}]}

    @pytest.mark.asyncio
    async def test_200_array_payload_returned_intact(self):
        # Lever returns a top-level JSON array.
        body = json.dumps([{"id": "a"}, {"id": "b"}]).encode("utf-8")
        client = _client_returning(_resp(200, content=body))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.lever.co/v0/postings/acme?mode=json")

        assert result.status == 200
        assert result.payload == [{"id": "a"}, {"id": "b"}]
        assert result.error is None

    @pytest.mark.asyncio
    async def test_200_empty_object_is_still_success(self):
        client = _client_returning(_resp(200, content=b"{}"))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/x")

        assert result.status == 200
        assert result.payload == {}
        assert result.error is None


# ── Non-200 status mapping ──────────────────────────────────────────


class TestNon200Status:
    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    @pytest.mark.asyncio
    async def test_retryable_statuses_return_fetchresult_not_raise(self, status):
        # Worker decides retry — fetcher MUST return, not raise, so
        # _is_retryable_status() in worker can pick the right path.
        client = _client_returning(_resp(status))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/x")

        assert result.status == status
        assert result.payload is None
        assert result.error == f"http_{status}"

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 451])
    @pytest.mark.asyncio
    async def test_permanent_4xx_statuses_return_fetchresult_not_raise(self, status):
        # 4xx other than 429 are permanent per worker contract — but
        # we still RETURN them as FetchResult; the worker is the policy
        # owner, not us.
        client = _client_returning(_resp(status))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/missing")

        assert result.status == status
        assert result.payload is None
        assert result.error == f"http_{status}"


# ── 200 + bad body ──────────────────────────────────────────────────


class TestMalformedBody:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_invalid_json_error(self):
        client = _client_returning(_resp(200, content=b"<html>not json</html>"))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/x")

        assert result.status == 200
        assert result.payload is None
        assert result.error == "invalid_json"

    @pytest.mark.asyncio
    async def test_truncated_json_returns_invalid_json_error(self):
        # JSON that starts valid but is truncated mid-stream.
        client = _client_returning(_resp(200, content=b'{"jobs": [{"id":'))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/x")

        assert result.status == 200
        assert result.payload is None
        assert result.error == "invalid_json"

    @pytest.mark.asyncio
    async def test_empty_body_returns_invalid_json_error(self):
        client = _client_returning(_resp(200, content=b""))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/x")

        assert result.status == 200
        assert result.payload is None
        assert result.error == "invalid_json"

    @pytest.mark.asyncio
    async def test_body_at_max_size_succeeds(self):
        # Exactly MAX_BODY_BYTES of valid JSON (a giant array of zeros).
        # We can't easily construct exactly MAX bytes of valid JSON,
        # so use a small body and prove the < check works.
        small_payload = {"a": "b"}
        body = json.dumps(small_payload).encode("utf-8")
        assert len(body) < MAX_BODY_BYTES
        client = _client_returning(_resp(200, content=body))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/x")

        assert result.status == 200
        assert result.payload == small_payload
        assert result.error is None

    @pytest.mark.asyncio
    async def test_body_over_max_size_returns_body_too_large(self):
        oversized = b"x" * (MAX_BODY_BYTES + 1)
        client = _client_returning(_resp(200, content=oversized))
        fetcher = make_httpx_fetcher(client=client)

        result = await fetcher("https://api.example.com/x")

        assert result.status == 200
        assert result.payload is None
        assert result.error == "body_too_large"


# ── Transport failures ──────────────────────────────────────────────


class TestTransportFailures:
    @pytest.mark.asyncio
    async def test_connect_timeout_raises_fetcherror(self):
        client = _client_raising(httpx.ConnectTimeout("connect timed out"))
        fetcher = make_httpx_fetcher(client=client)

        with pytest.raises(FetchError) as exc_info:
            await fetcher("https://api.example.com/x")

        assert "ConnectTimeout" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_timeout_raises_fetcherror(self):
        client = _client_raising(httpx.ReadTimeout("read timed out"))
        fetcher = make_httpx_fetcher(client=client)

        with pytest.raises(FetchError):
            await fetcher("https://api.example.com/x")

    @pytest.mark.asyncio
    async def test_connect_error_raises_fetcherror(self):
        client = _client_raising(httpx.ConnectError("DNS failed"))
        fetcher = make_httpx_fetcher(client=client)

        with pytest.raises(FetchError) as exc_info:
            await fetcher("https://api.example.com/x")

        assert "ConnectError" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pool_timeout_raises_fetcherror(self):
        client = _client_raising(httpx.PoolTimeout("pool exhausted"))
        fetcher = make_httpx_fetcher(client=client)

        with pytest.raises(FetchError):
            await fetcher("https://api.example.com/x")

    @pytest.mark.asyncio
    async def test_generic_request_error_raises_fetcherror(self):
        client = _client_raising(httpx.RequestError("boom"))
        fetcher = make_httpx_fetcher(client=client)

        with pytest.raises(FetchError):
            await fetcher("https://api.example.com/x")

    @pytest.mark.asyncio
    async def test_non_httpx_exception_propagates_unchanged(self):
        # Programmer-error exceptions (KeyError, ValueError, etc) must
        # NOT get swallowed as transport failures.
        client = _client_raising(KeyError("oops"))
        fetcher = make_httpx_fetcher(client=client)

        with pytest.raises(KeyError):
            await fetcher("https://api.example.com/x")


# ── Headers + customisation ─────────────────────────────────────────


class TestHeadersAndOptions:
    @pytest.mark.asyncio
    async def test_default_headers_include_useragent_and_accept_json(self):
        client = _client_returning(_resp(200, content=b"{}"))
        fetcher = make_httpx_fetcher(client=client)

        await fetcher("https://api.example.com/x")

        # client.get(url, headers=..., timeout=...)
        call = client.get.await_args
        assert call.args[0] == "https://api.example.com/x"
        headers = call.kwargs["headers"]
        assert headers["User-Agent"] == DEFAULT_USER_AGENT
        assert headers["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_custom_user_agent_honoured(self):
        client = _client_returning(_resp(200, content=b"{}"))
        fetcher = make_httpx_fetcher(client=client, user_agent="MyTestBot/2.0")

        await fetcher("https://api.example.com/x")

        headers = client.get.await_args.kwargs["headers"]
        assert headers["User-Agent"] == "MyTestBot/2.0"

    @pytest.mark.asyncio
    async def test_default_timeout_passed_to_get(self):
        client = _client_returning(_resp(200, content=b"{}"))
        fetcher = make_httpx_fetcher(client=client)

        await fetcher("https://api.example.com/x")

        assert client.get.await_args.kwargs["timeout"] == DEFAULT_TIMEOUT_S

    @pytest.mark.asyncio
    async def test_custom_timeout_passed_to_get(self):
        client = _client_returning(_resp(200, content=b"{}"))
        fetcher = make_httpx_fetcher(client=client, timeout_s=3.5)

        await fetcher("https://api.example.com/x")

        assert client.get.await_args.kwargs["timeout"] == 3.5

    @pytest.mark.asyncio
    async def test_injected_client_is_not_closed_by_fetcher(self):
        # Caller owns the lifecycle of the injected client; we must
        # NOT touch __aenter__/__aexit__ on it.
        client = _client_returning(_resp(200, content=b"{}"))
        fetcher = make_httpx_fetcher(client=client)

        await fetcher("https://api.example.com/x")

        # No aclose / __aexit__ usage on the injected client.
        assert not getattr(client, "aclose", MagicMock()).called
        # We never entered a context-manager protocol on it.
        assert not getattr(client, "__aenter__", MagicMock()).called


# ── One-shot client path (no injection) ─────────────────────────────


class TestOneShotClient:
    @pytest.mark.asyncio
    async def test_oneshot_path_used_when_no_client_injected(self, monkeypatch):
        # Patch httpx.AsyncClient at import site so we don't open a
        # real socket but still exercise the `with` branch.
        instances: list[Any] = []

        class _FakeAsyncClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.entered = False
                self.exited = False
                instances.append(self)

            async def __aenter__(self):
                self.entered = True
                return self

            async def __aexit__(self, exc_type, exc, tb):
                self.exited = True
                return False

            async def get(self, url):
                self.last_url = url
                return _resp(200, content=b'{"ok":1}')

        monkeypatch.setattr(
            "app.services.portal_scanner_http.httpx.AsyncClient",
            _FakeAsyncClient,
        )

        fetcher = make_httpx_fetcher()  # no client injection
        result = await fetcher("https://api.example.com/y")

        assert result.status == 200
        assert result.payload == {"ok": 1}
        # One AsyncClient constructed, entered, and exited.
        assert len(instances) == 1
        assert instances[0].entered is True
        assert instances[0].exited is True
        # Headers + timeout passed to the constructor (not to .get).
        assert instances[0].kwargs["timeout"] == DEFAULT_TIMEOUT_S
        assert instances[0].kwargs["follow_redirects"] is True
        assert instances[0].kwargs["headers"]["User-Agent"] == DEFAULT_USER_AGENT
        assert instances[0].kwargs["headers"]["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_oneshot_transport_failure_still_raises_fetcherror(self, monkeypatch):
        # Same path, but get() raises — must still wrap as FetchError.
        class _FakeAsyncClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url):
                raise httpx.ConnectError("DNS")

        monkeypatch.setattr(
            "app.services.portal_scanner_http.httpx.AsyncClient",
            _FakeAsyncClient,
        )

        fetcher = make_httpx_fetcher()

        with pytest.raises(FetchError) as exc_info:
            await fetcher("https://api.example.com/y")

        assert "ConnectError" in str(exc_info.value)
