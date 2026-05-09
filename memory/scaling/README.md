# memory/scaling

Capacity, performance, and hot-path constraints.

- **Importance**: 3.5

## What goes here

- Performance budgets (latency, throughput) per surface
- k6 baseline numbers + dates
- Provider rate-limit awareness (OpenAI, Anthropic, Gemini, Supabase)
- Hot-path rules ("don't add a synchronous DB call here")
- Index-strategy notes for Supabase tables

## Write contract

```markdown
# <Title — what scales / what's the budget>

- **Date**: YYYY-MM-DD
- **Surface**: <subsystem / endpoint / job>

## Budget
<Quantified target: p95 latency, RPS, queue depth, etc.>

## Current
<Most recent measurement + date + how measured (k6 scenario, prod metric).>

## Bottleneck
<Where the budget would break first.>

## Mitigations available
<Numbered list of options if budget is breached.>

## Linked
- k6 scenario in `k6/scenarios/`
- monitoring dashboard link
- related ADRs
```
