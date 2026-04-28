"""Tests for operational hardening: HTML sanitization, request tracing, input validation."""
import pytest


# ═══════════════════════════════════════════════════════════════════════
#  HTML Sanitization
# ═══════════════════════════════════════════════════════════════════════

class TestHTMLSanitization:
    """Ensure AI-generated HTML is sanitized before reaching the frontend."""

    def test_strips_script_tags(self):
        from app.core.sanitize import sanitize_html

        html = '<div>Hello</div><script>alert("xss")</script><p>World</p>'
        result = sanitize_html(html)
        assert "<script>" not in result
        assert "alert" not in result
        assert "<div>Hello</div>" in result
        assert "<p>World</p>" in result

    def test_strips_event_handlers(self):
        from app.core.sanitize import sanitize_html

        html = '<div onmouseover="alert(1)">Hover me</div>'
        result = sanitize_html(html)
        assert "onmouseover" not in result
        assert "Hover me" in result

    def test_strips_javascript_uri(self):
        from app.core.sanitize import sanitize_html

        html = '<a href="javascript:alert(1)">Click</a>'
        result = sanitize_html(html)
        assert "javascript:" not in result

    def test_strips_iframe(self):
        from app.core.sanitize import sanitize_html

        html = '<p>Safe</p><iframe src="http://evil.com"></iframe>'
        result = sanitize_html(html)
        assert "<iframe" not in result
        assert "<p>Safe</p>" in result

    def test_strips_form_and_input(self):
        from app.core.sanitize import sanitize_html

        html = '<form action="/hack"><input type="text" name="pw"/></form>'
        result = sanitize_html(html)
        assert "<form" not in result
        assert "<input" not in result

    def test_preserves_safe_html(self):
        from app.core.sanitize import sanitize_html

        html = (
            '<div class="cv-header"><h1>Jane Doe</h1>'
            '<p><strong>Senior Engineer</strong></p>'
            '<ul><li>Python</li><li>FastAPI</li></ul>'
            '<table><tr><td>Skill</td><td>Level</td></tr></table>'
            '</div>'
        )
        result = sanitize_html(html)
        assert "<h1>Jane Doe</h1>" in result
        assert "<strong>Senior Engineer</strong>" in result
        assert "<li>Python</li>" in result
        assert "<table>" in result

    def test_preserves_style_attribute(self):
        from app.core.sanitize import sanitize_html

        html = '<div style="margin-top: 10px; color: #333">Styled</div>'
        result = sanitize_html(html)
        assert 'style="' in result

    def test_preserves_img_with_safe_src(self):
        from app.core.sanitize import sanitize_html

        html = '<img src="https://example.com/photo.jpg" alt="Photo" />'
        result = sanitize_html(html)
        assert "https://example.com/photo.jpg" in result

    def test_truncates_oversized_html(self):
        from app.core.sanitize import sanitize_html

        huge = "<p>" + "x" * 2_000_000 + "</p>"
        result = sanitize_html(huge, max_size=1000)
        assert len(result) <= 1100  # some overhead from tag structure

    def test_handles_empty_and_none(self):
        from app.core.sanitize import sanitize_html

        assert sanitize_html("") == ""
        assert sanitize_html(None) == ""  # type: ignore[arg-type]
        assert sanitize_html(123) == ""   # type: ignore[arg-type]

    def test_strips_object_embed_tags(self):
        from app.core.sanitize import sanitize_html

        html = '<object data="evil.swf"></object><embed src="evil.swf">'
        result = sanitize_html(html)
        assert "<object" not in result
        assert "<embed" not in result

    def test_nested_xss_in_attribute(self):
        from app.core.sanitize import sanitize_html

        html = '<div style="background:url(javascript:alert(1))">Test</div>'
        result = sanitize_html(html)
        # nh3 keeps the style but strips the javascript: part
        assert "javascript:" not in result


# ═══════════════════════════════════════════════════════════════════════
#  Request ID Tracing
# ═══════════════════════════════════════════════════════════════════════

class TestRequestIDTracing:
    """Ensure X-Request-ID is propagated through middleware."""

    def test_request_id_var_default(self):
        from app.core.tracing import request_id_var

        assert request_id_var.get("") == ""

    def test_request_id_var_set_and_get(self):
        from app.core.tracing import request_id_var

        token = request_id_var.set("test-123")
        assert request_id_var.get("") == "test-123"
        request_id_var.reset(token)
        assert request_id_var.get("") == ""

    @pytest.mark.asyncio
    async def test_middleware_sets_response_header(self):
        from app.core.tracing import RequestIDMiddleware

        captured_headers = {}

        async def dummy_app(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({
                "type": "http.response.body",
                "body": b"ok",
            })

        middleware = RequestIDMiddleware(dummy_app)

        async def mock_send(message):
            if message["type"] == "http.response.start":
                for name, value in message.get("headers", []):
                    captured_headers[name] = value

        scope = {"type": "http", "headers": []}

        async def mock_receive():
            return {"type": "http.request", "body": b""}

        await middleware(scope, mock_receive, mock_send)
        assert b"x-request-id" in captured_headers
        assert len(captured_headers[b"x-request-id"]) > 0

    @pytest.mark.asyncio
    async def test_middleware_honours_incoming_rid(self):
        from app.core.tracing import RequestIDMiddleware, request_id_var

        captured_rid = None

        async def dummy_app(scope, receive, send):
            nonlocal captured_rid
            captured_rid = request_id_var.get("")
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = RequestIDMiddleware(dummy_app)
        scope = {
            "type": "http",
            "headers": [(b"x-request-id", b"my-trace-id")],
        }

        async def noop_receive():
            return {"type": "http.request"}

        async def noop_send(m):
            pass

        await middleware(scope, noop_receive, noop_send)
        assert captured_rid == "my-trace-id"


# ═══════════════════════════════════════════════════════════════════════
#  Input Validation
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineInputValidation:
    """PipelineRequest and GenerationJobRequest validation."""

    def test_rejects_empty_job_title(self):
        from app.api.routes.generate import PipelineRequest, _validate_pipeline_input
        from fastapi import HTTPException

        req = PipelineRequest(job_title="", jd_text="Some JD")
        with pytest.raises(HTTPException) as exc_info:
            _validate_pipeline_input(req)
        assert exc_info.value.status_code == 400

    def test_rejects_empty_jd(self):
        from app.api.routes.generate import PipelineRequest, _validate_pipeline_input
        from fastapi import HTTPException

        req = PipelineRequest(job_title="Engineer", jd_text="  ")
        with pytest.raises(HTTPException) as exc_info:
            _validate_pipeline_input(req)
        assert exc_info.value.status_code == 400

    def test_rejects_oversized_jd(self):
        from app.api.routes.generate import PipelineRequest, _validate_pipeline_input
        from fastapi import HTTPException

        # Use varied text to avoid garbage detection, but exceed 50KB hard limit
        req = PipelineRequest(job_title="Engineer", jd_text="Senior Software Engineer role. " * 2000)
        with pytest.raises(HTTPException) as exc_info:
            _validate_pipeline_input(req)
        assert exc_info.value.status_code == 413

    def test_rejects_oversized_resume(self):
        from app.api.routes.generate import PipelineRequest, _validate_pipeline_input
        from fastapi import HTTPException

        req = PipelineRequest(
            job_title="Engineer",
            jd_text="Looking for a senior engineer with Python experience.",
            resume_text="x" * 101_000,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_pipeline_input(req)
        assert exc_info.value.status_code == 413

    def test_accepts_valid_input(self):
        from app.api.routes.generate import PipelineRequest, _validate_pipeline_input

        req = PipelineRequest(
            job_title="Senior Engineer",
            jd_text="Looking for a senior engineer with 5+ years...",
            resume_text="I have 6 years experience...",
        )
        # Should not raise
        _validate_pipeline_input(req)


class TestGenerationJobInputValidation:
    """GenerationJobRequest pydantic validation."""

    def test_rejects_empty_application_id(self):
        from pydantic import ValidationError
        from app.api.routes.generate import GenerationJobRequest

        with pytest.raises(ValidationError):
            GenerationJobRequest(application_id="   ")

    def test_rejects_unknown_module(self):
        from pydantic import ValidationError
        from app.api.routes.generate import GenerationJobRequest

        with pytest.raises(ValidationError):
            GenerationJobRequest(
                application_id="app-123",
                requested_modules=["cv", "evil_module"],
            )

    def test_rejects_too_many_modules(self):
        from pydantic import ValidationError
        from app.api.routes.generate import GenerationJobRequest

        with pytest.raises(ValidationError):
            GenerationJobRequest(
                application_id="app-123",
                requested_modules=["cv"] * 25,
            )

    def test_accepts_valid_job_request(self):
        from app.api.routes.generate import GenerationJobRequest

        req = GenerationJobRequest(
            application_id="app-123",
            requested_modules=["cv", "cover_letter"],
        )
        assert req.application_id == "app-123"
        assert req.requested_modules == ["cv", "cover_letter"]

    def test_accepts_empty_modules(self):
        from app.api.routes.generate import GenerationJobRequest

        req = GenerationJobRequest(application_id="app-456")
        assert req.requested_modules == []


# ═══════════════════════════════════════════════════════════════════════
#  Retry Logic
# ═══════════════════════════════════════════════════════════════════════

class TestRetryClassification:
    """Verify that the retry decision logic is correct."""

    def test_quota_exhaustion_not_retryable(self):
        from ai_engine.client import _is_retryable, _is_quota_exhausted

        err = Exception("GenerateRequestsPerDay quota exhausted")
        assert _is_quota_exhausted(err) is True
        assert _is_retryable(err) is False

    def test_rate_limit_is_retryable(self):
        from ai_engine.client import _is_retryable

        err = Exception("Resource exhausted: rate limit hit, retry in 30s")
        assert _is_retryable(err) is True

    def test_auth_error_not_retryable(self):
        from ai_engine.client import _is_retryable

        err = Exception("API key not valid. Please check your key.")
        assert _is_retryable(err) is False

    def test_generic_error_is_retryable(self):
        from ai_engine.client import _is_retryable

        err = Exception("Connection reset by peer")
        assert _is_retryable(err) is True

    def test_permission_denied_not_retryable(self):
        from ai_engine.client import _is_retryable

        err = Exception("Permission denied for model gemini-2.5-pro")
        assert _is_retryable(err) is False


# ═══════════════════════════════════════════════════════════════════════
#  Error Classification
# ═══════════════════════════════════════════════════════════════════════

class TestErrorClassification:
    """Verify AI error classification produces correct HTTP codes."""

    def test_classifies_401_for_invalid_key(self):
        from app.api.routes.generate import _classify_ai_error

        result = _classify_ai_error(Exception("API key not valid"))
        assert result is not None
        assert result["code"] == 401

    def test_classifies_429_for_rate_limit(self):
        from app.api.routes.generate import _classify_ai_error

        result = _classify_ai_error(Exception("Resource exhausted: 429"))
        assert result is not None
        assert result["code"] == 429

    def test_classifies_403_for_permission(self):
        from app.api.routes.generate import _classify_ai_error

        result = _classify_ai_error(Exception("Permission denied"))
        assert result is not None
        assert result["code"] == 403

    def test_returns_none_for_unknown_error(self):
        from app.api.routes.generate import _classify_ai_error

        result = _classify_ai_error(Exception("Something weird happened"))
        assert result is None

    def test_retry_after_parsed_from_gemini_message(self):
        from app.api.routes.generate import _extract_retry_after_seconds

        assert _extract_retry_after_seconds("Please retry in 51.7469s.") == 52
        assert _extract_retry_after_seconds("retryDelay': '30s'") == 30
        assert _extract_retry_after_seconds("No retry info here") is None


# ═══════════════════════════════════════════════════════════════════════
#  Security Headers Middleware
# ═══════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    """Verify security headers are injected."""

    @pytest.mark.asyncio
    async def test_adds_security_headers(self):
        from app.core.security import SecurityHeadersMiddleware

        captured_headers = {}

        async def dummy_app(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = SecurityHeadersMiddleware(dummy_app)

        async def mock_send(message):
            if message["type"] == "http.response.start":
                for name, value in message.get("headers", []):
                    captured_headers[name] = value

        scope = {"type": "http", "headers": []}
        await middleware(scope, lambda: {"type": "http.request"}, mock_send)

        assert b"x-content-type-options" in captured_headers
        assert captured_headers[b"x-content-type-options"] == b"nosniff"
        assert b"x-frame-options" in captured_headers
        assert captured_headers[b"x-frame-options"] == b"DENY"
