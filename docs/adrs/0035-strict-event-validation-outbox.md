# ADR-0035: Strict event-payload validation at `OutboxWriter.append`

**Status:** Accepted 2026-05-08
**Date:** 2026-05-08
**Deciders:** @BalaShankar9
**Context tags:** events | contracts | platform | governance

---

## 1 · Context

[`packages/events/schema/v1/`](../../packages/events/schema/v1/) holds JSON
Schema (Draft 2020-12) definitions for our domain events:
`aim.assignment.created`, `aim.source.created`, `generation.requested`,
`generation.completed`, `mission.draft.created`. The intent (per
[`WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md` §M3](../architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md))
is that this directory is the **enforced** source of truth.

Today, [`backend/app/core/events/envelope.py`](../../backend/app/core/events/envelope.py)
validates two things at `EventEnvelope` construction time:

1. The `event_type` string is in the in-process `REGISTERED_EVENT_TYPES` map
   (5 types).
2. The `event_version` integer matches the registered version for that type.

It does **not** validate the `payload` contents against any JSON Schema. The
schema files in `packages/events/` are documentation-only at runtime; nothing
prevents an emitter from writing a `generation.requested` row with a missing
`requested_modules` field, an extra `internal_debug` field, or a non-UUID
`job_id`. Downstream consumers (`OutboxRelay`, the Redis Stream subscriber,
analytics jobs) trust a contract that is not actually enforced at the
write boundary.

The blueprint calls this out explicitly in two places:

> §M3 (line 579): "`OutboxWriter.append` MUST call `validate_event(event_type,
> version, payload)` before insert. Validation failure = 500 to caller, no
> row written. The schema directory is the **enforced** source of truth, not
> advisory."

> §P1-2 (line 993): "Strict event-payload validation at `OutboxWriter.append`
> | W12 | platform | TODO".

[`SCALING_PHASES.md` L35](../architecture/SCALING_PHASES.md) further notes that
~25 currently-emitted events have no schema in `packages/events/schema/v1/`
at all — a separate follow-up to migrate those emitters one at a time.

This ADR covers the **gating mechanism**, not the per-emitter migration: we
add the validator and the kill-switch flag now so the next 2 weeks of
emitter work can be validated end-to-end as it lands.

## 2 · Decision

We will:

1. Add `backend/app/core/events/schema_registry.py` — a lazy loader that maps
   `(event_type, event_version) → jsonschema.Draft202012Validator` by reading
   `packages/events/schema/v1/<event_type>.v<version>.schema.json`. Loaded
   schemas are cached for the process lifetime. Missing schema files are
   surfaced as `MissingEventSchema` (a subclass of `EventValidationError`).
2. Add `validate_event(envelope)` — runs the validator over the envelope's
   serialised shape (`event_type`, `event_version`, `payload`). Returns the
   list of validation errors (empty on success). Never raises by itself.
3. Modify `OutboxWriter.__init__` to accept `strict: bool | None = None`
   (when `None`, reads the live `ff_strict_event_validation` flag at append
   time). Modify `OutboxWriter.append` to call `validate_event(envelope)`
   before insert with this contract:
   - **Validation passes** → insert as today.
   - **Validation fails AND strict=False** (default) → log
     `event_validation_failed_shadow` with the error list, **insert anyway**
     (status quo for existing emitters).
   - **Validation fails AND strict=True** → raise `EventValidationError`,
     **no row inserted**, caller sees 500.
   - **Schema file missing AND strict=False** → log
     `event_schema_missing_shadow`, insert anyway.
   - **Schema file missing AND strict=True** → raise `MissingEventSchema`,
     no row inserted.
4. Add `ff_strict_event_validation` (default OFF, sunset 2026-09-01). Ships
   in shadow mode so we can quantify the violation rate before flipping.
5. Add `jsonschema>=4.21,<5` to `backend/requirements.txt` (Draft 2020-12
   support and stable validator API).

## 3 · Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| A: Hand-rolled per-event validators in Python (one function per event_type) | Zero new dependency; type-checker-friendly | Drifts from the JSON-Schema source of truth in `packages/events/`; doubles the maintenance surface; loses cross-language reuse (frontend already consumes the JSON files) | Rejected: defeats the "schema directory IS the contract" principle |
| B: Pydantic models generated from the JSON schemas at build time | Stronger typing in Python | Codegen step adds a build dependency; failure mode at build is far from the failure mode at runtime; we already have `EventEnvelope` doing the structural shape and don't want a second parallel hierarchy | Rejected: complexity for marginal gain |
| C (chosen): Direct JSON-Schema validation via `jsonschema` lib at `OutboxWriter.append` | Single source of truth (the JSON files); cross-language; minimal code; works with existing envelope | Adds one dependency (`jsonschema`); validator-build cost amortised by per-process cache | Chosen |
| D: Database-side validation via Postgres `CHECK (jsonb_path_exists(...))` | Cannot be bypassed | JSON Schema is too rich for `CHECK` (formats, oneOf, refs); error messages would be opaque; harder to dark-ship behind a flag | Rejected: wrong layer |
| E: Switch to Apache Avro / Protobuf with a registry | Industry standard for high-throughput eventing | Massive blast radius; loses human-readable JSON in the outbox; not justified at our current event volume (~50 events/sec peak projected) | Rejected: scope, deferred to a future ADR if/when needed |

## 4 · Consequences

### Positive
- The `packages/events/schema/v1/` directory becomes the enforced contract
  surface (per blueprint §M3). Frontend consumers, codegen tooling, and the
  OutboxWriter all read the same files.
- Shadow mode quantifies the migration scope: counting
  `event_validation_failed_shadow` log occurrences over a week tells us
  exactly which emitters need fixing before we flip the flag.
- New emitters (and new event types) get a fast-feedback loop: forget the
  schema → see the failure in the test suite (in strict mode) or in the
  shadow log (in dev).
- Decoupled rollout: shadow → flip in canary → flip in prod, with the same
  flag mechanism we used for `ff_ai_invocations_recorder` and
  `ff_anthropic_provider`.

### Negative
- One JSON-Schema validation per envelope insert. Cost is ~50–200 µs per
  event for our payload sizes — negligible at projected event volume but
  worth measuring during canary.
- `jsonschema` library adds ~600 KB to the wheel tree and one transitive
  (`referencing`).
- Per-event validators are loaded lazily on first use. First-call latency is
  one-time per process (~5 ms for a typical schema file).
- Strict mode surfaces existing payload bugs as 500s — the whole point of
  shadow mode is to find these before flipping the flag, not after.

### Out of scope
- **Migrating the ~25 currently-unregistered emitters.** That is the follow-up
  per-PR work the blueprint and `SCALING_PHASES.md` call out. This ADR adds
  only the gating mechanism.
- **Schema versioning policy beyond v1.** Adding `v2` of an event type is a
  separate decision (new file, both validators loaded, emitter chooses which
  version to publish). Documented in `packages/events/README.md`.
- **Consumer-side validation.** `OutboxRelay` and downstream subscribers
  trust the writer's validation today and continue to. If we ever support
  out-of-band writes that bypass `OutboxWriter`, consumers will need their
  own validation pass.
- **Schema registry service** (Confluent-style HTTP registry). Filesystem
  load is sufficient at our scale; revisit if/when we operate multi-process
  schema authoring.

## 5 · Implementation Notes

- `EventValidationError` is exported from `app.core.events`.
- `MissingEventSchema(EventValidationError)` is the schema-not-found subclass
  so callers can distinguish "wrong shape" from "no contract registered".
- Schema file naming convention is **frozen**:
  `<event_type>.v<event_version>.schema.json` under
  `packages/events/schema/v1/`. The loader resolves files by string-format
  only — no introspection of `$id`. This keeps the contract human-greppable.
- Validator instances are cached on `_SchemaRegistry`; `reset_registry_for_tests()`
  is exported for the unit suite.
- Shadow-mode log line uses `event_validation_failed_shadow` (not just
  `_failed`) so log queries can grep for the shadow signal vs. real strict
  failures (which become 500s and surface in error tracking).

## 6 · Rollout Plan

1. Land this PR with flag OFF (shadow mode). Existing emitters unaffected.
2. Watch `event_validation_failed_shadow` counts in dev/staging for 7 days.
3. Migrate the named emitters one PR at a time (separate from this PR).
4. Once the shadow log goes quiet for 7 consecutive days in staging, flip
   `FF_STRICT_EVENT_VALIDATION=true` in canary.
5. Watch error tracking for `EventValidationError`. If quiet for another
   7 days, flip in prod.
6. Sunset 2026-09-01: at sunset we either (a) make strict mode permanent
   and remove the flag, or (b) extend the sunset because not all emitters
   have been migrated. CI fails if neither happens.

## 7 · Validation Criteria

- (✅) `validate_event` returns empty list for a known-good envelope.
- (✅) `validate_event` returns non-empty list for a payload missing a
  required field.
- (✅) `MissingEventSchema` raised for an event type with no schema file
  (only when strict=True).
- (✅) `OutboxWriter.append` in shadow mode logs the violation and STILL
  inserts.
- (✅) `OutboxWriter.append` in strict mode raises `EventValidationError`
  and inserts NOTHING.
- (✅) Existing 4 tests in `test_outbox_writer.py` still pass (additive
  change, not behavioural change at default flag).
- (pending — production canary) `event_validation_failed_shadow` count
  drops to zero over a 7-day window before flipping the flag.

## 8 · Related Work

- ADR-0031 — Multi-provider AI dispatch (`ff_anthropic_provider` flag pattern).
- ADR-0034 — `ai_invocations` flight recorder (`ff_ai_invocations_recorder`
  flag pattern).
- `WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md` §M3 — original requirement.
- `SCALING_PHASES.md` L35 — the ~25 unregistered-emitter migration this
  ADR unblocks.
