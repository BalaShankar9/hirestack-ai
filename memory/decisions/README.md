# memory/decisions

**Lightweight, reversible** decisions worth remembering. Use this
when a full ADR is overkill but "nobody remembers why" would hurt
in 6 months.

- **Importance**: 4.0
- **Lifecycle**: each note has an explicit "expiration condition" —
  when to revisit

## When this vs an ADR

| Question | Decision (`memory/decisions/`) | ADR (`docs/adrs/`) |
| -------- | ------------------------------ | ------------------ |
| Reversible? | Yes, in a single PR | No, requires migration |
| Affects external contracts? | No | Often |
| Affects data model? | No | Yes |
| Read by future agents? | Yes | Yes |
| Numbered? | No (slug only) | Yes (NNNN) |

## Write contract

```markdown
# <Decision title — present tense>

- **Date**: YYYY-MM-DD
- **Trigger**: <what forced the decision>

## Situation
<One paragraph context.>

## Options considered
- **A**: <description>. Pros / cons.
- **B**: <description>. Pros / cons.

## Choice
<Which option, in one paragraph.>

## Expiration condition
<Concrete signal that says "revisit this": e.g. "when corpus exceeds
50k chunks", "when OpenAI pricing drops below $X", "after 6 months",
"when test runtime exceeds 60s".>

## Linked
- PR(s)
- related ADRs
- related memory notes
```
