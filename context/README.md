<!--
context/README.md — Index for the Living Engineering Brain.

This folder is a continuously-maintained, codebase-specific knowledge layer
for HireStack AI. Each file is a 300-600 line synthesis of one concern,
cross-referencing the canonical sources rather than duplicating them.

When you add a new system, table, route, agent, or migration, update the
matching context file in the same PR. CI checks freshness via
`scripts/governance/check_context_freshness.py` (advisory, non-blocking).
-->

# `/context/` — HireStack AI Living Engineering Brain

> **Purpose.** Make the codebase legible to any new engineer (human or AI) in
> under one hour. Each file synthesizes ONE concern of the system, points at
> the canonical sources of truth, and explains "what is here, why it is here,
> and what changes when you change it."
>
> **Not a duplicate.** When the canonical doc (blueprint, ADR, runbook) and a
> context file disagree, the canonical doc wins. Context files are the *map*,
> not the *territory*.
>
> **Self-updating contract.** See [`CONTRIBUTING.md`](../CONTRIBUTING.md)
> section "Context system maintenance." The advisory checker lives at
> [`scripts/governance/check_context_freshness.py`](../scripts/governance/check_context_freshness.py)
> and is wired as `make check-context`.

---

## File index

| # | File | Concern | Watches |
|---|---|---|---|
| 1 | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | What HireStack AI is, who it serves, what it ships | `README.md`, `pyproject.toml`, `frontend/package.json` |
| 2 | [ARCHITECTURE.md](ARCHITECTURE.md) | Component map, deployables, request lifecycle | `docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`, `docs/ARCHITECTURE.md` |
| 3 | [FRONTEND_CONTEXT.md](FRONTEND_CONTEXT.md) | Next.js app, routes, state, dynamic imports | `frontend/src/**`, `frontend/package.json` |
| 4 | [BACKEND_CONTEXT.md](BACKEND_CONTEXT.md) | FastAPI app, route registry, services, middleware | `backend/main.py`, `backend/app/**` |
| 5 | [DATABASE_CONTEXT.md](DATABASE_CONTEXT.md) | Postgres tables, RLS, partitions, migrations | `supabase/migrations/**` |
| 6 | [API_CONTEXT.md](API_CONTEXT.md) | HTTP/SSE surface, contract types, idempotency | `backend/app/api/routes/**`, `packages/events/**` |
| 7 | [AUTH_SECURITY_CONTEXT.md](AUTH_SECURITY_CONTEXT.md) | JWT, RLS, capability tokens, prompt injection | `backend/app/core/security.py`, `ai_engine/agents/prompt_*` |
| 8 | [DEVOPS_INFRA_CONTEXT.md](DEVOPS_INFRA_CONTEXT.md) | Hosting, Docker, CI, deployment topology | `infra/**`, `Dockerfile*`, `.github/workflows/**` |
| 9 | [AI_CONTEXT.md](AI_CONTEXT.md) | Pipeline, agents, chains, model router, cost | `ai_engine/**` |
| 10 | [TESTING_CONTEXT.md](TESTING_CONTEXT.md) | Test pyramid, contracts, eval gates | `backend/tests/**`, `frontend/e2e/**`, `k6/**` |
| 11 | [PERFORMANCE_CONTEXT.md](PERFORMANCE_CONTEXT.md) | Latency budgets, hot paths, caching | `ai_engine/cache.py`, `backend/app/core/queue.py` |
| 12 | [FILE_TREE.md](FILE_TREE.md) | Annotated repository map | (whole tree) |
| 13 | [BUSINESS_LOGIC_CONTEXT.md](BUSINESS_LOGIC_CONTEXT.md) | Domain rules, invariants, lifecycle states | `backend/app/services/**` |
| 14 | [TECH_DEBT.md](TECH_DEBT.md) | TD-1..TD-10 register synthesis | `docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#20` |
| 15 | [RELEASE_READINESS.md](RELEASE_READINESS.md) | Pre-deploy gates, rollout discipline | `docs/architecture/PRODUCTION_READINESS_CHECKLIST.md` |
| 16 | [CHANGELOG_INTELLIGENCE.md](CHANGELOG_INTELLIGENCE.md) | What shipped, when, why, links to PRs | `CHANGELOG.md`, `/memories/repo/m*-pr*-shipped.md` |
| 17 | [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | Open bugs, surprising behaviour, gotchas | `/memories/repo/**`, GitHub issues |
| 18 | [SCALABILITY_ROADMAP.md](SCALABILITY_ROADMAP.md) | Stage A/B/C plan, scaling triggers | `docs/architecture/SCALING_PHASES.md` |

---

## Conventions every context file follows

Every file in this folder begins with a YAML front-matter block:

```yaml
---
title: <Concern>
last_synced: 2026-05-08
watch_paths:
  - <glob>
  - <glob>
canonical_sources:
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#<anchor>
  - docs/runbooks/<file>.md
update_when:
  - <trigger>
---
```

`check_context_freshness.py` reads `watch_paths` and warns when any matching
file has been modified since `last_synced`. This is **advisory** — the script
exits 0 in all cases. Treat warnings as a polite reminder.

## How to consume this folder

- **New engineer onboarding:** read in order 1, 2, 12, 9, 4, 3, 5 — that
  covers ~80% of system surface in under one hour.
- **Reviewing a PR:** open the context file matching the PR's primary surface
  area, scan its "Watch list" section, then read the diff with that lens.
- **Debugging an outage:** start at [KNOWN_ISSUES.md](KNOWN_ISSUES.md) and
  [PERFORMANCE_CONTEXT.md](PERFORMANCE_CONTEXT.md), then jump to the
  matching runbook in `docs/runbooks/`.
- **AI assistant context window:** files 2, 4, 9, 14, 16 give a coding agent
  enough to reason about most changes without re-discovering structure.
