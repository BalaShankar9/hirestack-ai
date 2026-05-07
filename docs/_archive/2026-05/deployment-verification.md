# Production deployment verification

This doc describes the gate between **code-complete** and **verified live**.
It is the contract the production-readiness verdict cites when claiming a
deploy is "green".

## When to run

After ANY deploy to production (Railway backend or Netlify frontend),
run the health-check script to verify the deployed surface actually works.
Do NOT rely on Railway's or Netlify's "deploy succeeded" green tick —
those mean the build artifacts shipped, not that the app responds.

## How

```bash
python scripts/health_check.py \
  --backend  https://<your-railway-domain> \
  --frontend https://<your-netlify-domain>
```

## Exit codes (machine-readable for CI)

| Exit | Meaning | Action |
|------|---------|--------|
| `0` | All checks passed | Deploy is GREEN — verdict can claim "verified live" |
| `1` | At least one **critical** check failed | Deploy is NOT GREEN — roll back or fix immediately |
| `2` | At least one **non-critical** check failed | Deploy is DEGRADED — investigate but no rollback required |

## Checks today

### Critical (a single failure means NOT GREEN)

- `backend.health` — `GET /health` returns 200 with `status` field
- `backend.openapi` — `GET /openapi.json` returns 200 with valid OpenAPI doc
- `frontend.root` — `GET /` returns 200 with HTML body

### Non-critical (failures mean DEGRADED, deploy still up)

- `backend.docs` — `GET /docs` returns 200 with Swagger UI

## Honest scope today

The script intentionally exercises only **unauthenticated, side-effect-free**
endpoints. It is a smoke test, not an end-to-end functional test. Specifically
it does NOT:

- Submit a generation job (would consume AI credits, write DB rows)
- Test any authenticated endpoint (would need a service-role token)
- Verify Supabase migrations are applied (run the SQL audit script for that)
- Verify env vars are set (e.g. `BILLING_ENABLED`, `GEMINI_API_KEY`)

Those checks remain manual today. Documented as known gaps in the
production-readiness verdict.

## Future expansion (not blocking Beta-Ready-for-Pilot)

When a service-role test token exists in the deployment env, add:

- `backend.auth.me` — `GET /api/auth/me` returns 200 with user shape
- `backend.jobs.list` — `GET /api/jobs?limit=1` returns 200
- `backend.billing.status` — `GET /api/billing/status` returns 200 and
  surfaces `plan: "billing_disabled"` when env flag is off
