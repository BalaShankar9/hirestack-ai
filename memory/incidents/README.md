# memory/incidents

Production postmortems. Schema is **mandatory** — see
[`../docs/FAILURE_LEARNING_SYSTEM.md`](../docs/FAILURE_LEARNING_SYSTEM.md)
for the full spec.

- **Importance**: 4.0 (surfaces aggressively for any matching query)
- **Naming**: `<YYYY-MM-DD>-<slug>.md`
- **Closure rule**: an incident isn't closed until "Prevention" is a
  concrete, committed change (test, alert, validation, ADR, runbook)

## Required sections

- INC-NNNN title (present tense)
- Date / Detected by / Severity / Duration / Affected systems
- Detection
- Impact (with concrete numbers)
- Timeline
- Root cause
- Fix
- Prevention
- Linked (ADRs, PRs, memory, runbook)

## Severity guide

| SEV | Trigger |
| --- | ------- |
| 1 | Total outage / data loss / security breach |
| 2 | Major degradation, 50%+ error rate |
| 3 | Partial degradation, single feature broken |
| 4 | Minor / contained, no user impact |

SEV-2 and above mandate an ADR for the prevention work.

## See also

- [`../docs/FAILURE_LEARNING_SYSTEM.md`](../docs/FAILURE_LEARNING_SYSTEM.md)
- [`docs/runbooks/`](../../docs/runbooks/) — procedures referenced in fixes
