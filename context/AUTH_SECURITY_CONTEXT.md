---
title: Auth & Security Context
last_synced: 2026-05-08
watch_paths:
  - backend/app/core/security.py
  - backend/app/api/deps.py
  - backend/main.py
  - backend/tests/security
  - ai_engine/registry
  - ai_engine/tools
canonical_sources:
  - SECURITY.md
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#11-security
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#6-ai-runtime-standards
update_when:
  - JWT signing alg or claim shape changes
  - a new middleware is added or order changes
  - a new sandbox tier is added (L0..L3)
  - the capability token shape changes (org_id, user_id, grant_id, expires_at, nonce)
  - SSRF safe_fetch policy changes
  - prompt-injection defenses change
  - RLS policy template changes
---

# Auth & Security Context

> Security in this repo is **layered, not perimeter**. Every layer assumes
> the previous one might fail. The result: even a successful prompt
> injection cannot exfiltrate cross-tenant data, because RLS + capability
> tokens + sandbox tiers each independently veto the action.

---

## TL;DR — 12 lines

1. **Authentication is Supabase JWT** (RS256 in production, HS256 allowed
   in dev with explicit env var).
2. **Authorization is two-layer:** FastAPI scope checks at the route
   (`Depends(require_scope("..."))`) AND Postgres RLS at the data layer.
3. **All multi-tenant tables enforce RLS** keyed on `org_id` (64/64
   today). Regression test
   [`tests/security/test_tenancy_isolation.py`](../backend/tests/security/test_tenancy_isolation.py)
   blocks merges that introduce a non-RLS table.
4. **Idempotency keys** stored 24h in `idempotency_keys`; middleware
   replays cached responses (P0-6 SHIPPED).
5. **Rate limiting** via slowapi + Redis (token bucket). Required in
   production; tests assert `RateLimitExceeded` raises 429 with
   `Retry-After`.
6. **SSRF defense** is `ai_engine.tools.fetch.safe_fetch` (P0-2 SHIPPED):
   IP-pinning, deny private/loopback/link-local, deny redirects to private,
   per-org bandwidth budget, scheme allowlist (http/https only).
7. **Prompt injection defenses** are five layers (blueprint §6.5):
   detect → sanitize → wrap → limit privilege → post-output guard.
8. **Tool registry + capability tokens** (P0-5 SHIPPED — m7-pr29). Every
   tool call requires a `CapabilityToken` carrying `(org_id, user_id,
   grant_id, expires_at, nonce)`. The orchestrator (never the LLM) signs.
9. **Sandbox tiers L0–L3** (blueprint §6.3) gate what side effects a tool
   can perform. L3 (write to user data) requires explicit grant.
10. **Secrets** never committed. `.env` patterns scanned by GitHub secret
    scanning. `pre-commit` hook for new files (`gitleaks`).
11. **Sentry redaction depth = 16** (TD-2 SHIPPED). Before-send scrubs
    PII (email, phone, address, JD/resume body) at every depth.
12. **Vulnerability hygiene:** `pyjwt 2.12+` (CVE-2026-32597), `pytest
    9.0.3+` (CVE-2025-71176). Dependency audit promoted to CI-required
    gate (m12-pr04).

---

## JWT contract

Issued by Supabase Auth on login. Verified by
`backend/app/core/security.py:verify_jwt()` and the
`JWTAuthMiddleware`.

Required claims:

```jsonc
{
  "sub": "usr_...",            // user_id
  "org_id": "org_...",          // current active org
  "cell_id": "us-east/shard-0", // ADR-0030; routed by API gateway
  "role": "owner | admin | member | viewer",
  "scopes": ["application:write", "billing:read", ...],
  "iat": 0, "exp": 0, "iss": "supabase", "aud": "authenticated"
}
```

The middleware sets `request.state.user` with the validated claims and
also writes the JWT into `request.jwt.claims` (per-connection GUC) so RLS
sees the same `org_id` on every query.

Forbidden:

- Trusting any value from the body that should come from the JWT
  (`org_id`, `user_id`, `cell_id`).
- Issuing JWTs from anywhere except Supabase Auth (no in-app token mint).
- Long-lived JWTs (max `exp` is the Supabase session length; refreshed by
  the client).

---

## Middleware stack (load-bearing order)

Reproduced from [BACKEND_CONTEXT.md](BACKEND_CONTEXT.md) for completeness:

```
SecurityHeadersMiddleware -> CORS -> SlowAPI -> JWTAuth ->
UsageGuard -> BillingCheck -> Idempotency -> Route
```

If you add a layer:

1. Decide where it sits relative to JWT (before = unauthenticated; after
   = trusts `request.state.user`).
2. Decide where it sits relative to billing (before = bypasses cap; after
   = enforces cap).
3. Add an ADR if header semantics change.

---

## Row-level security (RLS)

The standard policy (every multi-tenant table):

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;

CREATE POLICY <t>_org_isolation ON <t>
  USING (org_id = current_setting('request.jwt.claims', true)::jsonb ->> 'org_id'::text)
  WITH CHECK (org_id = current_setting('request.jwt.claims', true)::jsonb ->> 'org_id'::text);
```

Service-role queries (background jobs that bypass RLS) MUST still
explicitly filter by `org_id`. Reviewers reject queries without it.

The CI gate
[`backend/tests/security/test_tenancy_isolation.py`](../backend/tests/security/test_tenancy_isolation.py)
is the single most important test in the repo. It:

1. Creates two orgs with overlapping data.
2. Sets the JWT context for org A.
3. Queries every multi-tenant table.
4. Asserts zero rows belong to org B.

A new multi-tenant table without an RLS policy = the test fails on the
new table = PR is blocked.

---

## Idempotency

Table:

```sql
CREATE TABLE idempotency_keys (
  key text PRIMARY KEY,
  org_id uuid NOT NULL,
  request_hash text NOT NULL,
  status_code int NOT NULL,
  response_body jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON idempotency_keys (created_at);  -- TTL sweep
```

Middleware behavior:

- Hash = SHA-256(`route + key + body`).
- Cache hit + same hash → return cached response, status `2xx`.
- Cache hit + different hash → 409 `idempotency.conflict`.
- Cache miss → run handler; on `2xx`, persist; on error, do not persist
  (so client can retry).

Sweeper: scheduler process deletes rows older than 24h.

---

## Rate limiting

slowapi with a Redis backend. In `backend/main.py`:

```python
from slowapi import Limiter
limiter = Limiter(key_func=lambda req: req.state.user.org_id, storage_uri=REDIS_URL)
```

Per-route decorators (246 across 46/48 route files):

```python
@router.post("/")
@limiter.limit("60/minute")
async def create_application(...):
    ...
```

Why per-org rather than per-IP: prevents one org's runaway client from
DOS'ing tenants behind a shared NAT. Per-IP is layered by the platform
(Netlify edge / Railway).

Tests assert `RateLimitExceeded` returns 429 with `Retry-After`.

---

## SSRF defense (`safe_fetch` — P0-2 SHIPPED)

Any tool that fetches a URL goes through
`ai_engine/tools/fetch.py:safe_fetch(url, *, org_id, max_bytes=...)`:

1. Resolve the URL's hostname to IPs (all of them).
2. Reject if any IP is in:
   - private (10/8, 172.16/12, 192.168/16),
   - loopback (127/8, ::1),
   - link-local (169.254/16, fe80::/10),
   - multicast / reserved.
3. Pin the connection to the resolved IP (TLS SNI to the original host)
   so DNS rebinding cannot swap the IP after the check.
4. Disallow following redirects to private addresses (re-validate every
   hop).
5. Allowlist schemes: `http`, `https` only.
6. Per-org bandwidth budget (counter table); cap per request via
   `max_bytes`.

Direct `requests.get(...)` / `httpx.get(...)` calls in `ai_engine/` to a
URL from user input are forbidden and grep-checked in CI.

---

## Prompt injection defenses (5 layers)

Per blueprint §6.5. The orchestrator owns these — agents are dumb.

1. **Detect.** `prompt_injection_detector` runs over user-supplied text
   (resume, JD, message). Flags suspicious patterns ("ignore previous
   instructions", role swaps). Logs but does not block by default.
2. **Sanitize.** Strip / neutralize zero-width chars, BIDI controls,
   homoglyphs.
3. **Wrap.** All user input is concatenated via `wrap_user_input(text)`
   which delimits with deterministic markers and instructs the model to
   treat the contents as data. Never raw-concat user text into a system
   prompt.
4. **Limit privilege.** Even if the model is fooled, the action gate
   below prevents tool calls without a capability token.
5. **Post-output guard.** A separate critic examines the model output for
   exfiltration attempts (URLs to unknown hosts, base64 blobs, etc.)
   before persisting / streaming.

---

## Action gate, tool registry, capability tokens (P0-5 SHIPPED)

The fundamental rule: **the LLM never invokes a tool. Ever.** The model
emits a structured request; the orchestrator validates and dispatches.

```
LLM output (structured)
     |
     v
Action gate
  - allowed-tools allowlist (per chain / per phase)
  - jsonschema validation of args
  - capability token check
     |
     v
Tool registry (`ai_engine/registry/`)
  - resolves name -> implementation
  - sandbox tier dispatch
     |
     v
Tool implementation
  - emits ai_tool_invocations row (audit)
```

`CapabilityToken` shape:

```python
class CapabilityToken(BaseModel):
    org_id: UUID
    user_id: UUID
    grant_id: UUID                    # references a grant row
    expires_at: datetime              # short TTL (minutes)
    nonce: str                        # one-time use
    signature: str                    # HMAC-SHA256(secret, payload)
```

The orchestrator signs tokens at run start; tools verify before executing.
Replay protection via `nonce` (single-use cache in Redis with TTL).

---

## Sandbox tiers (L0–L3)

| Tier | Allows | Examples |
|---|---|---|
| **L0** | pure compute, no I/O | text manipulation, regex, scoring functions |
| **L1** | read-only HTTP via `safe_fetch` only | company_lookup, RSS read |
| **L2** | sidecar process boundary; no DB write; can read own org's data | RAG retrieval, computation that touches storage |
| **L3** | write to user data (DB, document_library) | resume rewrite, evidence ledger update |

Each `ai_tools` row has a `sandbox_tier` column. The dispatcher routes to
the matching runtime. L2 calls a separate `tool-runner` process (Stage B);
today L0/L1/L2 share the worker process and L3 is gated by capability
token.

Adding a tool without a `sandbox_tier` is forbidden.

---

## Secrets

- Never committed. `.env*` files in `.gitignore`.
- GitHub secret scanning enabled at the org.
- `gitleaks` pre-commit hook (planned; not yet in `pyproject.toml`).
- Production secrets live in Railway / Netlify env stores; rotation policy
  documented in `SECURITY.md`.
- Supabase service role key is reserved for the backend; never exposed
  to the frontend.

---

## Logging, redaction, error reporting

- structlog JSON to stdout; collected by Railway and shipped to Sentry +
  Grafana.
- Sentry `before_send` redacts depth = 16 (TD-2 SHIPPED). Scrubs:
  - email, phone, postal address;
  - resume body, JD body;
  - JWT, capability token signature;
  - Stripe customer / payment IDs.
- Errors include `correlation_id` (from middleware) so logs and traces
  join up.

---

## Vulnerability + dependency posture

- `pyjwt >= 2.12` (CVE-2026-32597 — algorithm confusion).
- `pytest >= 9.0.3` (CVE-2025-71176 — symlink TOCTOU during temp dir
  setup).
- Dependency audit gate (m12-pr04 SHIPPED): GitHub `pip-audit` /
  `npm audit` are CI-required, not informational.
- TD-4 open: `requirements.txt` ranges (`>=`) need a lockfile (`pip-tools`
  / `uv pip compile`) to make builds reproducible.

---

## "Must never happen" scenarios (blueprint §21) — security subset

| # | Scenario | Defense | Test anchor |
|---|---|---|---|
| 1 | Cross-org data leak via missing RLS | RLS policy template + isolation test | `tests/security/test_tenancy_isolation.py` |
| 2 | Prompt-injection-driven tool call to write another org's data | Action gate + capability token + L3 gating | `tests/ai/test_action_gate.py` (planned) |
| 3 | SSRF to internal metadata endpoint | `safe_fetch` IP pinning | `tests/security/test_safe_fetch.py` |
| 4 | JWT forge via algorithm confusion | `pyjwt 2.12+`, explicit `algorithms=[...]` | `tests/security/test_jwt_alg.py` |
| 5 | Cost runaway during outage | `usage_guard` per-org daily $ cap (P0-4) | `tests/billing/test_org_daily_cost_cap.py` (m12-pr08) |

---

## What "good security" looks like in this repo

- [ ] New table has RLS in the same migration; isolation test passes.
- [ ] New route uses `Depends(get_current_user)` and (where relevant)
      `Depends(require_scope("..."))`.
- [ ] New route has `@limiter.limit(...)`.
- [ ] New tool has a `sandbox_tier` and a JSON schema; capability token
      enforced by registry.
- [ ] New external HTTP fetch uses `safe_fetch`.
- [ ] New user-supplied text is wrapped via `wrap_user_input(...)` before
      reaching any prompt template.
- [ ] No new dependency without verifying CVE feed.
- [ ] No new secret in repo (gitleaks would catch; reviewer checks).
