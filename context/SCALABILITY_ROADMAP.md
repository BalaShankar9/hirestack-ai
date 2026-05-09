---
title: Scalability Roadmap
last_synced: 2026-05-08
watch_paths:
  - infra
  - docs/architecture
  - backend/app/temporal
canonical_sources:
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#3-cells-and-regions
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#20-stage-a-exit-criteria
update_when:
  - a stage transitions (A -> B, B -> C)
  - a scaling trigger fires
  - a new bottleneck is identified
  - the cell topology changes
---

# Scalability Roadmap

> Three stages, each with explicit triggers that move us into the next
> one. We do not invest in Stage B work until a Stage A trigger fires.
> Premature scale work is the cheapest way to slow ourselves down.

---

## TL;DR — 10 lines

1. **Stage A (today):** single cell, single region (`us-east/shard-0`).
   Designed for 1k–10k DAU.
2. **Stage B:** multi-cell within a region; per-tenant cell affinity for
   Enterprise; per-region observability.
3. **Stage C:** multi-region active-active; geo-DNS; per-region eval
   pinning.
4. **The triggers are explicit** — see the table below. Do not ship
   Stage B work until a Stage A trigger fires.
5. **The DB is the gravity well.** Cell sharding is mostly a DB story;
   compute scales horizontally with replicas trivially.
6. **Cell ID is everywhere already** (P1-13 deferred but `cell_id`
   propagates in JWT, spans, and event payloads). Sharding is mostly
   plumbing, not redesign.
7. **Per-cell SLOs** apply once Stage B starts. Until then, global SLOs
   are sufficient.
8. **Cost grows roughly linearly with DAU** because the dominant cost
   is per-generation LLM tokens. Infra is < 10% of total spend at Stage A.
9. **Capacity model:** every component has a documented headroom (CPU,
   memory, conn pool, queue depth). When any component reaches 70% of
   limit, the relevant Stage B work activates.
10. **Cell migration is online** — Enterprise tenants can be moved cell
    -to-cell with zero downtime via a documented runbook (Stage B).

---

## Stage A (today)

**Topology:**

```
Netlify CDN -> Railway us-east project -> Supabase (managed) + Upstash Redis
                                       -> Temporal Cloud (us-east namespace)
```

- 1 API service (2 replicas, scale to 8).
- 1 worker (2 replicas, scale to 8).
- 1 scheduler (1 replica, leader-locked).
- 1 temporal_worker (2 replicas, scale to 8).
- 1 Postgres (Supabase) + 1 read replica (planned).
- 1 Redis cluster (Upstash).
- 1 Temporal namespace.

**Designed for:** 1k–10k DAU; ≤ 200 RPS API peak; ≤ 1k generations/hr.

**SLOs:** see [PERFORMANCE_CONTEXT.md](PERFORMANCE_CONTEXT.md).

---

## Stage B (multi-cell, single region)

**Triggers (any one):**

| Trigger | Threshold |
|---|---|
| DAU sustained | > 10k for 14 days |
| API RPS p95 | > 200 RPS sustained 1h |
| Generation throughput | > 1k/hr sustained |
| Single Enterprise tenant exceeds | 30% of any cell's capacity |
| First Enterprise tenant signed under "dedicated cell" SKU | n/a |
| Per-cell SLO required by contract | n/a |

**Topology change:**

```
                       Netlify (geo-DNS within region)
                                     |
                  +------------------+------------------+
                  |                                    |
        cell us-east/shard-0                 cell us-east/shard-1
        (shared Pro/Team tenants)            (Enterprise dedicated)
                  |                                    |
            Postgres us-east-0                Postgres us-east-1
            Redis    us-east-0                Redis    us-east-1
            Temporal us-east-0 ns             Temporal us-east-1 ns
```

**Code changes already accounted for:**

- `cell_id` claim in JWT (today): the API gateway uses it to route to the
  correct cell. ADR-0030.
- All event payloads carry `cell_id` so per-cell archival is trivial.
- All span attributes carry `cell_id` (P1-13 deferred but enforced in
  contract test).

**New work for Stage B:**

- Per-cell observability dashboards (TD-9).
- Cell migration runbook (Enterprise tenant moves between cells).
- Per-cell cost rollup tables.
- DB shard router (lightweight; reads JWT.cell_id; routes connection
  pool).
- Per-cell rate-limit storage (slowapi already keyed per-org; per-cell
  Redis is automatic since each cell has its own Redis).

**Estimated work:** 6–10 PRs over a sprint. Most of the design is
already done; what remains is plumbing and per-cell dashboards.

---

## Stage C (multi-region active-active)

**Triggers (any one):**

| Trigger | Threshold |
|---|---|
| EU customer base | > 1k DAU sustained from EU |
| GDPR / data residency contractual requirement | n/a |
| Per-region p95 latency penalty | > 200ms over baseline for 14 days |

**Topology:**

```
                       geo-DNS (Netlify + Route 53)
                              /              \
                  region us-east             region eu-west
                /        |        \            /        |        \
            cell-0    cell-1   cell-2     cell-0    cell-1   cell-2
              |         |         |          |         |         |
            Postgres / Redis / Temporal   Postgres / Redis / Temporal
              \________________________________________________/
                       cross-region read replicas (lagged)
                       cross-region archival (S3 multi-region)
```

**New work for Stage C:**

- Per-region eval pinning (run evals in-region for latency).
- Cross-region read replicas for analytics.
- Active-active write conflict policy (last-writer-wins per row; per-org
  pinned to one region for write authority).
- DSR (data residency) per-org region pinning at signup.
- Per-region SLO + error budget.

**Cost considerations:**

- Multi-region adds ~ 30% infra cost.
- Cross-region egress is not free; minimize chatty cross-region calls
  (per-org pinning solves most).

---

## Capacity model (per component)

| Component | Today's headroom | Yellow at | Red at | Stage B trigger? |
|---|---|---|---|---|
| API CPU | 30% avg, 60% p95 | 70% sustained 1h | 85% sustained 15m | yes (>200 RPS) |
| API memory | 40% | 70% | 85% | indirect |
| Worker queue depth | < 50 | 200 | 500 | yes (queue > 200 sustained) |
| Temporal task queue lag | < 5s | 30s | 2m | yes |
| Postgres connections | 30% of pool | 70% | 90% | yes |
| Postgres disk | 20% | 70% | 85% | tier upgrade or shard |
| Redis memory | 20% | 70% | 85% | tier upgrade or shard |
| Redis ops/s | 30% of plan | 70% | 85% | tier upgrade |
| LLM token throughput | <30% of provider quota | 70% | 85% | quota increase or downshift |
| Cost burn rate | < 50% daily cap on any org | 80% | 100% | per-org hard limit |

Yellow → planning. Red → action.

---

## What scales today (and what doesn't)

**Scales horizontally:**

- API replicas (stateless after JWT decode).
- Worker replicas (consumer-group; Redis Streams handles distribution).
- Temporal worker replicas (Temporal handles task distribution).

**Scales by tier upgrade only (today):**

- Postgres (Supabase plan).
- Redis (Upstash plan).
- Temporal (Cloud plan).

**Does not scale until Stage B:**

- Per-org concurrency cap when one tenant goes hot (cell-isolation
  needed; sharing the pool means hot tenant pressures others).
- Eval workload (single-cell). Evals will grow with chain count;
  Stage B per-cell eval pool.

---

## Cell migration (Stage B runbook outline)

When an Enterprise tenant moves from cell-0 to cell-1:

1. Set tenant `org.cell_id` to cell-1 in `orgs` table (transactional).
2. Future requests route to cell-1.
3. Run `MigrateOrgWorkflow` (Temporal): copy tables WHERE org_id = X
   from cell-0 DB to cell-1 DB; verify checksums; flip read traffic.
4. Drain in-flight cell-0 jobs for the org (wait for queue depth = 0
   for org).
5. Delete from cell-0 (after 7-day grace).

Zero downtime to the user; the user's UI sees a brief queueing of new
generations during the cutover (≤ 30s).

---

## What "good scalability work" looks like in this repo

- [ ] A trigger fired (or is imminent in the next 30 days) — not
      speculative.
- [ ] Capacity dashboard cited in the PR (which metric, what threshold).
- [ ] No new architectural primitive without an ADR.
- [ ] No multi-region story landed before Stage B is closed.
- [ ] Per-cell-id propagation is preserved end-to-end.
- [ ] Backwards compatible: existing tenants see no behavior change.

---

## Anti-patterns we will not adopt without evidence

- **Sharding by user_id within an org.** RLS is org-scoped; user-scope
  sharding adds complexity for no gain.
- **Microservice extraction "for scale".** AO-1 (KNOWN_ISSUES). Modular
  monolith scales fine through Stage B.
- **Eventually-consistent read models for live UI.** Outbox + projection
  is enough.
- **Active-active across cells in the same region.** Cells are isolation
  units, not active-active replicas.
