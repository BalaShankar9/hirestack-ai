# Scaling Phases

**Status:** Canonical
**Companion to:** [`WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`](./WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md) §22

> The point of this document is to **prevent premature optimization**.
> Each phase has explicit triggers. Do **not** start phase N+1 work until the trigger is met.
> Do **not** skip phase N hardening because phase N+1 looks shinier.

---

## Stage A — Today → 10× (target ~50K generations/day)

### Triggers to begin
You are here. Start: today.

### Triggers to **exit** (declare Stage A complete)
- All P0 fixes (P0-1..P0-7) closed (blueprint §18).
- All P1 fixes targeted for Stage A closed (P1-1..P1-9, P1-11, P1-12, P1-14).
- DR drill executed and passed within last 90 days.
- 9 baseline test failures triaged (fixed or `xfail` with linked issue).
- Cost-per-generation dashboard live and reviewed weekly.
- SLO instrumentation live for all four golden SLOs.

### What changes during Stage A

| Area | Action | Tracking |
|---|---|---|
| Reliability | Eliminate in-process fallback; ACK on success only; partition rotation | P0-1..P0-3 |
| Cost | Per-org cap; cascade-failure breaker; cost attribution table | P0-4, P1-8 |
| AI runtime | Capability tokens; sandbox tiers; second LLM provider | P0-5, P1-4 |
| Idempotency | Middleware ON in production | P0-6 |
| Realtime | SSE `Last-Event-ID` end-to-end | P0-7 |
| Workflow | Per-stage Temporal activities (PR-24 phase 2) | P1-1 |
| Eventing | Strict validation at OutboxWriter; ~25 missing event types added | P1-2, P1-3 |
| Repo health | Single migration root; single `main.py`; codegen for events | P1-5..P1-7 |
| Process | `import-linter` enforced; coverage gate; staging mirror | P1-10, P1-14, P1-15 |
| Observability | Migrate `/metrics` to `prometheus_client` | TD-3 |

### What we **explicitly do NOT do** in Stage A
- Do **not** shard Postgres.
- Do **not** introduce Kafka.
- Do **not** extract microservices (api-gateway, identity-svc, billing-svc remain in monolith).
- Do **not** migrate off pgvector.
- Do **not** add a second region.
- Do **not** build a control-plane / data-plane split.
- Do **not** build customer-facing webhook delivery (lives in Stage B).
- Do **not** build customer-facing eval product (we build it for ourselves only).

### Cost / capacity assumptions
- Single Supabase Postgres instance handles 50K generations/day comfortably with read replicas at end of stage.
- Single Upstash Redis handles 10K rps cache + queue ops.
- Temporal Cloud at "Starter" or low-tier "Production".
- Gemini quotas as primary; Anthropic as redundancy + ~30% of traffic for diversity.

---

## Stage B — 10× → 100× (target ~5M generations/day)

### Triggers to begin
- Sustained > 30K generations/day for 4 consecutive weeks, OR
- > $5M ARR with named enterprise customers requesting:
  - Dedicated tenancy
  - EU data residency
  - SSO/SCIM
  - Audit log export
- Postgres p95 query latency > SLO budget for 2 consecutive weeks.

### Triggers to **exit**
- ≥ 2 cells in active production.
- First enterprise customer on dedicated cell.
- EU cell live with at least one EU customer.
- Realtime gateway extracted; SSE survives rolling deploys.
- Kafka in production for analytics + customer webhooks.
- SOC 2 Type II evidence collection underway.
- WorkOS SSO/SCIM live for enterprise tier.

### What changes during Stage B

| Area | Action |
|---|---|
| Topology | Cell architecture activated: ≥ 2 cells; cell-router DB; JWT `cell_id` claim |
| DB | Migrate to Aurora PostgreSQL per cell; pgBouncer at cell edge |
| Realtime | Extract `realtime-gateway-svc`; web pods publish to Redis pub/sub |
| Eventing | Add Kafka (Confluent or MSK) as durable parallel bus |
| Service extraction | `event-relay-svc` (already separate worker), `tool-runner` sidecar, `realtime-gateway-svc`, then `identity-svc`, `billing-svc` |
| Knowledge | Extract `knowledge-svc` if vector workload distinct |
| Auth | WorkOS SSO/SCIM at enterprise tier |
| Compliance | SOC 2 Type I done; Type II evidence rolling |
| Audit | `audit_log` table; admin actions write to it; retained 7 years |
| Webhooks | Customer-facing webhook dispatcher (signed, retried) |
| OPS | On-call rotation formalized; status page live |

### What we explicitly do NOT do in Stage B
- Do **not** go multi-region active-active until Stage C.
- Do **not** migrate off pgvector unless cost > Turbopuffer breakeven.
- Do **not** build customer-facing eval / observability product unless it is paid.
- Do **not** open-source the AI runtime — competitive moat.

### Cost / capacity assumptions
- Each cell: ~1M generations/day capacity.
- Aurora cluster per cell, multi-AZ.
- Temporal Cloud Production tier per namespace.
- Three LLM providers active (Gemini + Anthropic + OpenAI).
- Per-customer cost margin ≥ 70% (gross).

---

## Stage C — 100× → 1000× (hyperscale, multi-region)

### Triggers to begin
- ≥ $50M ARR.
- ≥ 3 enterprise customers paying for multi-region.
- Sustained > 1M generations/day for 4 consecutive weeks.
- Latency SLO violations driven by cross-region distance.

### Triggers to **exit**
- N/A — this is the steady-state hyperscale stage.
- Re-evaluate every 4 quarters whether infrastructure choices remain optimal.

### What changes during Stage C

| Area | Action |
|---|---|
| Topology | Active-active cells per region (US-East, US-West, EU-West minimum) |
| Vector store | Migrate off pgvector → Turbopuffer or Qdrant cluster |
| Cold storage | Iceberg on S3 for events older than 90 days |
| Observability | Per-region observability sharding |
| Connection pooling | pgBouncer per cell tuned for connection-storm scenarios |
| LLM | On-prem fallback option for highest-tier enterprise (regulated industries) |
| Internal | Self-hosted Temporal evaluation if Temporal Cloud cost > 50% of infra |
| Mobile | Kotlin Multiplatform shared client (iOS + Android) |

### What we explicitly do NOT do even in Stage C
- Do **not** rewrite the monolith into microservices for the sake of it. Extract only what scaling demands.
- Do **not** go multi-cloud unless a customer pays the premium.
- Do **not** build a "platform" product (PaaS) — stay focused on career intelligence.

---

## Anti-overengineering checklist (apply at every stage)

Before adding any new infrastructure component, the proposer must answer:

1. **What concrete signal triggered this?** (Specific metric, customer ask, SLO breach.)
2. **What is the simplest change that addresses the signal?**
3. **What does this commit us to operationally for the next 3 years?**
4. **Have we exhausted optimization of existing components first?**
5. **What's the rollback plan if it doesn't work?**
6. **What does this delete from the architecture?** (Net zero or net negative components is the goal — don't accumulate.)

If any answer is "I don't know" or "we'll figure it out": **the change waits.**

---

## Decision: when to skip a stage

Skipping is rare and dangerous. Reasons that justify skipping ahead:

- A regulator requirement (e.g., must be in EU within 6 months).
- A signed enterprise contract that requires a phase-N+1 capability.
- A demonstrated, measurable production failure that cannot be fixed in the current stage.

Reasons that do **not** justify skipping ahead:

- "It feels behind."
- "Competitors do it."
- "An engineer wants to learn Kafka."
- "VC asked about it."
- "The architect saw a great conference talk."

Architecture-WG approves any stage skip. Document the skip reason in an ADR.
