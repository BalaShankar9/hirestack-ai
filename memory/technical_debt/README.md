# memory/technical_debt

The TD register. Each entry has identified cost, fix cost, and a
target PR (once scheduled).

- **Importance**: 3.0
- **Naming**: `td-NNN-<slug>.md` (NNN is a sequential id; check
  `ls memory/technical_debt | tail -5`)

## Write contract

```markdown
# TD-NNN: <one-line title>

- **Identified**: <YYYY-MM-DD or PR>
- **Identified by**: <person / agent>
- **Status**: open | scheduled | in-progress | done

## Cost if ignored
<Concrete: "+30 LOC per touch in jobs.py", "+200ms p95 per request",
"~2h/sprint of confusion for new contributors", etc.>

## Cost to fix
<Rough estimate. T-shirt size is fine: S/M/L/XL.>

## Target PR
<m12-prNN once scheduled, otherwise "unscheduled">

## Approach
<One paragraph on the proposed fix.>

## Risk if fixed wrong
<What could break. Often the reason it's debt and not just "not done yet".>

## Linked
- the file(s) that hurt today
- prior PRs that touched this area
- related debt entries
```

## Lifecycle

- `open` → `scheduled` (when a target PR exists)
- `scheduled` → `in-progress` (when PR opened)
- `in-progress` → `done` (when PR merged; add closing memory note link)
- Don't delete `done` entries — the audit trail is valuable.
