"""Standardized API response format for all endpoints."""
from typing import Any, Optional


def success_response(data: Any, meta: Optional[dict] = None) -> dict:
    """Wrap data in standardized success response."""
    resp = {"success": True, "data": data}
    if meta:
        resp["meta"] = meta
    return resp


