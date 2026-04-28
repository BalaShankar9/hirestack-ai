"""Standardized API response format for all endpoints."""
from typing import Any, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.core.tracing import request_id_var


def success_response(data: Any, meta: Optional[dict] = None) -> dict:
    """Wrap data in standardized success response."""
    resp = {"success": True, "data": data}
    if meta:
        resp["meta"] = meta
    return resp


def error_envelope(
    code: str,
    message: str,
    *,
    details: Optional[dict] = None,
    request_id: Optional[str] = None,
) -> dict:
    """Build a standardized error envelope body.

    Shape:
        {"success": false, "error": {"code", "message", "details", "request_id"}}

    `request_id` falls back to the active `request_id_var` ContextVar so callers
    inside a request scope rarely need to pass it explicitly.
    """
    if not code or not isinstance(code, str):
        raise ValueError("error_response: code must be a non-empty string")
    if not message or not isinstance(message, str):
        raise ValueError("error_response: message must be a non-empty string")

    rid = request_id if request_id is not None else request_id_var.get("")
    err: dict = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    if rid:
        err["request_id"] = rid
    return {"success": False, "error": err}


def error_response(
    code: str,
    message: str,
    *,
    status_code: int = 400,
    details: Optional[dict] = None,
    request_id: Optional[str] = None,
    headers: Optional[dict] = None,
) -> JSONResponse:
    """Return a JSONResponse carrying the standardized error envelope."""
    body = error_envelope(
        code, message, details=details, request_id=request_id
    )
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def error_http_exception(
    code: str,
    message: str,
    *,
    status_code: int = 400,
    details: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> HTTPException:
    """Build an HTTPException whose detail is the standardized error envelope.

    Useful for `raise` sites that want FastAPI's exception machinery to kick in
    while still emitting the envelope shape via the global handler.
    """
    body = error_envelope(code, message, details=details)
    return HTTPException(status_code=status_code, detail=body, headers=headers)


