---
title: Known Issues & Risk Matrix
last_synced: 2026-05-08
watch_paths:
  - backend/tests
  - ai_engine/tests
  - .github/workflows
canonical_sources:
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#21-must-never-happen
  - /memories/repo
update_when:
  - a new issue is discovered (W item) or a known one ships a fix
  - a risk's likelihood or impact changes
  - an anti-overengineering rule is broken (refresh evidence)
---

# Known Issues & Risk Matrix

> The list of "we know about this; here is the plan." If you encounter
> something not in this file, file it here in the same PR that fixes
> it. Surprises are debt.

---

## TL;DR — 10 lines

1. **W items** are known watch-list issues, not all bugs. Each has a
   plan. Today: W1–W15, mostly Stage B prep.
2. **Risk matrix top 5** (by likelihood × impact): Gemini outage,
   per-org cost runaway, in-process OOM (gated by ff), queue ACK loss,
   partition expiry.
3. **Mitigations are layered** — every top risk has at least two
   independent defenses.
4. **Anti-overengineering rules** are explicit. Breaking one without
   evidence is rejected in review.
5. **9 baseline test failures** (P1-11) were triaged and shipped during
   m12-pr05; this list is the current "next 9" if any.
6. **No Sev-1 outages in last 28 days.** No Sev-2 in last 14 days.
7. **Open Linear tickets** linked per W item where relevant.
8. **Each W item has a "trigger to escalate"** so you know when to make
   it a P1.
9. **The /context system itself is W14:** drift detection is advisory
   today (m12-pr13); promote to required when noise is acceptable.
10. **No silent issues.** "I noticed but didn't open a ticket" is not
    allowed.

---

## W items (open watch list)

### W1 — Gemini outage cascading retries

**Symptom:** when Gemini returns 5xx for sustained periods, retries pile
up before the breaker opens, briefly worsening the outage.

**Defense in place:** circuit breaker (5 failures / 60s). Anthropic
fallback when CB open (P1-4). 6/120s retry budget bounds blast radius.

**Plan:** add an upstream half-open canary so the breaker re-opens fast
on a flap. Tracked as a future PR; not a blocker.

**Trigger to escalate:** if a real outage burns > 10% of weekly error
budget.

---

### W2 — Per-org cost runaway during a misuse spike

**Symptom:** an org running scripted requests can burn through the daily
$ cap fast.

**Defense in place:** P0-4 cost cap; usage_guard pre-flights every call
with × 1.10 projection.

**Plan:** add per-minute spike detection (on top of daily cap) — burn
rate alarm at > 25% of daily cap in any 1m window.

**Trigger to escalate:** any org hits 100% of daily cap in < 10 min.

---

### W3 — In-process fallback OOM under sustained load

**Symptom:** with `ff_inprocess_fallback=true` (NEVER in prod), large
generations can OOM the API process.

**Defense in place:** flag is OFF in prod; CI asserts production config
has it OFF. ADR-0038.

**Plan:** harden the fallback path with a max-concurrency semaphore so
that even when accidentally on, blast is bounded.

**Trigger to escalate:** any prod env shows the flag ON in a deploy
manifest review.

---

### W4 — Redis Streams ACK loss under disconnect

**Symptom:** consumer crashes between `XREADGROUP` and `XACK` can leave a
message pending past the visibility timeout.

**Defense in place:** XPEL claim by another consumer after timeout; ACK
on success only (m7-pr27c).

**Plan:** add a `tests/queue/test_dlq.py` that includes the disconnect
scenario explicitly. Currently covered transitively.

**Trigger to escalate:** any prod backlog growth not explained by demand.

---

### W5 — Partition expiry without rotation

**Symptom:** if `pg_cron` partition rotation fails silently, writes to
`ai_invocations` could fail when no partition exists for the new month.

**Defense in place:** `PartitionRotationWorkflow` (Temporal) creates
partitions 90 days ahead; alert at < 30 days runway.

**Plan:** `tests/db/test_partition_health.py` to assert runway >= 30
days; runbook `partition-rotation-failed.md`.

**Trigger to escalate:** any partition runway alert.

---

### W6 — DLQ growth without operator awareness

**Symptom:** DLQ depth grows but the operator doesn't notice until SLO
burn.

**Defense in place:** DLQ depth alert at any non-zero growth in 1h.

**Plan:** weekly DLQ inspector report email to ops channel.

**Trigger to escalate:** DLQ depth > 100 in any 1h window.

---

### W7 — Eval baseline drift over time

**Symptom:** model upgrades from providers can shift baselines; eval
regression alarms become noisy.

**Defense in place:** baselines re-checked monthly; PR author can update
baseline with reviewer sign-off.

**Plan:** auto-flag PRs that update > 3 baselines as "model drift" —
require ADR.

**Trigger to escalate:** > 5 baselines updated in a single PR.

---

### W8 — Prompt cache stampede on fresh deploys

**Symptom:** after a deploy, both LRU tiers are cold; sudden burst of
identical prompts can bypass the LRU and hit Redis only.

**Defense in place:** Redis tier handles the warm-up.

**Plan:** prewarm critical prompt templates at process boot (deterministic
system prompts). Small effort.

**Trigger to escalate:** post-deploy p95 spike > 30%.

---

### W9 — TipTap autosave flooding the API

**Symptom:** rapid edits in TipTap can fire many autosave PUTs.

**Defense in place:** debounced (2s); per-route rate limit.

**Plan:** server-side dedupe on `(doc_id, version)`.

**Trigger to escalate:** any user reports duplicate-version errors.

---

### W10 — SSE buffer overflow on slow client

**Symptom:** a client with poor connectivity can fill server's send
buffer.

**Defense in place:** bounded per-connection buffer; drop oldest with
`stage.token_dropped` event.

**Plan:** none (current behavior is acceptable).

**Trigger to escalate:** > 1% of connections see drops.

---

### W11 — Stripe webhook duplicate delivery

**Symptom:** Stripe occasionally retries webhooks; duplicate event
processing must be idempotent.

**Defense in place:** webhook handler dedupes on `event.id`.

**Plan:** none.

**Trigger to escalate:** duplicate billing rows.

---

### W12 — Ad-hoc admin scripts without audit log

**Symptom:** scripts under `scripts/` can mutate prod data without an
audit trail.

**Defense in place:** policy: all prod-mutating scripts must write an
`audit_logs` row; reviewed at PR time.

**Plan:** scaffold `scripts/_admin_template.py` enforcing the audit
write.

**Trigger to escalate:** any prod-mutating script merged without audit.

---

### W13 — Frontend dynamic import drift

**Symptom:** as new heavy components land, bundle budget can creep up.

**Defense in place:** Lighthouse CI; bundle analyzer on PR.

**Plan:** weekly bundle-size delta report.

**Trigger to escalate:** initial JS gz > 250kB.

---

### W14 — `/context` drift over time

**Symptom:** the system documents this repo; if the docs drift, agents
get bad context.

**Defense in place:** `scripts/governance/check_context_freshness.py`
(advisory today; m12-pr13). Front-matter `watch_paths` enables targeted
detection.

**Plan:** promote to required gate once noise is acceptable. Until then
runs informationally on every PR.

**Trigger to escalate:** advisory > 30% noise rate after a month.

---

### W15 — Mobile sideload signature drift

**Symptom:** Android sideload `.apk` signing key managed manually;
rotation has no automation.

**Defense in place:** documented in `mobile/SIDELOAD.md`.

**Plan:** Stage B; not a Stage A blocker.

**Trigger to escalate:** any mobile beta tester reports signature
mismatch.

---

## Risk matrix (likelihood × impact)

| # | Risk | Likelihood | Impact | Defenses |
|---|---|---|---|---|
| 1 | Gemini outage > 30 min | Medium | High | CB + Anthropic fallback (P1-4); cost cap; SSE degraded UI |
| 2 | Cost runaway in one org | Medium | High | usage_guard cap (P0-4); spike alarm (W2); rate limit |
| 3 | In-process fallback OOM | Low | High | flag OFF in prod (P1-7); ADR-0038; CI assertion |
| 4 | Queue ACK loss / dup processing | Low | Medium | ACK-on-success (m7-pr27c); idempotency_keys (P0-3); XPEL claim |
| 5 | Partition expiry stall | Low | High | Temporal rotation 90d ahead; alert 30d runway |
| 6 | RLS regression in a new table | Low | Critical | tenancy isolation auto-discovered; nightly test |
| 7 | SSRF via redirect chain | Low | Critical | safe_fetch re-validates each hop |
| 8 | Prompt-injection-driven tool call | Low | Critical | action gate + capability token + sandbox tier |
| 9 | Provider key leak | Low | Critical | secret scan; gitleaks; redaction depth = 16 |
| 10 | Eval baseline drift / silent quality drop | Medium | Medium | nightly sweep; PR-touched chains gate |

---

## Anti-overengineering rules

These are **load-bearing decisions** — break one only with evidence.

| # | Rule | Why |
|---|---|---|
| AO-1 | No microservice split until cell-shard demands it (Stage B) | modular monolith ships faster |
| AO-2 | No event sourcing for read models | outbox + projection is enough |
| AO-3 | No GraphQL gateway | typed REST + OpenAPI codegen wins for our team size |
| AO-4 | No custom queue — use Redis Streams + Temporal | well-understood semantics |
| AO-5 | No K8s — Railway dynos | infra is boring; brain is interesting |
| AO-6 | No vector DB — pgvector is enough at our scale | one less moving part |
| AO-7 | No multi-cloud abstraction layer | YAGNI; we'd lose more in friction than we'd gain in option value |
| AO-8 | No "framework" inside `ai_engine` | direct functions + thin classes; resist meta-architecture |
| AO-9 | No speculative caching | measure first, cache second |
| AO-10 | No "smart" middleware that does several things | composable, ordered, testable |

When you propose breaking one, the PR description must:

1. Quote the rule.
2. Cite the metric / scenario forcing the break.
3. Estimate the cost of the new abstraction (LOC, on-call surface).

---

## Closed Sev incidents (last 90 days)

None. Last Sev-2 was m9 era (resolved m9-pr34/35 — SSE resume).

---

## What "good issue tracking" looks like in this repo

- [ ] Discovered an issue → opened a W entry in this file in the same
      PR that touched the area.
- [ ] Issue has a defense-in-place + a plan + a trigger.
- [ ] No "we'll get to it eventually" — it's W or it's not tracked.
- [ ] Sev incidents auto-create a W entry; closing the incident closes
      the W entry only when defenses are upgraded.
