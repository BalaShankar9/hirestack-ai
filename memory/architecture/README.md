# memory/architecture

Cross-cutting design briefs that explain **how the system fits together**
without rising to the irreversibility bar of an ADR.

- **Importance**: 4.5 (surfaces aggressively)
- **Lifecycle**: stable; supersede via a new note + link, don't edit in place
- **Pairs with**: [`docs/adrs/`](../../docs/adrs/) (ADRs say *why*; these say *how it fits*)

## Write contract

```markdown
# <Title — present-tense system fact>

- **Date**: YYYY-MM-DD
- **Status**: current | superseded by <link>

## Scope
<Which subsystems this brief covers.>

## Design
<Diagrams / numbered components / data flow.>

## Invariants
<What must always be true. These are the things future contributors
must not silently break.>

## Linked
- ADR-NNNN
- `path/to/code.py`
- other architecture briefs
```

## Examples of good fits

- "How the agent pipeline orchestrator routes between providers"
- "Temporal worker / FastAPI process boundary"
- "Frontend state model and SSE consumption"

## Anti-fits (use a different directory)

- One-off PR notes → `/memories/repo/`
- Domain rules → `business_logic/`
- Procedure → `docs/runbooks/`
- Decision rationale → ADR
