# memory/business_logic

Domain rules the code enforces. The point of this directory is that
**these rules must not be silently changed** by future refactors —
having them written down means future agents (human and AI) are
forced to acknowledge them before changing behaviour.

- **Importance**: 3.5
- **Lifecycle**: changes here are intentional events; pair with an ADR

## Write contract

```markdown
# <Rule name in present tense>

- **Date**: YYYY-MM-DD
- **Owners**: <team / area>

## Rule
<Plain-English statement of what the system does.>

## Why
<Business reasoning. Not engineering reasoning.>

## Where enforced
- `path/to/code.py:LineRange` — primary check
- `path/to/other.py:LineRange` — secondary
- `supabase/migrations/NNN.sql` — DB constraint

## Tests
<Test files / ids that lock this in.>

## Change procedure
<What must happen for this rule to legitimately change. Usually:
ADR + product approval + migration plan.>
```

## Examples of good fits

- Hireability score weights (per JD class)
- Resume parsing field contract (mandatory vs optional)
- Org-level cascade delete invariants
- Watchlist auto-prep trigger conditions
