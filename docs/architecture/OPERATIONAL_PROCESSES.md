# Operational Processes

**Status:** Canonical · Enforced
**Companion to:** [`WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`](./WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md)

Operational processes are the **predictable** rituals that prevent the elite team from being overrun by ad-hoc work. Each process below lists trigger, steps, owner, output artifact, and SLA.

> Designed for a small team. Each process is one page or less. If a process needs more than that, it has too many moving parts.

---

## 1 · Architecture Review (per PR with Architecture Impact)

| Field | Value |
|---|---|
| Trigger | PR has the Architecture Impact checklist with at least one boxed item ticked. |
| Owner | Architecture-WG (currently: @BalaShankar9). |
| Steps | (1) Skim PR body. (2) Walk impacted blueprint section. (3) Verify ADR exists if decision-class. (4) Verify rollback is real. (5) Verify observability emitted. (6) Approve, request changes, or escalate. |
| Output | PR review + (optionally) blueprint diff suggestion. |
| SLA | First response within 1 business day. Decision within 2 business days. |
| Escalation | If WG cannot agree, owner of the affected bounded context decides. Document the dissent in the ADR's Alternatives section. |

---

## 2 · Production Readiness Review (per release candidate)

| Field | Value |
|---|---|
| Trigger | Build promoted to release-candidate. |
| Owner | Release DRI (rotates weekly). |
| Steps | Walk [`PRODUCTION_READINESS_CHECKLIST.md`](./PRODUCTION_READINESS_CHECKLIST.md) sections A→I. Refuse to promote if any "Hard No" condition (§H) is hit. |
| Output | Sign-off comment on release issue. |
| SLA | 30 minutes for routine releases. Up to 2 hours for releases touching schema, security, or AI runtime. |
| Failure path | Block release. Open follow-up issue with what's missing. Do not negotiate. |

---

## 3 · Migration Review (per migration PR)

| Field | Value |
|---|---|
| Trigger | PR adds files in `supabase/migrations/`. |
| Owner | Database DRI (currently: @BalaShankar9). |
| Steps | (1) `scripts/governance/check_migration_safety.py` green. (2) Confirm expand-only, rollback migration committed. (3) Confirm `pg_partman` config touched if partitioned table. (4) Confirm RLS on any new public table. (5) Apply against staging Postgres copy of prod schema; capture timing. (6) For tables > 10M rows, require offline rehearsal note. |
| Output | Approval + recorded timing + runbook link if new alert. |
| SLA | Within 1 business day. |
| Failure path | Auto-block via CI; reviewer's explicit refusal otherwise. |

---

## 4 · Incident Review (per Sev1 / Sev2)

| Field | Value |
|---|---|
| Trigger | Sev1 (customer impact, SLO breach, data integrity) or Sev2 (degraded service, near-miss). |
| Owner | On-call IC during incident; postmortem lead = the engineer who shipped the triggering change (or the WG if unclear). |
| Timeline | Live war-room → mitigation → "stop the bleeding" within MTTM target. Postmortem draft within 5 business days. Postmortem published within 10 business days. |
| Postmortem template | `docs/postmortems/YYYY-MM-DD-slug.md` with: **Summary · Timeline · Customer impact · Root cause · Contributing factors · What went well · What went wrong · Detection latency · Action items (owner + SLA + tracking issue) · Lessons (link to blueprint section if amended).** |
| Blameless rule | Names appear only when assigning action items, never when describing decisions made under uncertainty. |
| Action items | Each one has a GitHub issue, an owner, and an SLA. Reviewed in the next architecture-WG meeting. SLA breaches escalate to leadership. |

---

## 5 · Operational Change Approval

For non-PR production changes (config flips, manual data fixes, manual scaling, manual rotation, runbook execution that mutates state).

| Field | Value |
|---|---|
| Trigger | Engineer wants to make a production change without a PR. |
| Owner | Two-person rule: the executing engineer + a second on-call (peer review). |
| Procedure | (1) Open a "change ticket" issue with: change, reason, blast radius, rollback, expected duration. (2) Second on-call approves with `LGTM-CHANGE`. (3) Execute, narrate live in #incidents channel. (4) Post completion + verification result in the issue. (5) Within 24h, file a follow-up PR if the change implies a code/config commit (e.g., flag flip permanently). |
| Audit trail | All change tickets remain open until the follow-up PR merges (or "no follow-up needed" justification recorded). |
| Forbidden | Production console SSH for code edits. Direct DB writes for routine fixes (must be a script in `scripts/ops/` reviewed in a PR). |

---

## 6 · Quarterly Architecture Review

| Field | Value |
|---|---|
| Trigger | Quarterly (calendar). |
| Owner | Architecture-WG. |
| Agenda | (1) Walk §18 P0/P1 register: closed? in flight? stalled? (2) Walk §19 risk matrix: scores changed? (3) Walk §20 tech-debt register: retire one. (4) Review SLO error budgets. (5) Review feature-flag registry: any flag past sunset? (6) Review ADRs from last quarter: any need superseding? (7) Decide on next-stage trigger status. |
| Output | Updated blueprint sections + meeting notes in `docs/architecture/quarterly/YYYY-Qn.md`. |
| Cadence safeguard | Skipping is allowed only if there's an active Sev1; reschedule within the quarter. |

---

## 7 · ADR Lifecycle

| Phase | Action | Trigger |
|---|---|---|
| Reserve | Add row to `docs/adrs/README.md` with `Proposed` status. | Decision identified. |
| Draft | Copy `ADR_TEMPLATE.md` → `docs/adrs/NNNN-slug.md`. Open implementation PR draft alongside. | Author has rough decision. |
| Review | Architecture-WG review. | Draft is complete enough to evaluate. |
| Accept | Flip status to `Accepted`. Implementation PR may proceed. | WG consensus. |
| Implement | Implementation PR merges. ADR's "Implementation Plan" checklist gets ticked. | After WG accept. |
| Validate | After 1 release cycle, ADR author confirms "Validation" criteria met. | Post-release. |
| Supersede | Create new ADR; mark old as `Superseded by ADR-NNNN`. Never delete. | Decision changes. |

---

## 8 · Forbidden processes

To prevent process bloat, these are explicitly **not** added:

- **Architecture office hours.** Use async PR review.
- **Cross-team alignment meetings.** Use ADRs.
- **"Innovation review" boards.** Spike → ADR → PR is the path.
- **Quarterly OKRs at architecture level.** Roadmap is the milestones doc; OKRs are a product concern.
- **Process for adding processes.** Adding a process requires (1) demonstrated 3+ failures the process would have prevented, (2) ADR.
