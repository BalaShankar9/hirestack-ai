# Agent memory protocol

**Mandatory** for every AI agent (Copilot, Claude, custom subagents,
human contributors using AI assistance) acting in this repo. The
protocol is two steps. Skipping either one wastes the system.

## Pre-task — query before you act

Before writing code, opening a PR, or making a non-trivial decision:

```bash
python -m scripts.memory.cli context "<a 5-12 word description of your task>" --budget 6000
```

Copy the output into your working context. If the task spans more than
one subsystem, run two narrower queries instead of one broad one.

Specialised lookups:

```bash
# Has this been decided already?
python -m scripts.memory.cli search "<topic>" --kind adr --kind decision

# Has this broken before?
python -m scripts.memory.cli search "<symptom>" --kind incident

# Is there a runbook?
python -m scripts.memory.cli search "<operation>" --kind runbook

# What touches this file?
python -m scripts.memory.cli neighbours code:app.api.routes.generate.jobs --depth 1
```

If your edits affect a file that hasn't been indexed since your last
edit, run `python -m scripts.memory.cli index` first — incremental,
~1 second.

## Post-task — log what you learned

After shipping (PR opened, decision made, incident resolved), write a
session note to `/memories/repo/<short-slug>.md` with at minimum:

```markdown
# <Title — what shipped or what was decided>

- **PR / commit**: <link or sha>
- **Date**: <YYYY-MM-DD>
- **Why**: <one sentence on the trigger>
- **What changed**: <bullets>
- **Validation**: <test counts, smoke results>
- **Follow-ups**: <bullets, optional>
- **Linked**: <other memory notes, ADRs, incidents>
```

Then re-index so the note is queryable:

```bash
python -m scripts.memory.cli index
```

That's it. ~5 minutes per task. The compound payoff is enormous —
every future agent on every future task can find your reasoning.

## When to escalate beyond a session note

| If the change is… | Write to… |
| ----------------- | --------- |
| A reversible decision the team should remember | `/memories/repo/*.md` (this is the default) |
| An irreversible architecture choice (data model, framework swap, contract change) | New ADR in `docs/adrs/NNNN-*.md` |
| A new operational procedure | `docs/runbooks/*.md` |
| A production incident | `memory/incidents/<YYYY-MM-DD>-<slug>.md` (use the schema in `FAILURE_LEARNING_SYSTEM.md`) |
| A new permanent system invariant (security, business logic) | `memory/security/` or `memory/business_logic/` |

## Quality bar for memory entries

- **Specific paths.** Backtick-wrap them: `` `backend/app/api/routes/generate/jobs.py` ``.
  This is what the graph builder picks up to wire memory→code edges.
- **Cite ADRs by id.** `ADR-0040`, `ADR 0040`. Both forms are recognised.
- **Concrete validation.** "tests pass" is useless. "109/109 tests
  green in 2.94s, smoke ran clean" is useful.
- **One topic per file.** Easier to retrieve and easier to age out.

## How automated agents identify themselves

Optional but encouraged: prefix the slug with the agent's role.

- `m12-pr19-td1-split-jobs-shipped.md` → human + Copilot, PR-shipped
- `subagent-research-frontend-routes.md` → background research run
- `incident-2026-05-08-supabase-rls.md` → incident note

## Failure modes (and what to do)

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| `cli search` returns nothing relevant | Index stale | `cli index` |
| `cli search` returns too much noise | Query too vague | Rephrase with concrete identifiers; add `--kind` filter |
| You wrote a memory note but search can't find it | Index stale | `cli index` (it's content-addressed; only re-reads changed files) |
| Two notes contradict | Bad: nobody resolved a conflict | Open a third note that explicitly links and resolves both, or open an ADR |

## See also

- [MEMORY_UPDATE_WORKFLOW.md](MEMORY_UPDATE_WORKFLOW.md) — when to write
  what kind of memory.
- [MEMORY_RANKING_SYSTEM.md](MEMORY_RANKING_SYSTEM.md) — how importance
  + recency drive what surfaces first.
- Repo-root [`AGENTS.md`](../../AGENTS.md) — the short version of this
  contract (10 lines).
- `.github/copilot-instructions.md` — Copilot-specific phrasing.
