# ADR-0031: Multi-provider AI dispatch (Anthropic alongside Gemini)

**Status:** Accepted 2026-05-08
**Date:** 2026-05-08
**Deciders:** @BalaShankar9
**Context tags:** ai-runtime | cost | release

---

## 1 · Context

Today every LLM call in `ai_engine/` ultimately routes through `_GeminiProvider`
in [`ai_engine/client.py`](../../ai_engine/client.py). The cascade in
[`ai_engine/model_router.py`](../../ai_engine/model_router.py) only contains
Gemini SKUs. A full Gemini outage (region-wide quota exhaustion, regional
401 storm, Vertex AI control-plane failure) will burn every retry slot and
fail the generation pipeline with no second-provider seam to fall back to.

Closes **P1-4** (M8 brief in [`docs/architecture/IMPLEMENTATION_MILESTONES.md`](../architecture/IMPLEMENTATION_MILESTONES.md)).
The M8 exit gate explicitly demands a chaos drill where "Gemini full outage
completes a generation end-to-end via Anthropic with no SLO violation".

## 2 · Decision

We will introduce **Anthropic as a second LLM provider** behind the existing
`AIClient` facade. Provider selection is driven by **model name prefix**: any
candidate model whose name starts with `claude-` is dispatched through
`_AnthropicProvider`; everything else continues through `_GeminiProvider`.
The change is additive — zero behaviour change at default flag state.

Specifically:

- New `_AnthropicProvider` class in [`ai_engine/client.py`](../../ai_engine/client.py)
  exposing the same async surface as `_GeminiProvider`: `complete`, `complete_json`,
  `chat`, `stream_completion`, `complete_json_streaming`. Uses the official
  `anthropic` SDK (lazy-imported) wrapped with `asyncio.to_thread` for the
  sync client. Same per-model circuit breaker hook (`_get_model_breaker`) and
  same tenacity retry policy as Gemini.
- New `AIClient._select_provider(model_name) -> Provider` helper that
  dispatches by prefix. AIClient's `complete`/`complete_json`/`chat` cascade
  loops resolve the provider per candidate model rather than always using
  `self._provider`.
- New flag `ff_anthropic_provider` (default OFF, sunset 2026-09-01).
  When OFF, the cascade resolver in `model_router.resolve_cascade` strips any
  `claude-*` entries — so even if a route is mis-configured, no Anthropic call
  is ever attempted at default state.
- Cascade additions (only effective when flag is ON): tier-1 reasoning tasks
  (`reasoning`, `fact_checking`, `quality_doc`, `aim_recon`, `aim_writer`,
  `aim_fix`) gain `claude-3-5-sonnet-20241022` as their final fallback after
  Pro→Flash. No Anthropic primary routes — Gemini stays first for cost.

## 3 · Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| A: Keep Gemini-only and rely on Vertex regional failover | No new dep, no new spend | Doesn't survive a Google-wide quota event; ties M8 exit gate to a single vendor's SRE | Single-provider risk is exactly what P1-4 names |
| B: Adopt LiteLLM / OpenRouter as a unified gateway | One client, many providers | Extra hop, extra failure mode, opaque cost attribution, weakens our retry/circuit-breaker telemetry | Sidecar gateway is overkill for two providers; we already have a clean facade |
| C (chosen): Add `_AnthropicProvider` co-located with `_GeminiProvider`; prefix-based dispatch | Smallest change surface; keeps cascade/cache/breaker logic untouched; flag-gated; trivially extensible to a third provider later | More code in `client.py` (already 1300 lines); an SDK dep | n/a |

## 4 · Consequences

### Positive
- M8 exit gate becomes achievable: cascade can complete a tier-1 generation
  via Anthropic when every Gemini SKU returns 5xx/429.
- Per-model circuit breaker keys naturally extend to Anthropic models without
  code changes (breaker name = `ai_model_<safe_name>`).
- ADR-0034 (`ai_invocations`) gets multi-provider data from day one.

### Negative / cost
- One new dependency: `anthropic>=0.40,<1.0`.
- Anthropic Sonnet input cost is roughly 12× Gemini 2.5 Flash input. Cascade
  ordering keeps it as last-resort only — typical bill impact under steady
  state is zero.
- Cost attribution in `_DailyUsageTracker._estimate_cost_cents` is currently
  Gemini-only; Anthropic calls will under-count until the flight recorder
  (m7-pr30, ADR-0034) lands the per-provider rate table. Acceptable for two
  weeks of forward-only telemetry.

### Neutral / new obligations
- `ANTHROPIC_API_KEY` must be set in the environment when the flag is ON.
- Streaming surface is implemented but the `complete_json_streaming` token-sink
  fast path in `AIClient.complete_json` will still prefer Gemini paths when
  the resolved primary is a Gemini model (status quo).

## 5 · Implementation Plan

- [x] PR: `m7-pr28`
- [x] Feature flag: `ff_anthropic_provider` (default OFF, sunset 2026-09-01)
- [x] Settings: `anthropic_api_key`, `anthropic_default_model`, `anthropic_max_tokens`
- [x] Migration steps: none (additive code; no schema change)
- [x] Rollback plan: flip `ff_anthropic_provider=false`; resolver strips
      `claude-*` from cascades; effectively reverts to status quo
- [x] Observability: existing `ai_call_audit` log line + per-model circuit
      breaker name covers Anthropic by name; new INFO log
      `provider_selected: model=claude-... provider=anthropic`
- [ ] Updates to blueprint section §6.1 (AI runtime) — follow-up doc PR
- [ ] Runbook: `docs/runbooks/ai-provider-failover.md` — m7-pr28b

## 6 · Validation

- [x] Unit tests: `_AnthropicProvider` mocked-SDK round-trip
- [x] Integration test: AIClient.complete dispatches `claude-*` to anthropic
- [x] Chaos test: simulated Gemini quota exhaustion → cascade reaches and
      succeeds via Anthropic
- [ ] (Post-deploy, ≥7 days) Production "Gemini outage" chaos drill green —
      gates M8 exit
- [x] No new P0/P1 risks: default flag OFF, no behaviour change

## 7 · References

- Blueprint section: §6.1 AI runtime
- Related ADRs: ADR-0034 (`ai_invocations`), ADR-0040 (DLQ — prerequisite)
- External docs: <https://docs.anthropic.com/en/api/messages>
