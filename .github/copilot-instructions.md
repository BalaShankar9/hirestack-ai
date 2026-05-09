# Copilot instructions for HireStack AI

This repo has a project-wide memory system. Every Copilot interaction
must use it. Full details in [`AGENTS.md`](../AGENTS.md) at the repo
root and the [`memory/docs/`](../memory/docs/) spec set.

## Pre-task (mandatory)

When starting any non-trivial task, load context from the memory system
before making changes:

```bash
python -m scripts.memory.cli context "<5-12 word description of task>" --budget 6000
```

If your work spans multiple areas, run two narrower queries instead of
one broad one. For decision-shaped questions, prefer kind filters:

```bash
python -m scripts.memory.cli search "<topic>" --kind adr --kind decision
python -m scripts.memory.cli search "<symptom>" --kind incident
python -m scripts.memory.cli search "<operation>" --kind runbook
```

If files have changed since the last index, re-index first
(~1 second incremental):

```bash
python -m scripts.memory.cli index
```

## Post-task (mandatory)

After shipping a change, write a session memory note to
`/memories/repo/<short-slug>.md`. Required fields:

- title (action-shaped, e.g. "m12-prNN: extract X from Y")
- PR or commit link
- date (YYYY-MM-DD)
- why (one sentence)
- what changed (bullets with backtick-wrapped file paths so the graph
  builder can wire memory→code edges)
- validation (specific: test counts, smoke results, perf numbers)
- follow-ups (optional)
- linked ADRs / incidents / prior memory notes

Then re-index:

```bash
python -m scripts.memory.cli index
```

## When session memory is not the right home

| Situation | Write to instead |
| --------- | ---------------- |
| Irreversible architectural choice | `docs/adrs/NNNN-<slug>.md` |
| Production incident | `memory/incidents/<YYYY-MM-DD>-<slug>.md` per `FAILURE_LEARNING_SYSTEM.md` |
| New operational procedure | `docs/runbooks/<slug>.md` |
| Domain rule / business logic invariant | `memory/business_logic/<slug>.md` |
| Security posture entry | `memory/security/<slug>.md` |
| Tech debt entry | `memory/technical_debt/<slug>.md` |

See `memory/docs/MEMORY_UPDATE_WORKFLOW.md` for the full decision tree.

## Repo conventions Copilot should respect

- **Branch chain.** Work proceeds in stacked PRs (m12-prNN). Open a new
  branch from the most recent open PR's head, not from main, when the
  work depends on un-merged changes.
- **Commit messages.** Use `git commit -F <file>` for prose messages.
  Backticks in `git commit -m "..."` are interpreted as zsh command
  substitution and silently strip content. ASCII only.
- **Tests.** `PYTHONPATH=. python -m pytest backend/tests/<dir> -q`
  from the repo root. Backend tests run with the venv at `.venv/`.
- **Frontend.** TypeScript + React + Tailwind in `frontend/src/`. Run
  `cd frontend && pnpm test` (or `npm test` if no pnpm).
- **AI engine.** `ai_engine/` is import-rooted at the repo root —
  `from ai_engine.agents.critic import …`, never `from agents.critic`.
- **Backend.** `backend/app/...` is import-rooted at `backend/` —
  `from app.api.routes.generate.jobs import …`, never with `backend.`.

## Security & safety reminders

- Never commit secrets. Check `.env*` is gitignored before adding.
- Never write to `/memory/vector_indexes/` or `/memory/agent_logs/` —
  those are gitignored generated artefacts.
- Don't propose `git push --force`, `git reset --hard <published-ref>`,
  or any destructive operation on shared branches without explicit
  confirmation.
- Don't bypass pre-commit / CI checks (`--no-verify`).
- See `memory/docs/AGENT_MEMORY_PROTOCOL.md` and `AGENTS.md` for the
  full quality bar.
