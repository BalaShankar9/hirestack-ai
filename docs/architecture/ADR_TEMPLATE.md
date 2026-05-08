# ADR-NNNN: <Title (verb + noun)>

**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-XXXX
**Date:** YYYY-MM-DD
**Deciders:** @name1, @name2
**Context tags:** identity | billing | orchestration | ai-runtime | knowledge | realtime | eventing | content | api | observability | security | cost | data | release

> Numbering is sequential under [`docs/adrs/`](../adrs/).
> Keep ADRs short (~1 page). Long rationale belongs in the blueprint or a design doc.
> Do not edit an Accepted ADR; supersede it with a new one.

---

## 1 · Context

What problem are we solving? Why now? What constraints (regulatory, cost, latency, team)?
Reference current state via [`WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`](./WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md) section numbers. Cite code paths.

## 2 · Decision

State the decision in one paragraph. Use the active voice ("We will…").
Include the **specific** technical choice (library version, infrastructure SKU, schema name).

## 3 · Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| A: ___ | | | |
| B: ___ | | | |
| C (chosen): ___ | | | n/a |

## 4 · Consequences

### Positive
- ___

### Negative / cost
- ___

### Neutral / new obligations
- ___

## 5 · Implementation Plan

- [ ] PR(s): #___
- [ ] Migration steps (expand → migrate → contract):
- [ ] Feature flag: `ff_<name>`
- [ ] Rollback plan:
- [ ] Observability: new metrics / spans / events emitted
- [ ] Updates to blueprint section ___
- [ ] Updates to runbook(s): ___

## 6 · Validation

How will we know this decision was correct?

- [ ] SLO unaffected (specify)
- [ ] Cost within budget
- [ ] No new P0/P1 risks introduced
- [ ] Eval / contract / integration tests added

## 7 · References

- Blueprint section: §___
- Related ADRs: ADR-___
- External docs / standards: ___
- Discussion threads: ___
