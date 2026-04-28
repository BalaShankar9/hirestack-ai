"""Tests for standardized response/error envelope helpers (S1-F6)."""
import json

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.api.response import (
    error_envelope,
    error_http_exception,
    error_response,
    success_response,
)
from app.core.tracing import request_id_var


def _body(resp: JSONResponse) -> dict:
    return json.loads(resp.body.decode("utf-8"))


# ---------- success_response (existing contract) ---------------------------


def test_success_response_minimal():
    assert success_response({"x": 1}) == {"success": True, "data": {"x": 1}}


def test_success_response_with_meta():
    out = success_response([1, 2], meta={"page": 3})
    assert out == {"success": True, "data": [1, 2], "meta": {"page": 3}}


# ---------- error_envelope --------------------------------------------------


def test_error_envelope_basic_shape():
    env = error_envelope("BAD_INPUT", "nope")
    assert env["success"] is False
    assert env["error"]["code"] == "BAD_INPUT"
    assert env["error"]["message"] == "nope"
    assert "details" not in env["error"]
    assert "request_id" not in env["error"]


def test_error_envelope_includes_details_and_request_id():
    env = error_envelope(
        "RATE_LIMITED",
        "slow down",
        details={"retry_after": 5},
        request_id="rid-123",
    )
    assert env["error"]["details"] == {"retry_after": 5}
    assert env["error"]["request_id"] == "rid-123"


def test_error_envelope_pulls_request_id_from_contextvar():
    token = request_id_var.set("ctx-rid-42")
    try:
        env = error_envelope("X", "y")
    finally:
        request_id_var.reset(token)
    assert env["error"]["request_id"] == "ctx-rid-42"


def test_error_envelope_omits_empty_request_id():
    env = error_envelope("X", "y")  # default ContextVar is ""
    assert "request_id" not in env["error"]


def test_error_envelope_rejects_blank_code():
    with pytest.raises(ValueError):
        error_envelope("", "msg")


def test_error_envelope_rejects_blank_message():
    with pytest.raises(ValueError):
        error_envelope("CODE", "")


def test_error_envelope_explicit_request_id_overrides_contextvar():
    token = request_id_var.set("ctx-rid")
    try:
        env = error_envelope("X", "y", request_id="explicit-rid")
    finally:
        request_id_var.reset(token)
    assert env["error"]["request_id"] == "explicit-rid"


# ---------- error_response (JSONResponse) -----------------------------------


def test_error_response_default_status_400():
    resp = error_response("BAD", "nope")
    assert resp.status_code == 400
    body = _body(resp)
    assert body["success"] is False
    assert body["error"]["code"] == "BAD"


def test_error_response_custom_status_and_headers():
    resp = error_response(
        "RATE_LIMITED",
        "throttle",
        status_code=429,
        details={"retry_after": 30},
        headers={"Retry-After": "30"},
    )
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "30"
    body = _body(resp)
    assert body["error"]["details"] == {"retry_after": 30}


def test_error_response_returns_json_content_type():
    resp = error_response("X", "y")
    assert resp.headers.get("content-type", "").startswith("application/json")


# ---------- error_http_exception -------------------------------------------


def test_error_http_exception_carries_envelope():
    exc = error_http_exception("NOT_FOUND", "missing", status_code=404)
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail["success"] is False
    assert exc.detail["error"]["code"] == "NOT_FOUND"


def test_error_http_exception_includes_headers():
    exc = error_http_exception(
        "AUTH_REQUIRED",
        "login",
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )
    assert exc.headers == {"WWW-Authenticate": "Bearer"}
