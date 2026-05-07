# S9 — Mobile (Android Kotlin) — Sign-off

**Date:** 2026-04-21
**Lead:** autonomous loop
**Status:** ✅ COMPLETE
**Reference:** [`0011-mobile-android-contract-surface.md`](../adrs/0011-mobile-android-contract-surface.md)

## Scope delivered

| Risk | Surface | Action | Tests added |
| --- | --- | --- | --- |
| R1 | `data/network/RetryInterceptor.kt` (57 LOC) | Pinned backoff math + idempotency gate | 12 |
| R2 | `data/network/AuthInterceptor.kt` (26 LOC) | Pinned bearer-token injection + Accept header | 7 |
| R4 | `data/network/PipelineSse.kt` event-shape parser | Extracted `PipelineEvent.from` + pinned mapping | 15 |
| R5 | `data/network/ParityModels.kt` + `Models.kt` | Pinned Moshi wire shapes (Application, GenerationJob, ResumeParseResponse, …) | 11 |

**Total new tests:** 45.
**Total new test LOC:** ~790.
**mobile/android suite:** 0 → 45 passed.
**Wall time:** ~6.9 s (incremental); ~1 m 22 s cold gradle build.

## Production code touched

- `mobile/android/app/build.gradle.kts`: added
  `testImplementation("io.mockk:mockk:1.13.13")` and
  `testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")`.
- `mobile/android/app/src/main/java/.../PipelineSse.kt`: extracted
  the inline JSON-map → typed-event mapping in `onEvent` into a
  pure `PipelineEvent.from(type, parsed)` factory in the
  `PipelineEvent` companion object. Byte-for-byte equivalent
  behaviour (verified by line-diff of the field assignments).

No other production code was modified.

## Out of scope (deferred with rationale)

- **R3 — `TokenStore.kt` (DataStore keys):** requires Robolectric
  or instrumentation; not a contract pin but a persistence test.
  Defer to whichever future squad wires Robolectric for Compose
  preview tests.
- **ViewModel coroutines tests:** large surface; Compose-driven;
  owned by Mobile-UX squad.
- **Compose UI / screenshot tests, Play-Store hardening, R8
  enabling, signing config:** owned by S10 Infra & Deploy and the
  future Mobile-Release squad.

## Commits (LOCAL on `main`)

| SHA | Title |
| --- | --- |
| `f4fd002` | S9-F0: mobile (Android) audit + R1-R6 risk register |
| `ae5ee64` | S9-F1: pin RetryInterceptor contracts (R1) |
| `e708714` | S9-F2: pin AuthInterceptor contracts (R2) |
| `d325721` | S9-F3: extract PipelineEvent.from + pin SSE event shape (R4) |
| `7450dd2` | S9-F4: pin Moshi adapter wire shapes (R5) |
| _next_ | S9-F5: ADR-0011 + sign-off |

All commits remain LOCAL until the S10 staging gate.

## Verification gate

- `cd mobile/android && ./gradlew :app:testDebugUnitTest` → 45
  passed in 6.9 s (incremental).
- Backend suite untouched (1715 / 8.12 s baseline).
- Frontend suite untouched (335 / 7.72 s baseline).

## Next

**S10 — Infra & Deploy.** Audit `infra/`, `docker-compose.yml`,
`netlify.toml`, `railway.toml`, `Procfile`, `Dockerfile`s, the
GitHub Actions / Netlify pipelines, and the staging-gate plan.
