# memory/testing

Lightweight notes about test patterns, flakes, and test-harness
gotchas. Heavyweight blessed practices live in
[`docs/superpowers/`](../../docs/superpowers/).

- **Importance**: 2.5

## What goes here

- Flake register (test id, flake rate, suspected cause)
- Slow-test ledger (test id, runtime, cost/benefit of speeding up)
- Fixture map (which fixture used by which suite, ownership)
- Mock strategy notes (what we mock, what we don't, why)

## Write contract

```markdown
# <Title>

- **Date**: YYYY-MM-DD
- **Suite**: backend | frontend | mobile | e2e

## Pattern
<What pattern / fixture / mock / decision.>

## Why
<Trade-off explanation.>

## Examples
- `backend/tests/path/test_x.py::test_name`
- `frontend/tests/path/x.spec.ts`

## Avoid
<What not to do, with reasoning.>
```
