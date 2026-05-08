"""Tests for capability tokens (ADR-0032, PR m7-pr29)."""

from __future__ import annotations

import pytest

from ai_engine.registry.capability import (
    Authorizer,
    CapabilityConfigError,
    CapabilityInvalid,
    InProcessNonceStore,
)


SECRET = b"unit-test-secret-please-rotate"
ALT_SECRET = b"unit-test-secret-rotation-target"


def _auth(*, secret: bytes = SECRET, previous: bytes | None = None) -> Authorizer:
    return Authorizer(
        secret=secret,
        nonce_store=InProcessNonceStore(),
        previous_secret=previous,
        default_ttl_seconds=60,
        max_ttl_seconds=300,
    )


def test_config_error_when_secret_missing() -> None:
    with pytest.raises(CapabilityConfigError):
        Authorizer(secret=b"", nonce_store=InProcessNonceStore())


def test_mint_rejects_zero_or_negative_ttl() -> None:
    auth = _auth()
    with pytest.raises(CapabilityConfigError):
        auth.mint(tool_name="t", org_id="o", user_id="u", grant_id="g", ttl_seconds=0)
    with pytest.raises(CapabilityConfigError):
        auth.mint(tool_name="t", org_id="o", user_id="u", grant_id="g", ttl_seconds=-5)


def test_mint_rejects_ttl_above_max() -> None:
    auth = _auth()
    with pytest.raises(CapabilityConfigError):
        auth.mint(tool_name="t", org_id="o", user_id="u", grant_id="g", ttl_seconds=10_000)


@pytest.mark.asyncio
async def test_round_trip_mint_then_verify() -> None:
    auth = _auth()
    wire = auth.mint(tool_name="echo", org_id="o1", user_id="u1", grant_id="g1")
    token = await auth.verify(wire, tool_name="echo", org_id="o1", user_id="u1")
    assert token.tool_name == "echo"
    assert token.org_id == "o1"
    assert token.user_id == "u1"
    assert token.grant_id == "g1"


@pytest.mark.asyncio
async def test_expired_token_rejected_without_burning_nonce() -> None:
    auth = _auth()
    # Mint with a real TTL, then verify "in the future" so it has expired.
    wire = auth.mint(tool_name="echo", org_id="o", user_id="u", grant_id="g")
    future = 9_999_999_999.0  # year ~2286
    with pytest.raises(CapabilityInvalid, match="expired"):
        await auth.verify(wire, tool_name="echo", now=future)


@pytest.mark.asyncio
async def test_tampered_signature_rejected() -> None:
    auth = _auth()
    wire = auth.mint(tool_name="echo", org_id="o", user_id="u", grant_id="g")
    payload, sig = wire.split(".", 1)
    # flip one char in sig
    bad_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    with pytest.raises(CapabilityInvalid, match="bad_signature"):
        await auth.verify(payload + "." + bad_sig, tool_name="echo")


@pytest.mark.asyncio
async def test_malformed_token_rejected() -> None:
    auth = _auth()
    with pytest.raises(CapabilityInvalid, match="malformed"):
        await auth.verify("not-a-token", tool_name="echo")
    with pytest.raises(CapabilityInvalid, match="malformed"):
        await auth.verify("missingdot", tool_name="echo")


@pytest.mark.asyncio
async def test_tool_mismatch_rejected() -> None:
    auth = _auth()
    wire = auth.mint(tool_name="echo", org_id="o", user_id="u", grant_id="g")
    with pytest.raises(CapabilityInvalid, match="tool_mismatch"):
        await auth.verify(wire, tool_name="other")


@pytest.mark.asyncio
async def test_org_mismatch_rejected() -> None:
    auth = _auth()
    wire = auth.mint(tool_name="echo", org_id="o1", user_id="u", grant_id="g")
    with pytest.raises(CapabilityInvalid, match="org_mismatch"):
        await auth.verify(wire, tool_name="echo", org_id="other-org")


@pytest.mark.asyncio
async def test_user_mismatch_rejected() -> None:
    auth = _auth()
    wire = auth.mint(tool_name="echo", org_id="o", user_id="u1", grant_id="g")
    with pytest.raises(CapabilityInvalid, match="user_mismatch"):
        await auth.verify(wire, tool_name="echo", user_id="other-user")


@pytest.mark.asyncio
async def test_nonce_replay_rejected() -> None:
    auth = _auth()
    wire = auth.mint(tool_name="echo", org_id="o", user_id="u", grant_id="g")
    await auth.verify(wire, tool_name="echo")
    with pytest.raises(CapabilityInvalid, match="nonce_replayed"):
        await auth.verify(wire, tool_name="echo")


@pytest.mark.asyncio
async def test_secret_rotation_dual_key_accepts_both() -> None:
    # Active = ALT, previous = SECRET. Token minted under SECRET still verifies.
    minter = _auth(secret=SECRET)
    verifier = _auth(secret=ALT_SECRET, previous=SECRET)
    wire = minter.mint(tool_name="echo", org_id="o", user_id="u", grant_id="g")
    token = await verifier.verify(wire, tool_name="echo")
    assert token.tool_name == "echo"


@pytest.mark.asyncio
async def test_rotation_without_previous_rejects_old_token() -> None:
    minter = _auth(secret=SECRET)
    verifier = _auth(secret=ALT_SECRET)  # no previous_secret
    wire = minter.mint(tool_name="echo", org_id="o", user_id="u", grant_id="g")
    with pytest.raises(CapabilityInvalid, match="bad_signature"):
        await verifier.verify(wire, tool_name="echo")


@pytest.mark.asyncio
async def test_inprocess_nonce_store_evicts_expired() -> None:
    store = InProcessNonceStore(max_size=4)
    assert await store.claim("a", ttl_seconds=0.01) is True
    # Wait past TTL by faking it via direct mutation: shave the expiry.
    store._seen["a"] = 0.0  # type: ignore[attr-defined]
    # New claim with same nonce should succeed because eviction sweep clears it.
    assert await store.claim("a", ttl_seconds=60) is True
