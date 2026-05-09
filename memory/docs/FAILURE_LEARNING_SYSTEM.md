# Failure learning system

How HireStack remembers production failures so they don't repeat.

## The contract

Every production incident produces an incident note in
`memory/incidents/<YYYY-MM-DD>-<slug>.md`. The schema below is
mandatory — incidents missing required fields are bugs in the process.

The indexer assigns incidents `importance 4.0`, so they surface for
nearly any query touching the affected subsystem. Combined with their
kind tag, they're queryable in isolation:

```bash
python -m scripts.memory.cli search "rate limit 429" --kind incident
python -m scripts.memory.cli search "rls policy violation" --kind incident
```

## Incident note schema

```markdown
# INC-NNNN: <one-line title in present tense>

- **Date**: <YYYY-MM-DD>
- **Detected by**: <on-call alert | user report | automated check | post-deploy smoke>
- **Severity**: SEV-1 | SEV-2 | SEV-3 | SEV-4
- **Duration**: <e.g. "47 minutes from first alert to resolved">
- **Affected systems**: <bulleted list of subsystems / files>

## Detection
<How did we notice? Which alert / metric / user signal?>

## Impact
<Concrete user-visible effect. Numbers if you have them: requests
failed, users affected, $ at risk.>

## Timeline
- HH:MM  first alert
- HH:MM  on-call acked
- HH:MM  rollback / mitigation
- HH:MM  full resolution

## Root cause
<The actual technical cause. Cite specific files / commits / PRs.>

## Fix
<What we did to resolve.>

## Prevention
<What we are changing so this can't happen again. Concrete:
new test, new alert, new validation, new ADR.>

## Linked
- ADR(s): ADR-NNNN
- PR(s): #NN
- Memory: <link to /memories/repo/ note about the fix PR>
- Runbook: <link if procedural change required>
```

## Why this schema (and not freeform)

Incidents are the highest-leverage memory in the system. A future
agent debugging a similar symptom should be able to find the prior
incident in one query and read it in 2 minutes. That requires:

- **Title in present tense** so the search query "rate limit 429"
  matches even after the incident is resolved.
- **Affected systems** as plain words, not jargon — these go into the
  BM25 lexicon.
- **Root cause + Fix + Prevention** as separate sections so the agent
  can scan to the relevant one.

## Severity guidelines

| SEV | Meaning | Examples |
| --- | ------- | -------- |
| 1 | Total outage / data loss / security breach | DB down, auth broken, RLS bypass |
| 2 | Major degradation | Pipeline backlog, 50%+ error rate, slow critical path |
| 3 | Partial degradation | One feature broken, one provider failing over |
| 4 | Minor / contained | Single non-critical job retrying, cosmetic regression |

Anything SEV-2 or above mandates an ADR for the prevention work, even
if the prevention is "added test X". This forces us to think about
whether the architecture made the failure possible.

## Prevention enforcement

The "Prevention" section MUST be a concrete, committed change — not a
vow. Acceptable forms:

- A new test (link to PR)
- A new alert (link to monitoring config)
- A new validation in code (link to file:line)
- A new ADR (link to ADR id)
- A new runbook (link to docs/runbooks/)

If the prevention can't be made concrete, the incident isn't closed.

## Anti-patterns

- **"Investigated, no action needed."** Then it isn't an incident; it's
  a noisy alert. Either fix the alert or document the false-positive
  pattern in a runbook.
- **One mega-note for multiple incidents.** Split them. Each gets its
  own searchable note.
- **Linking the fix PR but not the prevention PR.** The fix stops
  bleeding; the prevention stops the recurrence. Both must be linked.
- **Burying the root cause in narrative prose.** State it directly in
  the "Root cause" section. Save the story for context.

## Retrieval mandate (for agents)

Before touching code in a subsystem with a history of incidents,
agents should run:

```bash
python -m scripts.memory.cli search "<subsystem keywords>" --kind incident -k 5
```

If anything turns up, read it. The 5 minutes spent reading saves
hours of repeating the same mistake.

## Today's state (m12-pr20)

`memory/incidents/` is empty at ship time. The infrastructure is in
place; the retroactive backfill is a follow-up: scan
`/memories/repo/*.md` and `docs/PROJECT_JOURNAL.md` for words like
"incident", "outage", "broke", "rolled back", and convert qualifying
entries into incident notes per this schema.

## Cross-references

- [MEMORY_UPDATE_WORKFLOW.md](MEMORY_UPDATE_WORKFLOW.md) — when an
  incident note is the right home for a thought.
- [MEMORY_RANKING_SYSTEM.md](MEMORY_RANKING_SYSTEM.md) — why
  importance 4.0 and what that means for retrieval.
- [AGENT_MEMORY_PROTOCOL.md](AGENT_MEMORY_PROTOCOL.md) — the broader
  pre-task / post-task contract.
