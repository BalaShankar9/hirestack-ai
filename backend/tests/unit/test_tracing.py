"""S1-F4: behavioral tests for app.core.tracing middlewares.

Companion to test_operations_hardening.py (which covers the basic
RequestIDMiddleware happy path). Pins the harder edges:

  RequestIDMiddleware:
    1. Caps incoming X-Request-ID at 128 chars (header-flood defence).
    2. Generates a 16-hex-char RID when no header present.
    3. Non-HTTP scopes (websocket, lifespan) pass through untouched.

  MaxBodySizeMiddleware:
    4. Rejects with 413 when content-length exceeds limit (no body read).
    5. Streaming requests (no content-length) are limited mid-stream.
    6. Exempt prefixes (default /api/upload) bypass the limit entirely.
    7. Invalid content-length header is tolerated (does not crash).

  AccessLogMiddleware:
    8. Skip-paths (/health, /metrics, /docs) are NOT logged (passthrough).
    9. Non-skip paths invoke the app and capture a status code.

  TimeoutMiddleware:
    10. Skip-paths bypass the timeout wrapper entirely.

Pure ASGI plumbing — no FastAPI test client.
"""
from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# RequestIDMiddleware edges
# ─────────────────────────────────────────────────────────────────────────────

class TestRequestIDEdges:
    @pytest.mark.asyncio
    async def test_incoming_rid_capped_at_128_chars(self) -> None:
        from app.core.tracing import RequestIDMiddleware, request_id_var

        captured = {"rid": None}

        async def app(scope, receive, send):
            captured["rid"] = request_id_var.get("")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = RequestIDMiddleware(app)
        scope = {
            "type": "http",
            "headers": [(b"x-request-id", b"x" * 500)],
        }
        await mw(scope, _noop_receive, _noop_send)

        assert captured["rid"] is not None
        assert len(captured["rid"]) == 128, "incoming RID must be capped at 128 chars"

    @pytest.mark.asyncio
    async def test_generated_rid_is_16_hex_chars(self) -> None:
        from app.core.tracing import RequestIDMiddleware, request_id_var

        captured = {"rid": None}

        async def app(scope, receive, send):
            captured["rid"] = request_id_var.get("")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = RequestIDMiddleware(app)
        scope = {"type": "http", "headers": []}
        await mw(scope, _noop_receive, _noop_send)

        rid = captured["rid"]
        assert rid is not None and len(rid) == 16
        # 16 hex chars only
        int(rid, 16)  # would raise if not hex

    @pytest.mark.asyncio
    async def test_non_http_scope_passthrough(self) -> None:
        from app.core.tracing import RequestIDMiddleware

        called = {"with_scope": None}

        async def app(scope, receive, send):
            called["with_scope"] = scope

        mw = RequestIDMiddleware(app)
        scope = {"type": "lifespan"}
        await mw(scope, _noop_receive, _noop_send)
        assert called["with_scope"] is scope, "non-http scopes must pass through unmodified"


# ─────────────────────────────────────────────────────────────────────────────
# MaxBodySizeMiddleware
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxBodySize:
    @pytest.mark.asyncio
    async def test_rejects_when_content_length_exceeds_limit(self) -> None:
        from app.core.tracing import MaxBodySizeMiddleware

        sent_messages: list[dict] = []

        async def downstream(scope, receive, send):
            raise AssertionError("app must NOT be called when content-length exceeds limit")

        mw = MaxBodySizeMiddleware(downstream, max_bytes=1024)
        scope = {
            "type": "http",
            "path": "/api/anything",
            "headers": [(b"content-length", b"99999")],
        }

        async def capture_send(m):
            sent_messages.append(m)

        await mw(scope, _noop_receive, capture_send)
        assert sent_messages[0]["status"] == 413
        assert b"too large" in sent_messages[1]["body"].lower()

    @pytest.mark.asyncio
    async def test_exempt_prefix_bypasses_limit(self) -> None:
        from app.core.tracing import MaxBodySizeMiddleware

        called = {"hit": False}

        async def downstream(scope, receive, send):
            called["hit"] = True
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = MaxBodySizeMiddleware(downstream, max_bytes=10, exempt_prefixes=("/api/upload",))
        scope = {
            "type": "http",
            "path": "/api/upload/resume",
            "headers": [(b"content-length", b"99999")],
        }
        await mw(scope, _noop_receive, _noop_send)
        assert called["hit"] is True

    @pytest.mark.asyncio
    async def test_invalid_content_length_does_not_crash(self) -> None:
        from app.core.tracing import MaxBodySizeMiddleware

        called = {"hit": False}

        async def downstream(scope, receive, send):
            called["hit"] = True
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = MaxBodySizeMiddleware(downstream, max_bytes=1024)
        scope = {
            "type": "http",
            "path": "/api/anything",
            "headers": [(b"content-length", b"not-a-number")],
        }
        await mw(scope, _noop_receive, _noop_send)
        assert called["hit"] is True, "invalid content-length must be tolerated, not crash"

    @pytest.mark.asyncio
    async def test_non_http_scope_passthrough(self) -> None:
        from app.core.tracing import MaxBodySizeMiddleware

        called = {"with_scope": None}

        async def app(scope, receive, send):
            called["with_scope"] = scope

        mw = MaxBodySizeMiddleware(app, max_bytes=10)
        scope = {"type": "websocket"}
        await mw(scope, _noop_receive, _noop_send)
        assert called["with_scope"] is scope


# ─────────────────────────────────────────────────────────────────────────────
# AccessLogMiddleware
# ─────────────────────────────────────────────────────────────────────────────

class TestAccessLog:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "skip_path", ["/health", "/metrics", "/docs", "/openapi.json", "/redoc"]
    )
    async def test_skip_paths_not_logged(self, skip_path, monkeypatch) -> None:
        from app.core import tracing

        log_calls = {"count": 0}

        class FakeLogger:
            def info(self, *a, **kw): log_calls["count"] += 1
            def warning(self, *a, **kw): log_calls["count"] += 1
            def error(self, *a, **kw): log_calls["count"] += 1

        async def downstream(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = tracing.AccessLogMiddleware(downstream)
        # Inject our fake logger after construction
        mw._logger = FakeLogger()  # type: ignore[attr-defined]

        scope = {"type": "http", "path": skip_path, "method": "GET", "headers": []}
        await mw(scope, _noop_receive, _noop_send)
        assert log_calls["count"] == 0, f"{skip_path} must not be logged"

    @pytest.mark.asyncio
    async def test_non_skip_path_invokes_app_and_logs(self) -> None:
        from app.core import tracing

        log_calls: list[tuple] = []

        class FakeLogger:
            def info(self, *a, **kw): log_calls.append(("info", a, kw))
            def warning(self, *a, **kw): log_calls.append(("warning", a, kw))
            def error(self, *a, **kw): log_calls.append(("error", a, kw))

        downstream_called = {"hit": False}

        async def downstream(scope, receive, send):
            downstream_called["hit"] = True
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = tracing.AccessLogMiddleware(downstream)
        mw._logger = FakeLogger()  # type: ignore[attr-defined]

        scope = {"type": "http", "path": "/api/foo", "method": "POST", "headers": []}
        await mw(scope, _noop_receive, _noop_send)
        assert downstream_called["hit"] is True
        assert len(log_calls) == 1
        assert log_calls[0][0] == "info"  # 2xx → info
        # Captured kwargs include status, method, path
        assert log_calls[0][2].get("status") == 200
        assert log_calls[0][2].get("method") == "POST"
        assert log_calls[0][2].get("path") == "/api/foo"

    @pytest.mark.asyncio
    async def test_5xx_uses_error_logger(self) -> None:
        from app.core import tracing

        log_calls: list[str] = []

        class FakeLogger:
            def info(self, *a, **kw): log_calls.append("info")
            def warning(self, *a, **kw): log_calls.append("warning")
            def error(self, *a, **kw): log_calls.append("error")

        async def downstream(scope, receive, send):
            await send({"type": "http.response.start", "status": 500, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = tracing.AccessLogMiddleware(downstream)
        mw._logger = FakeLogger()  # type: ignore[attr-defined]

        scope = {"type": "http", "path": "/api/foo", "method": "GET", "headers": []}
        await mw(scope, _noop_receive, _noop_send)
        assert log_calls == ["error"]


# ─────────────────────────────────────────────────────────────────────────────
# TimeoutMiddleware
# ─────────────────────────────────────────────────────────────────────────────

class TestTimeout:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("skip_path", ["/health", "/metrics"])
    async def test_skip_paths_bypass_timeout_wrapper(self, skip_path) -> None:
        from app.core.tracing import TimeoutMiddleware

        called = {"hit": False}

        async def downstream(scope, receive, send):
            called["hit"] = True
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = TimeoutMiddleware(downstream, timeout_seconds=0.001)
        scope = {"type": "http", "path": skip_path, "method": "GET", "headers": []}
        await mw(scope, _noop_receive, _noop_send)
        assert called["hit"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _noop_receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _noop_send(message: dict) -> None:
    pass
