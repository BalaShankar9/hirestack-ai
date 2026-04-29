# ADR-0011 — Mobile (Android) Contract Surface

**Date:** 2026-04-21
**Status:** Accepted
**Squad:** S9 — Mobile (Android Kotlin)

## Context

The Android client (`mobile/android/`, Compose + Hilt + Retrofit +
Moshi + Supabase GoTrue, 13 629 LOC across 68 Kotlin files) shipped
without any unit test coverage. Network plumbing — bearer auth,
retries, SSE event parsing, JSON wire shapes — is the layer most
likely to silently desync from the backend during routine API
evolution and should never have to be diagnosed first via a crash
report from a beta tester.

S9 stands up the JVM unit-test source set
(`app/src/test/java/...`) and pins the network contract surface.

## Decision

The following Android contracts are now pinned and **must not
change without an updated ADR + test update**.

### `data/network/RetryInterceptor.kt` (R1)

- `maxAttempts = 3`; `backoffMs = [0, 400, 1200]`.
- Idempotent verbs (`GET`, `HEAD`) are retried on:
  - `IOException`
  - HTTP `502`, `503`, `504`
- Non-idempotent verbs (`POST`, `PUT`, `PATCH`, `DELETE`) are
  NEVER retried (replay protection for partially-applied writes).
- HTTP `500` is NOT retryable.
- HTTP `4xx` is terminal (returned unchanged).
- On exhausted retries: returns the LAST 5xx response (callers see
  the real status, not a forged 200) or re-throws the LAST
  IOException.

### `data/network/AuthInterceptor.kt` (R2)

- Always sets `Accept: application/json` (via `addHeader`, so a
  caller-supplied Accept survives alongside).
- Sets `Authorization: Bearer <token>` only when
  `TokenStore.snapshotAccess()` returns non-null.
- Empty-string token is wrapped as `Bearer ` (which OkHttp trims to
  `Bearer` on the wire). Pinned to make a future "guard against
  blank" change intentional.
- Preserves request method, URL (incl. query string), body, and any
  caller-supplied headers (`X-Trace-Id`, `X-Custom`, etc.).

### `data/network/PipelineSse.PipelineEvent.from` (R4)

Extracted from the inline SSE callback into a pure factory
`PipelineEvent.from(type: String?, parsed: Map<*,*>?)`.

- `name` defaults to `"message"` when SSE `event:` type is null.
- `progress` accepts any `Number` (Int/Long/Double) and coerces via
  `toInt()` (truncation, not rounding); null when missing or
  non-numeric.
- `agent` prefers key `agent`; falls back to `agent_name`; null
  when both missing or value is non-string. (Pinned because the
  backend uses both spellings depending on the emitter.)
- `phase` / `stage` / `status` / `message`: String only; non-string
  values silently dropped.
- `raw` echoes the parsed map verbatim (`assertSame`-equal) so
  callers can read fields not promoted into the typed envelope.

### `data/network/ParityModels.kt` & `Models.kt` (R5)

Wire shape pinned via Moshi-generated adapter golden tests.

- `Application`: `id` required; all other fields optional with
  `null` defaults; snake_case throughout EXCEPT
  `Application.modules.<key>.updatedAt` which is camelCase
  (backend contract). Unknown fields ignored silently.
- `Application.scores`: `ScoresShape` with `overall`, `keyword`,
  `readability`, `structure`, `ats` as Double, `topFix` as String.
- `Application.confirmed_facts`: `ConfirmedFacts`.
- `GenerationJob`: snake_case throughout; uses `current_agent`.
- `GenerationJobEvent`: snake_case; uses `agent_name` (pinned
  because the parallel job payload uses `current_agent` — both
  spellings must remain stable).
- `CreateGenerationJobRequest`: snake_case wire shape;
  `requested_modules` defaults to `emptyList()` when omitted on
  parse.
- `ResumeParseResponse`: camelCase `fileName` / `contentType`
  (parse-resume endpoint contract).
- `GenerationJob` round-trips through `toJson` + `fromJson` with
  no loss.

## Out of scope (deferred)

- **R3 — `TokenStore.kt`:** DataStore key constants would need
  Robolectric or instrumentation to test the actual persistence
  cycle. Constants are stable in practice; revisit when Robolectric
  is wired up for Compose previews.
- **ViewModel coroutines tests:** large surface and ViewModel
  behaviour is largely Compose-driven; not a contract pin but a
  behavioural-coverage task. Owned by the future Mobile-UX squad.
- **Compose UI tests, screenshot tests, Play-Store hardening,
  R8 enabling, signing config:** owned by S10 Infra & Deploy and
  the future Mobile-Release squad.
- **Ktor / Supabase GoTrue client wrappers:** thin adapters with
  no logic; not a maintenance risk.

## Consequences

- **Positive:** `RetryInterceptor`, `AuthInterceptor`,
  `PipelineEvent.from`, and the Moshi wire shapes are now pinned
  by deterministic JUnit cases. A regression flips the suite RED
  at `./gradlew :app:testDebugUnitTest`.
- **Positive:** JVM test source set is bootstrapped with `mockk`
  (1.13.13) and `kotlinx-coroutines-test` (1.9.0) — future S9
  follow-up work has the deps it needs.
- **Positive:** `PipelineEvent.from` is now reusable outside the
  SSE callback (e.g. for replay tests or alternate transports).
- **Negative:** Tests are coupled to current implementation
  invariants. Intentional behaviour changes require both an ADR
  amendment and test updates.
- **Negative:** First gradle run is ~1m 22s (cold KSP + Hilt
  compile); subsequent incremental runs ~10–15 s. Mitigated by
  daemon caching.
