"""Capability tokens for tool invocation (ADR-0032, PR m7-pr29).

A `CapabilityToken` is a one-shot, time-bound, HMAC-signed attestation
that a specific (org_id, user_id, grant_id) tuple is authorised to
invoke a specific tool right now. The dispatcher verifies the token
before calling the tool's resolver — failure raises
``CapabilityInvalid`` (a subclass of ``GrantDenied`` so existing
catch-blocks degrade gracefully).

Wire format::

    base64url(payload_json) + "." + base64url(hmac_sha256(secret, payload_json))

The payload is verbatim — we want integrity, not confidentiality
(the same payload is also written to ``ai_tool_invocations`` for audit).

Replay protection uses Redis ``SET NX EX`` keyed on the nonce, with
TTL = ``max(0, expires_at - now)``. When Redis is unavailable (dev,
unit tests) the module falls back to a process-local LRU set —
loud-warning logged so operators notice.

Module is intentionally self-contained: no FastAPI imports, no Supabase
imports. Callers wire ``settings.tool_capability_secret`` and a Redis
client at construction time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets as _secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── exceptions ─────────────────────────────────────────────────────────


class CapabilityError(PermissionError):
    """Base class for all capability-token failures."""


class CapabilityConfigError(CapabilityError):
    """Mint or verify attempted without a configured secret."""


class CapabilityInvalid(CapabilityError):
    """Token is malformed, expired, tampered with, or replayed."""


# ── data class ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CapabilityToken:
    tool_name: str
    org_id: str
    user_id: str
    grant_id: str
    expires_at: float
    nonce: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "org_id": self.org_id,
            "user_id": self.user_id,
            "grant_id": self.grant_id,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }


# ── replay-protection store ────────────────────────────────────────────


class _NonceStore:
    """Pluggable nonce sink. Implementations claim a nonce once."""

    async def claim(self, nonce: str, ttl_seconds: float) -> bool:
        """Return True if the nonce was newly claimed; False if already seen."""
        raise NotImplementedError


class InProcessNonceStore(_NonceStore):
    """LRU set fallback. Loud-warns on first use; not for production."""

    def __init__(self, *, max_size: int = 10_000) -> None:
        self._max_size = max_size
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._warned = False

    async def claim(self, nonce: str, ttl_seconds: float) -> bool:
        if not self._warned:
            logger.warning(
                "tool_capability_nonce_inprocess_fallback",
                extra={"reason": "redis_unavailable", "max_size": self._max_size},
            )
            self._warned = True
        now = time.time()
        # Evict expired
        expired = [k for k, exp in self._seen.items() if exp <= now]
        for k in expired:
            self._seen.pop(k, None)
        if nonce in self._seen:
            return False
        self._seen[nonce] = now + ttl_seconds
        # Bound size
        while len(self._seen) > self._max_size:
            self._seen.popitem(last=False)
        return True


class RedisNonceStore(_NonceStore):
    """Production replay store. Uses redis SET NX EX. Async client only."""

    def __init__(self, redis_client: Any, *, key_prefix: str = "captok:") -> None:
        self._redis = redis_client
        self._prefix = key_prefix

    async def claim(self, nonce: str, ttl_seconds: float) -> bool:
        # ttl must be >= 1 for SET EX; if token is already expired the
        # caller will have rejected it before reaching here, but guard.
        ttl = max(1, int(ttl_seconds))
        key = f"{self._prefix}{nonce}"
        try:
            # redis-py async returns True on first set, None on collision.
            result = await self._redis.set(key, "1", nx=True, ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tool_capability_nonce_redis_failed",
                extra={"error": str(exc), "key": key},
            )
            # Conservatively reject — better to fail one call than to
            # silently allow replays when Redis is sick.
            raise CapabilityInvalid("nonce_store_unavailable") from exc
        return bool(result)


# ── authorizer ─────────────────────────────────────────────────────────


@dataclass
class Authorizer:
    """Mints and verifies CapabilityTokens.

    ``secret`` is the active HMAC key. ``previous_secret`` (optional) is
    a verify-only key used during rotation overlap. ``default_ttl_seconds``
    is the mint default; per-call override allowed up to ``max_ttl_seconds``.
    """

    secret: bytes
    nonce_store: _NonceStore
    previous_secret: Optional[bytes] = None
    default_ttl_seconds: int = 60
    max_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.secret:
            raise CapabilityConfigError("tool_capability_secret_unset")

    # --- mint ----------------------------------------------------------
    def mint(
        self,
        *,
        tool_name: str,
        org_id: str,
        user_id: str,
        grant_id: str,
        ttl_seconds: Optional[int] = None,
        now: Optional[float] = None,
    ) -> str:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        if ttl <= 0:
            raise CapabilityConfigError(f"ttl_must_be_positive: got {ttl}")
        if ttl > self.max_ttl_seconds:
            raise CapabilityConfigError(
                f"ttl_exceeds_max: {ttl} > {self.max_ttl_seconds}"
            )
        now_s = now if now is not None else time.time()
        token = CapabilityToken(
            tool_name=tool_name,
            org_id=org_id,
            user_id=user_id,
            grant_id=grant_id,
            expires_at=now_s + ttl,
            nonce=_secrets.token_urlsafe(16),
        )
        return _encode(token, self.secret)

    # --- verify --------------------------------------------------------
    async def verify(
        self,
        wire: str,
        *,
        tool_name: str,
        org_id: Optional[str] = None,
        user_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> CapabilityToken:
        token = _decode(wire, self.secret, self.previous_secret)
        now_s = now if now is not None else time.time()
        if token.expires_at <= now_s:
            raise CapabilityInvalid("expired")
        if token.tool_name != tool_name:
            raise CapabilityInvalid(
                f"tool_mismatch: token={token.tool_name} expected={tool_name}"
            )
        if org_id is not None and token.org_id != org_id:
            raise CapabilityInvalid("org_mismatch")
        if user_id is not None and token.user_id != user_id:
            raise CapabilityInvalid("user_mismatch")
        # Replay claim happens AFTER all other checks so a malformed/expired
        # token never burns a nonce slot.
        ttl_remaining = token.expires_at - now_s
        claimed = await self.nonce_store.claim(token.nonce, ttl_remaining)
        if not claimed:
            raise CapabilityInvalid("nonce_replayed")
        return token


# ── codec ──────────────────────────────────────────────────────────────


def _encode(token: CapabilityToken, secret: bytes) -> str:
    payload_bytes = json.dumps(token.to_payload(), sort_keys=True).encode("utf-8")
    sig = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    return f"{_b64(payload_bytes)}.{_b64(sig)}"


def _decode(
    wire: str,
    primary_secret: bytes,
    previous_secret: Optional[bytes],
) -> CapabilityToken:
    if not isinstance(wire, str) or "." not in wire:
        raise CapabilityInvalid("malformed")
    payload_b64, sig_b64 = wire.split(".", 1)
    try:
        payload_bytes = _unb64(payload_b64)
        sig = _unb64(sig_b64)
    except Exception as exc:  # noqa: BLE001
        raise CapabilityInvalid("malformed") from exc

    expected_primary = hmac.new(primary_secret, payload_bytes, hashlib.sha256).digest()
    valid = hmac.compare_digest(sig, expected_primary)
    if not valid and previous_secret:
        expected_prev = hmac.new(previous_secret, payload_bytes, hashlib.sha256).digest()
        valid = hmac.compare_digest(sig, expected_prev)
    if not valid:
        raise CapabilityInvalid("bad_signature")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        return CapabilityToken(
            tool_name=str(payload["tool_name"]),
            org_id=str(payload["org_id"]),
            user_id=str(payload["user_id"]),
            grant_id=str(payload["grant_id"]),
            expires_at=float(payload["expires_at"]),
            nonce=str(payload["nonce"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise CapabilityInvalid("malformed") from exc


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


__all__ = [
    "Authorizer",
    "CapabilityError",
    "CapabilityConfigError",
    "CapabilityInvalid",
    "CapabilityToken",
    "InProcessNonceStore",
    "RedisNonceStore",
]
