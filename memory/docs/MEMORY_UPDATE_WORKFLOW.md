# Memory update workflow

Decision tree for "where does this thought go?" Use it; don't dump
everything into `/memories/repo/`.

## Triggers + targets

```
Did something ship (code, infra, doc)?
  └── yes → /memories/repo/<slug>-shipped.md   (session note)
            + bump context/CHANGELOG_INTELLIGENCE.md if user-visible

Did we make an irreversible architectural choice?
  └── yes → docs/adrs/NNNN-<slug>.md           (ADR)
            + /memories/repo/ note linking it

Did production break?
  └── yes → memory/incidents/<YYYY-MM-DD>-<slug>.md
            + runbook update if procedure changed
            + ADR if root cause was an architectural decision

Did we discover a non-obvious system invariant?
  └── yes → memory/business_logic/<slug>.md      (if domain rule)
            memory/security/<slug>.md            (if security)
            memory/scaling/<slug>.md             (if perf / capacity)
            memory/architecture/<slug>.md       (if cross-cutting design)

Did we identify technical debt worth tracking?
  └── yes → memory/technical_debt/<slug>.md
            + a TD-N tag in PR titles

Did we write a new procedure?
  └── yes → docs/runbooks/<slug>.md

Did we change a test pattern / fixture / mock strategy?
  └── yes → memory/testing/<slug>.md            (lightweight)
            docs/superpowers/<slug>.md          (heavyweight, blessed)

Otherwise (research notes, design sketches, todos)?
  └── /memories/repo/ — but mark with "(notes)" in the title
```

## Per-target write contracts

### `/memories/repo/<slug>.md` (session memory)

Required sections: Title, PR/commit link, date, why, what changed,
validation, follow-ups (optional), linked memory.

Audience: future agents searching for prior work. Be specific about
file paths and identifiers (graph builder picks them up).

### `docs/adrs/NNNN-<slug>.md` (architecture decision record)

Use the existing template (see `docs/adrs/0001-*.md`). Required
sections: status, context, decision, consequences, alternatives
considered. NNNN is the next free number — check
`ls docs/adrs | tail -5`.

### `memory/incidents/<YYYY-MM-DD>-<slug>.md`

Schema is enforced by `FAILURE_LEARNING_SYSTEM.md`. Required:
detection, impact, root cause, fix, prevention. Importance defaults to
4.0 in the indexer, so incidents surface aggressively.

### `memory/decisions/<slug>.md`

Lighter than an ADR. Use when the choice is reversible but worth
remembering. Required: situation, options considered, choice,
expiration condition (when to revisit).

### `memory/business_logic/<slug>.md`

Domain rules that the code enforces and that future contributors must
not silently change. Examples: hireability score weights, JD/resume
contract fields, scoring rubrics. Importance 3.5.

### `memory/security/<slug>.md`

Security posture: RLS policies in plain English, threat model entries,
secret rotation log, audit findings. Importance 4.5 — these surface
*before* most other content for security-adjacent queries.

### `memory/scaling/<slug>.md`

Capacity decisions, performance budgets, hot-path constraints. Pair
with k6 results when relevant.

### `memory/architecture/<slug>.md`

Cross-cutting design briefs that aren't ADRs (more "how it fits
together" than "why we chose"). Importance 4.5.

### `memory/technical_debt/<slug>.md`

Format:

```markdown
# TD-N: <title>

- **Identified**: <date / PR>
- **Cost if ignored**: <concrete: e.g. "+30 LOC per touch in jobs.py">
- **Cost to fix**: <rough estimate>
- **Target PR**: <m12-prNN once scheduled>
- **Status**: open | in-progress | done
- **Linked memory**: <other notes>
```

## Anti-patterns

- **Writing to `/memories/repo/` when an ADR is warranted.** Session
  notes age out of agent attention faster (importance 2.5 vs ADR 5.0).
- **Writing to ADRs for reversible choices.** ADRs should be expensive
  to add, so the surface stays curated. Use `memory/decisions/` for
  light decisions.
- **Updating an old ADR in place to flip its decision.** Open a new
  ADR that supersedes the old one and link both directions. The
  history matters.
- **Memory notes with no concrete identifiers.** They don't get picked
  up by the graph and they don't surface for future queries because
  the BM25 lexicon is empty.

## Re-index after writing

The store is content-addressed; re-running `cli index` after writing a
new memory file costs ~1 second (only changed files re-process). Do
this *immediately* after writing the note, so it's queryable for the
very next task.

```bash
python -m scripts.memory.cli index
python -m scripts.memory.cli search "<some keyword from your new note>" -k 3
```

If the second command doesn't return your note in the top 3, your note
is too vague — rewrite it with more specific terms.

## Aging policy

We do **not** auto-delete memory. Every note's `mtime` is the
recency-decay anchor (90-day half-life), but importance is preserved
forever. ADRs and incidents never age out of practical reach because
their importance dominates the recency penalty.

If a note is genuinely obsolete (superseded, fixed, never relevant
again), do one of:

- Add a `> SUPERSEDED-BY: <link>` line at the top. Keeps the audit
  trail; the new note will outrank it on relevance + recency.
- Move to `docs/_archive/` (already exists) for very old material.
- Hard-delete only if the note contains a *factual error* that could
  mislead future agents.
