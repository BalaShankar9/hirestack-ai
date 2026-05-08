# ADR-0033 — Tool sandbox tier classifier (L0 / L1 / L2)

| | |
|---|---|
| **Status** | Accepted 2026-05-08 |
| **Owners** | Platform Core + Security / @BalaShankar9 |
| **Closes** | P0-5 (sandbox-tier half) |
| **Slice** | m7-pr29 |
| **Supersedes** | — |
| **Superseded by** | — |
| **Related** | ADR-0032 (capability tokens — companion), Blueprint §6.3 / §6.4 |

## Context

The dispatcher (`ai_engine/registry/dispatcher.py`) today resolves a
tool's `code_ref` via a caller-supplied `resolver` callable
(`Callable[[str], Callable[..., Awaitable[dict]]]`). Two structural
problems:

1. **No isolation tier on the tool.** Every tool runs in-process with
   the FastAPI worker, holding the same network egress, file-system
   access, and CPU/memory budget as the request loop. A misbehaving or
   malicious tool can exfil arbitrary URLs, blow the worker, or write
   anywhere. This is fine for pure transforms, dangerous for tools that
   accept user-controlled URLs / PII payloads.
2. **`code_ref` is a free-form string.** The resolver in tests does
   `lambda _ref: fn`. There is no canonical RESOLVERS allowlist;
   `scripts/governance/check_architecture.py` AP-4 only forbids new
   `code_ref=` literals outside the registry, which catches the symptom
   not the cause.

Blueprint §6.3 specifies four tiers (L0/L1/L2/L3); §6.4 specifies
`code_ref` as a key into a static RESOLVERS map. This ADR makes both
concrete and is a **prerequisite for L2 sidecar work** (M11) — without
the tier column on the tool catalog, the dispatcher can't safely route.

This is P0 (security) per the same risk register row P0-5 → W5 as
ADR-0032; the two ADRs together close the slice.

## Decision

### Schema (expand → migrate → contract)

New migration `supabase/migrations/20260508010000_ai_tools_sandbox_tier.sql`:

```sql
-- expand
ALTER TABLE ai_tools
    ADD COLUMN IF NOT EXISTS sandbox_tier VARCHAR(2)
        NOT NULL DEFAULT 'L0'
        CHECK (sandbox_tier IN ('L0', 'L1', 'L2', 'L3')),
    ADD COLUMN IF NOT EXISTS egress_allowlist JSONB
        NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS requires_capability_token BOOLEAN
        NOT NULL DEFAULT FALSE;
```

`L3` (Firecracker BYO marketplace) accepted at the constraint level so
the next slice doesn't need a schema change. `requires_capability_token`
is the per-tool kill-switch from ADR-0032 — opt-in per tool until the
global flag flips.

Backfill is a no-op: defaults already match current behaviour (every
existing tool is L0, no egress restrictions, no token required).
Contract phase (drop `DEFAULT 'L0'` once `seed.py` populates every row
explicitly) tracked in slice m7-pr29b — out of scope here.

### Code

New module `ai_engine/registry/sandboxes.py` exposing:

```python
class Sandbox(Protocol):
    async def invoke(
        self,
        fn: Callable[..., Awaitable[dict]],
        *,
        arguments: dict[str, Any],
        record: ToolRecord,
    ) -> dict[str, Any]: ...


class L0InProcessSandbox:        # current behaviour, default
    async def invoke(self, fn, *, arguments, record):
        return await fn(**arguments)


class L1HttpxAllowlistSandbox:   # m7-pr29: dispatch path only; enforcement deferred
    """Routes the call through the same in-process path as L0, but logs
    `tool_sandbox_l1_unenforced` and exposes `record.egress_allowlist`
    on the call's contextvar so future per-tool httpx clients can read
    it. Actual host blocking lands in m7-pr29b once the first real L1
    tool is on the catalog and we know the right interception seam.
    Recording the wire here keeps the DB column honest."""


class L2GrpcSidecarSandbox:      # stub; raises NotImplementedError
    """Placeholder for the tool-runner sidecar (M11). Verifying the ADR
    landed by raising the right error."""
```

New module `ai_engine/registry/resolvers.py` exposing the canonical
`RESOLVERS` allowlist:

```python
# Today's seeded tools (search_user_history, extract_claims) have
# `code_ref` strings pointing to functions that don't exist in
# production yet — the registry has zero production callers, only
# tests. RESOLVERS therefore starts as the empty dict, and `resolve()`
# raises `UnknownCodeRef` for everything. As real resolvers land
# (m7-pr29b+, when the orchestrator first calls Dispatcher.invoke for
# real), each new entry MUST be added here in the same PR — that is
# the AP-4 governance hook. The empty-but-strict map is the load-bearing
# part: it makes "I'll wire the resolver later" impossible.

RESOLVERS: Final[dict[str, Callable[..., Awaitable[dict]]]] = {}


def resolve(code_ref: str) -> Callable[..., Awaitable[dict]]:
    try:
        return RESOLVERS[code_ref]
    except KeyError:
        raise UnknownCodeRef(code_ref)
```

`Dispatcher` no longer accepts a `resolver` parameter from callers;
instead it imports `resolve` from this module. The existing `resolver=`
test seam stays for unit tests via a constructor override (default =
the canonical `resolve`).

### Routing

`Dispatcher.invoke` reads `record.sandbox_tier` → picks one of the three
sandboxes from a registry dict. Behind a new feature flag
`ff_tool_sandbox_tier_routing` (default OFF, sunset **2026-09-01**):

- **Flag OFF** (legacy): all dispatches go through `L0InProcessSandbox`
  regardless of `record.sandbox_tier`. Tier is logged for shadow audit.
- **Flag ON**: tier is enforced. L2 routes raise `NotImplementedError`
  with a structured message naming the tool — making any premature L2
  assignment loud.

### Governance

`scripts/governance/check_architecture.py` AP-4 update: any new
`code_ref=` literal outside `ai_engine/registry/resolvers.py` and the
registry's own seed/tests is a CI fail. `seed.py` is added to the
allowed paths.

## Considered alternatives

- **(A) Per-tool subprocess for everything (no tiers).** Hard latency
  floor of ~30ms per invocation kills agent loops that fire 5-10 tools
  per turn. Tiers exist precisely to amortise that cost.
- **(B) eBPF egress filter at the pod level.** Operationally heavy
  (kernel module, per-host config), and we lose per-tool granularity.
  Useful as defence-in-depth on L2/L3 but doesn't replace per-tool
  allowlists.
- **(C) Seccomp filter at the worker process.** Would kill the FastAPI
  worker on policy violation. Wrong blast radius — we want the violating
  invocation to fail, not the entire request loop.
- **(D) Skip tier classification, jump straight to L2 sidecar for
  everything risky.** Defers the catalog work, but then the dispatcher
  has no way to know which is which — we'd be hand-coding the routing.
  Tier on the row is the least-bad ordering.
- **(E) Static YAML allowlist.** Loses parity with the rest of the
  catalog being DB-backed and forces a redeploy to add an allowed host.

## Consequences

**Positive:**
- Per-tool isolation tier is a first-class catalog field.
- L1 tools get egress allowlist enforcement (the dominant exfil
  surface for tools that fetch arbitrary URLs).
- L2 surface is reserved without committing to an implementation.
- `code_ref` becomes an enumerable allowlist; AP-4 governance becomes
  a strict equality check, not a regex.

**Negative:**
- Migration adds three columns to `ai_tools`. Backwards-compatible
  defaults; no read-side breakage.
- `Dispatcher` constructor surface changes (drops `resolver=` from the
  default path). Test fixtures need a one-line update.
- The L1 httpx interception adds ~50µs per HTTP call (negligible).

**Operational notes:**
- **Rollout order:** ship migration → ship code with flag OFF → set
  `sandbox_tier` per tool in `seed.py` → flip flag for one L1 tool
  in staging → observe `tool_egress_blocked` log for 24h → flip globally
  in prod.
- **Observability:** new structured logs `tool_sandbox_routed`
  (info, every invocation) and `tool_egress_blocked` (warn, every L1
  block). Existing `ai_tool_invocations` row gains no new columns; tier
  is recoverable via JOIN to `ai_tools`.

## Out of scope (deferred — written down so they don't get lost)

- L2 sidecar pod (`tool-runner`) implementation — M11. The stub
  raising `NotImplementedError` is the contract.
- **L1 actual host-blocking enforcement** — m7-pr29b. Today there are
  zero L1 tools on the catalog (every seeded row is L0). Building a
  generic httpx-transport intercept against zero callers ships
  speculative scaffolding. m7-pr29b is gated on the first real L1
  tool entering `seed.py` (Stage-B trigger below).
- L3 Firecracker (third-party BYO tools) — M12+ when the marketplace
  surface ships.
- Per-tool CPU / memory ceiling enforcement — needs cgroups, naturally
  belongs at the L2 boundary.
- Egress allowlist editing UI — DB column is the source of truth;
  ops edit via SQL until M11.
- Contract-phase migration to drop the `DEFAULT 'L0'` once every row is
  populated explicitly — tracked as m7-pr29b, fires after 30 days of
  flag-ON traffic.

## Stage-B revisit triggers

- First tool added with `sandbox_tier='L1'` → triggers m7-pr29b
  (real httpx host-blocking enforcement). Until then the L1 sandbox
  logs `tool_sandbox_l1_unenforced` to make the gap loud.
- First L2 sidecar deploy → revisit `Sandbox.invoke` signature for
  audience claim and serialisation contract.
- Egress allowlist exceeds 5 hosts on any single tool → revisit whether
  that tool actually wants L2 (allowlist drift = isolation failure).
- Any tool needs `sandbox_tier='L3'` → opens the marketplace ADR
  (separate slice).

## Verification

- Unit tests in `ai_engine/tests/registry/test_sandboxes.py` cover:
  L0 passes args through unchanged; L1 blocks a non-allowlisted host;
  L1 passes an allowlisted host; L2 raises with tool name in message.
- Unit tests in `ai_engine/tests/registry/test_resolvers.py` cover:
  unknown `code_ref` raises `UnknownCodeRef`; allowlisted refs resolve.
- Dispatcher integration test confirms tier routing under both flag
  states.
- Governance test confirms AP-4 fails on a planted `code_ref=` outside
  the allowed paths.
