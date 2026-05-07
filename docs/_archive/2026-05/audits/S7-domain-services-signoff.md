# S7 Domain Services — Sign-off

**Squad:** S7
**Charter:** Lock the public contracts of the 5 highest-risk
domain services in `backend/app/services/`.
**Date opened:** 2026-04-21 (audit committed `59bd90a`)
**Date closed:** 2026-04-21
**Status:** ✅ COMPLETE

## Risk register — closed

| ID | Service              | Severity | Resolution                                                | Commit    |
|----|----------------------|----------|-----------------------------------------------------------|-----------|
| R1 | export.py            | HIGH     | 42 tests pin Unicode/RTL/oversized strip + format dispatch | 31f0c87  |
| R2 | ats.py               | HIGH     | 16 tests pin extended-column probe + fallback path        | e2810f8  |
| R3 | webhook.py           | HIGH     | 29 tests pin Slack body + retry constants + signature     | 5055955  |
| R4 | social_connector.py  | CRITICAL | 56 tests pin SSRF block list + URL parsing + DNS guard    | 1394c9c  |
| R5 | job_sync.py          | MEDIUM   | 20 tests pin record defaults + ownership + singleton      | 7fb5dd9  |
| R6 | export.py markdown   | MEDIUM   | Closed by R1 (covered in `TestGenerateMarkdown` class)    | 31f0c87  |

## Out of scope (intentional)

- Stripe idempotency surface — deferred to a future Billing
  workstream (idempotency table mirrored in S2-F1+F2).
- ATS ranking quality (golden set) — owned by AI Engine evaluation.
- Per-platform retry/backoff for `social_connector` and `job_sync`
  — deferred to runtime hardening (post-S11 SRE).

## Suite delta

| Stage    | Tests | Latency | Δ tests | Δ latency |
|----------|-------|---------|---------|-----------|
| Pre-S7   | 1552  | 6.47s   | —       | —         |
| Post F1  | 1594  | 7.93s   | +42     | +1.46s    |
| Post F2  | 1623  | 8.49s   | +29     | +0.56s    |
| Post F3  | 1679  | 8.01s   | +56     | -0.48s    |
| Post F4  | 1695  | 8.63s   | +16     | +0.62s    |
| Post F5  | 1715  | 8.12s   | +20     | -0.51s    |
| **Net**  | **+163** | **+1.65s** | | |

Latency budget: 8.12s vs 15s ceiling — comfortable headroom.

## Commits

```
59bd90a  S7-F0: audit domain services
31f0c87  S7-F1: pin export.py contracts (42 tests)
5055955  S7-F2: pin webhook.py contracts (29 tests)
1394c9c  S7-F3: pin social_connector.py SSRF + URL contracts (56 tests)
e2810f8  S7-F4: pin ats.py contracts (16 tests)
7fb5dd9  S7-F5: pin job_sync.py contracts (20 tests)
<this>   S7-F6: ADR-0009 + sign-off
```

## Sign-off

S7 charter satisfied. Five highest-risk domain services have
behavioural locks; ADR-0009 codifies the contract surface;
deferred work has explicit owners (S8, S9, AI Engine evaluation).

Next: **S8 — Frontend Web**.
