# ADR-0001: Wrap Supabase and Stripe in circuit breakers

Status: Accepted — 2026-04-21 (S1-F9)
Owners: Platform Core squad

## Context

Two outbound dependencies dominate request-path failure modes:

1. **Supabase** (Postgres + Auth + Storage). Used by every authenticated
   request. Outages historically manifest as 5–60 s timeouts that
   cascade into worker exhaustion and 502 storms at the edge.
2. **Stripe** (Checkout / Customer Portal). Used in the billing flow.
   Stripe API issues block users from upgrading or managing
   subscriptions, but do not block the rest of the app.

Without a breaker, every request keeps issuing fresh outbound calls
during an upstream incident, holding workers and amplifying load on
the upstream when it tries to recover.

## Decision

Wrap both providers using the existing `app.core.circuit_breaker`
primitive (`CircuitBreaker`, `get_breaker_sync`).

### Supabase

- Breaker name: `supabase`
- `failure_threshold=10`, `recovery_timeout=30 s`
- Wraps `SupabaseDB._run` — the single chokepoint through which all
  `client.table().*` and Auth calls are dispatched.
- Trip condition: only **transient** errors increment the failure
  count (httpx timeouts, connection errors, 5xx responses). Logical
  errors (4xx, validation, RLS rejections) do **not** trip the
  breaker — they are user-input problems, not infrastructure.
- Open behaviour: raise `CircuitBreakerOpen` so callers fail fast
  with HTTP 503; `_check_supabase` reports the breaker state on
  `/health`.

### Stripe

- Breaker name: `stripe`
- `failure_threshold=5`, `recovery_timeout=30 s`
- Wraps `stripe.checkout.Session.create` and
  `stripe.billing_portal.Session.create` in `app/services/billing.py`.
- Open behaviour: log `stripe_breaker_open` with `remaining_s` and
  return `None` so the caller can render a "billing temporarily
  unavailable" UX instead of a 500.

### Tests

- `test_supabase_breaker.py` (3 tests): asserts transient failures
  trip the breaker, that non-transient errors do **not** trip it,
  and that a success resets the failure count.
- An autouse `_reset_breakers` fixture calls `reset_all_breakers()`
  to prevent cross-test contamination.

## Consequences

- During a Supabase incident, fresh requests after 10 transient
  failures fail fast in <1 ms with HTTP 503 instead of holding a
  worker for 30 s. Worker pool stays available; recovery probes run
  every 30 s via the half-open state.
- `/healthz/ready` flips to 503 within the breaker timeout, so an
  orchestrator can shed traffic.
- Billing UI degrades gracefully; the rest of the app is unaffected
  by Stripe outages.

## Alternatives considered

- **Per-call retries only** — chosen as a complement, not a
  replacement. Retries hide brief blips; breakers prevent thundering
  herds during sustained incidents. We use both.
- **Service-mesh breakers (e.g. Envoy)** — deferred. Operating in a
  mostly Railway/Vercel environment without a service mesh means
  in-process breakers are the simplest surface that works today.
