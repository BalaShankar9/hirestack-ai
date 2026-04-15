"""
HireStack AI – Shared security utilities.

Provides:
  • ``limiter``                – slowapi rate‑limiter instance (shared across routes)
  • ``get_user_or_ip``         – rate‑limit key: user ID from JWT, falls back to IP
  • ``SecurityHeadersMiddleware`` – ASGI middleware that adds OWASP security headers
  • ``MAX_TOKEN_SIZE``         – hard cap on bearer‑token length to prevent DoS
"""

from __future__ import annotations

from typing import Any, Callable

import base64
import json
import logging
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

from starlette.requests import Request

logger = logging.getLogger("hirestack.security")

# ---------------------------------------------------------------------------
# Rate limiter (import this in route modules instead of creating a new one)
# Uses Redis for persistence when REDIS_URL is available, in-memory otherwise.
# ---------------------------------------------------------------------------
_redis_url = os.getenv("REDIS_URL", "")
_storage_uri = _redis_url if _redis_url and not _redis_url.startswith("redis://localhost") else None


def get_user_or_ip(request: Request) -> str:
    """Extract user ID from JWT Bearer token for per-user rate limiting.

    Falls back to IP address for unauthenticated requests.
    Only reads the unverified payload claim — authentication is handled
    separately by ``get_current_user``.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) < MAX_TOKEN_SIZE:
        token = auth[7:]
        parts = token.split(".")
        if len(parts) == 3:
            try:
                payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                sub = payload.get("sub", "")
                if sub and isinstance(sub, str) and len(sub) < 256:
                    return f"user:{sub}"
            except Exception:
                pass  # malformed token → fall back to IP
    return get_remote_address(request)

limiter = Limiter(
    key_func=get_user_or_ip,
    storage_uri=_storage_uri,
    default_limits=[f"{os.getenv('RATE_LIMIT_REQUESTS', '100')}/minute"],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_TOKEN_SIZE = 8_192  # bytes – well above normal Supabase JWT (~1.5 KB)


# ---------------------------------------------------------------------------
# Security‑headers middleware (pure ASGI – safe for streaming/SSE responses)
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware:
    """
    Lightweight ASGI middleware that injects standard security headers into
    every HTTP response.  Uses the raw ASGI interface (not BaseHTTPMiddleware)
    so it never buffers response bodies – safe for SSE / streaming endpoints.
    """

    # Headers added to every response
    HEADERS: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"0"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()"),
        (b"cache-control", b"no-store"),
        (b"content-security-policy",
         b"default-src 'self'; script-src 'self'; "
         b"style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
         b"font-src 'self' data:; connect-src 'self' https://*.supabase.co wss://*.supabase.co; "
         b"frame-ancestors 'none'"),
    ]

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(self.HEADERS)

                # HSTS – only when behind TLS termination
                forwarded_proto = None
                for hdr_name, hdr_val in scope.get("headers", []):
                    if hdr_name == b"x-forwarded-proto":
                        forwarded_proto = hdr_val.decode()
                        break
                scheme = scope.get("scheme", "http")
                if forwarded_proto == "https" or scheme == "https":
                    headers.append(
                        (b"strict-transport-security", b"max-age=63072000; includeSubDomains; preload")
                    )

                # Cross-Origin isolation headers
                headers.append((b"cross-origin-opener-policy", b"same-origin"))
                headers.append((b"cross-origin-resource-policy", b"same-origin"))

                # Strip server banner
                headers = [(k, v) for k, v in headers if k.lower() != b"server"]

                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
