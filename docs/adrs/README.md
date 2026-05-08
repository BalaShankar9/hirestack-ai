# Architecture Decision Records

Canonical index of architectural decisions. Every Accepted ADR here is binding.

- **Template:** [`../architecture/ADR_TEMPLATE.md`](../architecture/ADR_TEMPLATE.md)
- **When required:** See [Engineering Guardrails §G3](../architecture/ENGINEERING_GUARDRAILS.md).
- **Numbering:** sequential, four digits, no gaps. Reserve a number when starting a draft.
- **Lifecycle:** Proposed → Accepted → (Deprecated | Superseded by ADR-NNNN). Never edit an Accepted ADR; supersede it.

## Index

### Foundations (0001–0019, complete)

| # | Title | Status |
|---|---|---|
| 0001 | Circuit breakers for Supabase + Stripe | Accepted |
| 0002 | Cache module extraction | Accepted |
| 0003 | Health vs readiness probes | Accepted |
| 0004 | Single migration source of truth | Accepted (drift open — see P1-5) |
| 0005 | Pipeline execution path audit tag | Accepted |
| 0006 | SSE protocol contract | Accepted |
| 0007 | Chain output and construction contract | Accepted |
| 0008 | Validation, critic, and model-router contract | Accepted |
| 0009 | Domain services contract surface | Accepted |
| 0010 | Frontend web contract surface | Accepted |
| 0011 | Mobile (Android) contract surface | Accepted |
| 0012 | Infra deploy contract surface | Accepted |
| 0013 | Observability + SRE contract surface | Accepted |
| 0014 | QA + release engineering contract surface | Accepted |
| 0015 | Planner risk-mode and strategy memory | Accepted |
| 0016 | Variant-lab winner pick | Accepted |
| 0020 | Workflow engine selection (Temporal) | Accepted |

### Open / required before next material change (0030–0040)

These are reserved numbers. The corresponding implementation PR cannot merge until the ADR is Accepted.

| # | Title | Status | Blocks PR |
|---|---|---|---|
| 0030 | Cell protocol skeleton (`cell_id` JWT claim + router) | Proposed | Stage-B trigger |
| 0031 | Multi-provider AI dispatch (P1-4) | Accepted 2026-05-08 | `m7-pr28` |
| 0032 | Capability tokens for tools (P0-5) | Accepted 2026-05-08 | `m7-pr29` |
| 0033 | Tool sandbox tier classifier (L0/L1/L2) | Accepted 2026-05-08 | `m7-pr29` |
| 0034 | `ai_invocations` flight recorder schema | Accepted 2026-05-08 | `m7-pr30` |
| 0035 | Strict event validation at OutboxWriter (P1-2) | Proposed | `m7-pr31` |
| 0036 | Per-stage Temporal activities (P1-1) | Proposed | `m8-pr32` |
| 0037 | Partition rotation strategy — `pg_cron` + native function for `events_outbox` (P0-1; pg_partman deferred to Stage B) | Accepted 2026-05-08 | `m7-pr27a` ✅ |
| 0038 | Eliminate in-process job fallback (P0-2) | Accepted 2026-05-08 | `m7-pr27b` ✅ |
| 0039 | Forbid native `EventSource`; mandate `@microsoft/fetch-event-source` (P0-7) | Proposed | `m7-pr27` |
| 0040 | ACK-on-success queue semantics + DLQ (P0-3) | Accepted 2026-05-08 | m7-pr27c ✅ |
| 0041 | Bootstrap task registry for generation dispatch (P0-4) | Accepted 2026-05-08 | m7-pr27d ✅ |

## Authoring rules

1. Copy `../architecture/ADR_TEMPLATE.md` into a new file `NNNN-short-slug.md`.
2. Status starts as **Proposed**.
3. Open the implementation PR draft alongside.
4. Architecture-WG review required to flip Proposed → Accepted.
5. Once Accepted, link the blueprint section it amends; if no section exists yet, add one.
6. Deprecation: never delete; mark Deprecated and add the superseding ADR number.
