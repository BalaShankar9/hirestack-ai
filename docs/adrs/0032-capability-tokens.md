# ADR-0032 — Capability tokens for tool invocation

| | |
|---|---|
| **Status** | Accepted 2026-05-08 |
| **Owners** | Platform Core + Security / @BalaShankar9 |
| **Closes** | P0-5 (capability tokens half) |
| **Slice** | m7-pr29 |
| **Supersedes** | — |
| **Superseded by** | — |
| **Related** | ADR-0033 (sandbox tier classifier — companion), Blueprint §6.5 |

## Context

The dispatcher (`ai_engine/registry/dispatcher.py`, ADR-0023 / m5-pr14)
today gates each tool invocation only on `(agent_name, tool_name)` grants
read from `ai_agent_tool_grants`. There is no per-call attestation that
the invocation was authorised at the right scope (org / user / job),
no expiry, and no nonce — meaning:

- Any code path that can call `Dispatcher.invoke(tool_name=...)` with
  the right `agent_name` and a granted tool can exfiltrate or mutate
  data tied to **any** org/user, because `org_id` / `user_id` are just
  audit-log fields today, not enforcement boundaries.
- A leaked grant row stays valid forever (no expiry).
- A reused message (replay) is indistinguishable from a fresh one.

The blueprint §6.5 specifies `CapabilityToken(tool_name, org_id, user_id,
grant_id, expires_at, nonce)`, minted by an Authorizer, **one-shot, time-
bound**. This ADR makes that concrete.

This is P0 (security) per `WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`
risk register row P0-5 → W5.

## Decision

Introduce a new module `ai_engine/registry/capability.py` exposing:

```python
@dataclass(frozen=True)
class CapabilityToken:
    tool_name: str
    org_id: str
    user_id: str
    grant_id: str       # UUID of the (agent, tool) grant row that authorised it
    expires_at: float   # absolute monotonic-equivalent unix epoch seconds
    nonce: str          # 128-bit, base64url, single-use


def mint(
    *,
    tool_name: str,
    org_id: str,
    user_id: str,
    grant_id: str,
    ttl_seconds: int = 60,
) -> str: ...


def verify(token: str, *, tool_name: str, now: float | None = None) -> CapabilityToken: ...
```

Wire format: `b64url(json(payload)).b64url(hmac_sha256(secret, payload))`.

- **Secret**: `settings.tool_capability_secret` (32-byte env-injected
  key, rotated on `expand → migrate → contract` schedule via dual-key
  verify; see Operational notes).
- **Replay protection**: `verify()` atomically claims the nonce in
  Redis with `SET NX EX = max(0, expires_at - now)`. Second `verify`
  for the same nonce raises `CapabilityReplayed`. Falls back to an
  in-process LRU set when Redis is unavailable (dev / unit tests).
- **Clock**: `time.time()` (wall clock). Acceptable because tokens are
  short-lived (default 60s, max 5 min) and any pod-clock skew up to a
  few seconds is masked by the TTL slack — the dispatcher is the sole
  consumer.

Dispatcher integration is gated by a new feature flag
`ff_tool_capability_tokens` (default OFF, sunset **2026-09-01**):

- **Flag OFF** (legacy, default for migration window): existing
  `(agent, tool)` grant check only. Tokens are *minted* opportunistically
  and logged but not required.
- **Flag ON**: dispatcher requires `capability_token=` argument; passes
  it to `verify()`. Failure surfaces as a new `GrantDenied` subclass
  `CapabilityInvalid` (so existing callers that already catch
  `GrantDenied` degrade gracefully).

Mint happens at the dispatcher's caller boundary (the agent
orchestrator), where the (org_id, user_id, job_id) context is available.
The `_run_generation_job_via_runtime` task already carries this context
in `RuntimeContext` (see `ai_engine/agents/orchestrator.py`).

## Considered alternatives

- **(A) In-process dataclass + nonce set.** Cheap, zero crypto. Rejected
  because it assumes the dispatcher always runs in the same process as
  the mint site. The L2 tier (ADR-0033, sidecar gRPC `tool-runner`) breaks
  this assumption; we'd be re-doing this slice. HMAC tokens cross
  process boundaries today and forward-compat the L2 work.
- **(B) JWT (PyJWT).** Heavy dependency for a 7-field payload. We don't
  need RS256 / key rotation tooling at this surface — HMAC-SHA256 with
  one rotated secret is sufficient and ~30 lines of stdlib.
- **(C) Database-row tokens.** Requires a write per mint and a read per
  verify, both on the hot path. Replay protection is much cheaper in
  Redis SETNX than in PG.
- **(D) `cryptography.fernet`.** Encrypts the payload — unnecessary
  because the payload is `(tool_name, org_id, user_id, grant_id,
  expires_at, nonce)` and is also written verbatim to
  `ai_tool_invocations` for audit. We need integrity, not confidentiality.

## Consequences

**Positive:**
- Per-call attestation at (org, user, grant, time) granularity.
- Replay-resistant via Redis SETNX nonce.
- L2 sidecar (ADR-0033) can verify the same token without a process
  boundary; no scheme rework needed.
- Forward-compatible with secret rotation (dual-key verify list).

**Negative:**
- One Redis SETNX per dispatch when the flag is on. Cost: ~0.3ms; well
  within the existing per-invocation budget.
- New env var `TOOL_CAPABILITY_SECRET` required in production.
  Bootstrap missing → mint raises `CapabilityConfigError` and
  `_run_generation_job_via_runtime` falls back to logged-and-fail path.
- Existing dispatcher callers that don't pass `capability_token=` start
  failing the moment the flag flips ON. Mitigated by:
  (i) flag default OFF + sunset date; (ii) staged rollout per-tool via
  per-tool kill-switch in `ai_tools.requires_capability_token` (added
  in m7-pr29 migration); (iii) audit-log review pre-flip.

**Operational notes:**
- **Secret rotation**: `settings.tool_capability_secret` is the active
  signing key. `settings.tool_capability_secret_previous` (optional) is
  an additional verify-only key used for the rotation overlap. Rotation
  procedure:
  1. (expand) deploy with `previous = old`, `active = new`.
  2. Wait 2× max-TTL (10 min by default) for old tokens to expire.
  3. (contract) deploy with `previous = ""`.
- **Observability**: new structured log `tool_capability_invalid`
  (reason ∈ `expired | bad_signature | nonce_replayed | malformed |
  config_error`). Counter increment on each failure.

## Out of scope (deferred — written down so they don't get lost)

- An `Authorizer` service that issues tokens via gRPC — current mint
  site is the agent orchestrator, which already holds the auth context.
  Promoting to a service is M11+ when third-party agents enter the
  picture.
- Per-token *audience* (e.g. tool-runner pod identity) — tied to L2
  rollout. Stage-B trigger: first L2 sidecar deploy.
- Cryptographic key in HSM / KMS — for now, env-var injected from
  the same secret store as everything else (Doppler / Railway).

## Stage-B revisit triggers

- More than 0.5% of dispatches log `tool_capability_invalid: bad_signature`
  → investigate clock skew or secret rotation bug.
- First production L2 sidecar deploy → revisit for audience claim.
- Third-party agent surface lands → revisit Authorizer-as-service.

## Verification

- Unit tests in `ai_engine/tests/registry/test_capability.py` cover
  mint/verify round-trip, expiry, malformed payload, bad signature,
  nonce replay (in-process and via Redis fake), tampered payload,
  secret-rotation dual-key verify.
- Dispatcher integration test confirms: flag OFF passes through legacy
  path; flag ON requires token; missing token raises `CapabilityInvalid`.
