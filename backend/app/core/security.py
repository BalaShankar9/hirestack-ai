"""
HireStack AI – Shared security utilities.

Provides:
  • ``limiter``                – slowapi rate‑limiter instance (shared across routes)
  • ``SecurityHeadersMiddleware`` – ASGI middleware that adds OWASP security headers
  • ``MAX_TOKEN_SIZE``         – hard cap on bearer‑token length to prevent DoS
"""

from __future__ import annotations

from typing import Any, Callable

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# ---------------------------------------------------------------------------
# Rate limiter (import this in route modules instead of creating a new one)
# Uses Redis for persistence when REDIS_URL is available, in-memory otherwise.
# ---------------------------------------------------------------------------
_redis_url = os.getenv("REDIS_URL", "")
_storage_uri = _redis_url if _redis_url and not _redis_url.startswith("redis://localhost") else None

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri,
    default_limits=["100/minute"],
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
        (b"x-xss-protection", b"1; mode=block"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        (b"cache-control", b"no-store"),
        (b"content-security-policy",
         b"default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
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
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )

                # Strip server banner
                headers = [(k, v) for k, v in headers if k.lower() != b"server"]

                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
