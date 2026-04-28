# Runbook: Circuit-breaker recovery

Applies to the in-process breakers in `app.core.circuit_breaker`:
`supabase` (10 failures / 30 s) and `stripe` (5 failures / 30 s).

## Symptom

Alert / dashboard shows `hirestack_circuit_breaker_state{name="…"} == 2`
(open). User-visible: 503s on auth/data routes (Supabase) or
"billing temporarily unavailable" UX (Stripe).

## 1. Confirm scope

```bash
curl -s "$BACKEND_URL/health" | jq '.circuit_breakers'
```

Look for `state: "open"` entries and the `failure_count`. Cross-check
upstream status pages:

- Supabase: <https://status.supabase.com/>
- Stripe: <https://status.stripe.com/>

If the upstream is down, **do not intervene** — the breaker is
working as designed. Wait for the upstream to recover; the breaker
will half-open after 30 s and close on the first success.

## 2. If the upstream is healthy but the breaker is still open

Most common causes:

1. **Stale credential** — rotated `SUPABASE_KEY` / `STRIPE_SECRET_KEY`
   that the running process still has the old value for. Action:
   redeploy after confirming the env var is updated.
2. **Network egress problem** — pod cannot reach the upstream even
   though the upstream is up. Action: from the pod, run
   `curl -sv $SUPABASE_URL/auth/v1/health` (or the Stripe analog).
   Fix DNS / firewall / NAT as appropriate.
3. **Local clock skew** — JWT validation against Supabase fails with
   "token used before issued". Action: `timedatectl status` or
   confirm NTP sync.

## 3. Manual reset (last resort)

If the breaker is stuck open after upstream recovery (very rare —
the half-open probe should close it within 30 s):

```python
# In a maintenance shell on one pod:
from app.core.circuit_breaker import reset_all_breakers
reset_all_breakers()
```

Or restart the pod. Both are equivalent — breakers are in-process
state, not shared.

## 4. Post-incident

- Record the incident in the on-call journal with timestamps.
- If the breaker tripped on a healthy upstream (false positive),
  open a ticket to investigate the failure-classification logic in
  `SupabaseDB._run` (we only count transient errors — see
  ADR-0001).
- If breakers tripped repeatedly during a known-flaky upstream
  window, consider raising `failure_threshold` for that breaker.
