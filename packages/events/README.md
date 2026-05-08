# `packages/events` — versioned event contracts (PR m6-pr26)

Source-of-truth JSON Schema definitions for every domain event that
flows through `events_outbox` → Redis Streams → consumers. One file
per `(event_type, version)`:

```
packages/events/schema/v1/
  ├─ envelope.schema.json
  ├─ aim.assignment.created.v1.schema.json
  ├─ aim.source.created.v1.schema.json
  ├─ generation.requested.v1.schema.json
  ├─ generation.completed.v1.schema.json
  └─ mission.draft.created.v1.schema.json
```

## Why a shared package

The Pydantic `EventEnvelope` lives in the backend; the TypeScript SSE
consumer lives in the frontend; mobile clients (PR future) will live in
Kotlin. Three implementations of "what does
`generation.completed.v1.payload` look like" is how prod outages
happen.

This package is the **canonical contract**. Codegen targets:

| Target           | Tool                  | Output                      |
| ---------------- | --------------------- | --------------------------- |
| Python (Pydantic) | `datamodel-code-generator` | `backend/app/core/events/generated/` |
| TypeScript        | `json-schema-to-typescript` | `frontend/src/types/events/` |
| Kotlin            | `quicktype`               | `mobile/lib/events/`        |

For PR m6-pr26 the schemas + envelope contract test ship; codegen
scaffolds land in PR m6-pr26b once we have the first cross-language
consumer to validate against.

## Versioning rule

Every schema filename ends in `.vN.schema.json`. The version in the
filename MUST equal the `event_version` field in the schema MUST equal
`REGISTERED_EVENT_TYPES[name].version` in
`backend/app/core/events/types.py`. The contract test
(`backend/tests/contracts/test_event_schema_contract.py`) enforces all
three.

To evolve a schema:

1. Add a new file `<name>.vN+1.schema.json` (do NOT edit the old one).
2. Add a new `EventType("...", N+1)` constant in `types.py`.
3. Update producers to emit the new version.
4. Keep consumers reading both versions until the old version drains
   from the outbox.
5. Once `events_outbox` shows zero rows of the old version, drop it
   from the registry.

Schemas are immutable once shipped; changes always mean a new version.
