# memory/security

Security posture. Plain-English mirror of the controls actually
running in code, RLS policies, and infra.

- **Importance**: 4.5 (surfaces *before* most other content)
- **Lifecycle**: append-mostly; never delete without ADR

## What goes here

- RLS policies in plain English (paired with the SQL migration)
- Threat model entries
- Secret rotation log (which secrets, when rotated, by whom)
- Audit findings + remediation status
- Permission boundary documentation

## Write contract

```markdown
# <Title — present tense>

- **Date**: YYYY-MM-DD
- **Class**: rls | secrets | threat | audit | rotation
- **Owners**: <team>

## Statement
<What the security control is, in plain English.>

## Implementation
- `path/to/file.py:LineRange`
- `supabase/migrations/NNN.sql`
- infra config link

## Verification
<How we test that the control is actually working — test ids, manual
verification steps, monitoring alerts.>

## Threats addressed
<What attack class this prevents.>

## Linked
- ADR-NNNN
- incident notes if this control was added in response to one
```

## Anti-patterns

- Storing secrets here. Ever.
- Vague rules ("we sanitise input"). Be specific: which input, where,
  with what library, against what threat.
