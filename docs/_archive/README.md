# Documentation Archive

This directory holds historical planning documents, deployment journals, audits,
and one-off design briefs that are **no longer canonical** but kept for context
and traceability.

## Layout

Archived docs are bucketed by the month they were retired from the active
documentation set, e.g.:

```
docs/_archive/
  2026-05/      # archived during May 2026 (PR-1 of M1)
  2026-06/      # next batch
```

## Rules

- **Do not link to archived docs from active code, runbooks, or onboarding
  material.** If something here is still useful, promote it back into the active
  docs and update it before linking.
- Archived docs are read-only by convention. Do not patch them in place — open a
  new doc under `docs/` and reference the archived version by path if needed.
- Anything in this archive may be deleted in a future cleanup PR without notice.

## What lives outside the archive

The following remain canonical and live under `docs/`:

- `docs/ARCHITECTURE.md` — single source of truth for system topology.
- `docs/adrs/` — Architecture Decision Records.
- `docs/runbooks/` — operational runbooks.
- `docs/superpowers/` — repo-scoped agent skill notes.
- `docs/SLO.md` — service level objectives.
- `docs/PROJECT_JOURNAL.md` — rolling project journal.
