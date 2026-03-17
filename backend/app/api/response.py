"""Standardized API response format for all endpoints."""
from typing import Any, Optional


def success_response(data: Any, meta: Optional[dict] = None) -> dict:
    """Wrap data in standardized success response."""
    resp = {"success": True, "data": data}
    if meta:
        resp["meta"] = meta
    return resp


def error_response(code: str, message: str, details: Optional[dict] = None, status_code: int = 400) -> dict:
    """Build standardized error response body."""
    resp: dict = {"success": False, "error": {"code": code, "message": message}}
    if details:
        resp["error"]["details"] = details
    return resp
