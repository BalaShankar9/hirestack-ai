---
title: AI Context
last_synced: 2026-05-08
watch_paths:
  - ai_engine
  - config/feature_flags.yaml
  - backend/app/services/pipeline_runtime.py
  - backend/app/temporal/workflows
canonical_sources:
  - ai_engine/api.py
  - ai_engine/model_router.py
  - ai_engine/client.py
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#6-ai-runtime-standards
update_when:
  - a new chain is added under ai_engine/chains/
  - a new agent domain is added under ai_engine/agents/
  - the model router policy changes (new provider, new task profile)
  - circuit breaker / retry / throttle parameters change
  - the prompt-versioning hash algorithm changes
  - a new sandbox tier is introduced (L0..L3)
  - cost projection multiplier changes (currently 1.10)
---

# AI Context

> The brain of the system. `ai_engine/` is a **library** consumed by
> backend processes — not a service. It owns model routing, retries,
> breakers, prompt versioning, RAG, agents, chains, tools, evals, and the
> AI flight recorder.

---

## TL;DR — 14 lines

1. **`ai_engine/` is library-only.** Public surface is
   [`ai_engine/api.py`](../ai_engine/api.py): `run_stage()`, `run_chain()`,
   `run_pipeline()`. `ai_engine` MAY NOT import from `backend.app` —
   enforced by `import-linter`.
2. **Default model: `gemini-2.5-pro` (Google).** Failover: Anthropic
   Claude (Sonnet/Opus tier per task) when `ff_anthropic_provider` is on
   (P1-4 SHIPPED — m7-pr28). Single-provider dependency in production is
   forbidden (blueprint §17).
3. **Model router** (`ai_engine/model_router.py`) selects provider × model
   per call by: task profile (drafting / scoring / classifying / parsing),
   input size, budget signal, provider health (CB state), feature flag.
4. **Circuit breaker:** 5 failures / 60s opens; half-open after 30s.
   Throttle: `GEMINI_MIN_INTERVAL_MS=100` between requests per worker.
   Retry: 6 attempts / 120s with jitter.
5. **The pipeline has 7 phases:** Recon → Atlas → Cipher → Quill → Forge →
   Sentinel → Nova. See [BUSINESS_LOGIC_CONTEXT.md](BUSINESS_LOGIC_CONTEXT.md)
   for what each does. Each phase is one or more agents and chains.
6. **Three execution paths** (BACKEND_CONTEXT §pipeline_runtime): Temporal
   (canonical) → Redis Streams (fallback) → in-process asyncio (gated by
   `ff_inprocess_fallback`, default OFF in prod).
7. **Per-stage Temporal activities** (P1-1 SHIPPED — m8-pr32): each phase
   is a separate activity. Crash mid-pipeline resumes from last green
   stage; tokens already burned are not re-burned.
8. **Tools execute in tiered sandboxes** L0–L3. The LLM never invokes a
   tool — orchestrator validates against allowlist, schema, and capability
   token. See [AUTH_SECURITY_CONTEXT.md](AUTH_SECURITY_CONTEXT.md).
9. **`ai_invocations` is the flight recorder.** One row per model call,
   no exceptions. Partitioned monthly, 84-month retention. Powers cost
   attribution, eval regression, and incident forensics.
10. **Prompt versioning:** every prompt template lives in
    `ai_engine/prompts/<name>.v<n>.txt`. The runtime hashes the template
    text and stores the hash in `ai_invocations.prompt_version`. Eval
    regressions are tied to prompt-version diffs.
11. **Prompt cache** is two-tier: in-process LRU (per worker) + Redis
    (cross-worker). Hit rate is a tracked metric. Saves on stable prompts
    (deterministic system prompts; identical user inputs).
12. **Cost projection × 1.10 safety margin.** Pre-flight projector
    estimates cost; multiplied by 1.10; checked against the org's
    remaining budget by `usage_guard` before the call.
13. **Evidence ledger** classifies every claim as VERBATIM > DERIVED >
    INFERRED > USER_STATED. Tier ordering is **load-bearing** — Sentinel
    rejects DERIVED claims that do not trace to a VERBATIM source.
14. **Eval gate.** A nightly `EvalRegressionWorkflow` re-runs gold sets;
    a regression past threshold creates a Linear ticket and pages the
    on-call.

---

## Public surface (`ai_engine/api.py`)

```python
async def run_stage(phase: PipelinePhase, brief: ApplicationBrief,
                    previous_outputs: dict, *, emitter: AgenticEventEmitter,
                    capability_token: CapabilityToken) -> StageResult:
    ...

async def run_chain(name: str, inputs: dict, *, ...) -> ChainResult: ...

async def run_pipeline(brief: ApplicationBrief, *, ...) -> PipelineResult: ...
```

These are the **only** functions backend code is allowed to call. Anything
else (`ai_engine.agents.drafter`, `ai_engine.chains.role_profiler`) is
internal — consumers cross-cut via this surface.

`import-linter` contract:

```toml
[tool.importlinter.contracts.ai-engine-public-surface]
type = "forbidden"
source_modules = ["backend.app"]
forbidden_modules = ["ai_engine.agents", "ai_engine.chains", "ai_engine.tools"]
ignore_imports = ["backend.app -> ai_engine.api"]
```

---

## Chains (25 total)

`ai_engine/chains/` — composable units that take inputs and produce a
typed artifact. Each chain is a class with `async def run(inputs) ->
ChainResult`.

Highlights (full inventory in `ai_engine/chains/`):

| Chain | Output | Used in phase |
|---|---|---|
| `RoleProfilerChain` | `RoleProfile` (skills, seniority, must-haves) | Recon |
| `CompanyIntelChain` | `CompanyIntel` (mission, values, recent news) | Recon |
| `DiscoveryChain` | `DiscoveryNotes` (open questions for the user) | Recon |
| `BenchmarkChain` | `Benchmark` (gold-standard CV/cover for this role) | Atlas |
| `GapAnalyzerChain` | `GapAnalysis` (deltas: candidate vs benchmark) | Cipher |
| `EvidenceLedgerChain` | classified evidence items | Cipher |
| `DocGeneratorChain` | `DocumentDraft` (CV / cover / portfolio) | Quill |
| `ATSScannerChain` | `ATSResult` (score + recommendations) | Sentinel |
| `CritiqueChain` | `CritiqueReport` (factual + style) | Sentinel |
| `AssemblyChain` | `Application` (final bundle) | Nova |
| ...20+ more | | |

Each chain declares its preferred model profile (e.g. `drafting`,
`scoring`); the model router maps profile → concrete model per provider.

---

## Agents (30+)

`ai_engine/agents/` — stateful primitives + per-domain agents.

Primitives at root:

- `BaseAgent` (interface)
- `Drafter`, `Critic`, `FactChecker`, `Optimizer`, `Eval`
- `EvidenceGraph`, `Memory`, `Lock`, `Multi-Pipeline`
- `BuildPlanner` (assembles per-application plan)
- `AgenticEventEmitter` (SSE event source)

Domain folders:

- `aim/` — Application Intelligence Module agents (RAG-backed insights)
- `culture_fit/` — culture-fit scoring
- `interview_sim/` — interview simulator turn engine
- `linkedin/` — LinkedIn profile/post agents
- `networking/` — outreach / cold-message agents
- `orchestration/` — phase orchestrators (Recon, Atlas, ...)
- `portfolio/` — portfolio asset agents
- `ppt/` — slide-deck agents
- `salary/` — salary coach agents

---

## The 7-phase pipeline

```
Recon   -> Atlas   -> Cipher  -> Quill    -> Forge   -> Sentinel -> Nova
profile     bench-     gap +      draft       portfolio  quality   assemble
+ intel     marks      evidence   docs        + extras   gates     output
```

| Phase | Done by | Output |
|---|---|---|
| **Recon** | RoleProfiler, CompanyIntel, Discovery | role profile + company intel |
| **Atlas** | Benchmark | benchmark target |
| **Cipher** | GapAnalyzer, EvidenceLedger | gap analysis + evidence items |
| **Quill** | DocGenerator (CV, cover, statement) | document drafts |
| **Forge** | Portfolio, PPT, LinkedIn helpers | optional assets |
| **Sentinel** | Critic, FactChecker, ATSScanner | quality report; can hard-fail |
| **Nova** | Assembly | final bundle persisted to document_library |

Each phase emits `stage.started`, `stage.token` (when streaming), and
`stage.completed` events. Sentinel can emit `stage.failed` which short-
circuits Nova.

`ff_strict_critic_gate=true` makes Sentinel a hard gate (rejects
generation on factual failure); `false` reports the failure but lets Nova
assemble.

---

## Model router

`ai_engine/model_router.py`:

```python
class TaskProfile(StrEnum):
    DRAFT = "draft"            # long-form generation
    SCORE = "score"            # numeric / classification
    CLASSIFY = "classify"      # short label
    PARSE = "parse"            # structured extraction
    SUMMARIZE = "summarize"
    REASON = "reason"          # multi-step

def choose(profile, *, input_tokens, budget_remaining_cents, ff_anthropic_provider, breaker_state) -> ModelChoice:
    ...
```

Default policy:

| Profile | Primary | Fallback (if breaker open or `ff_anthropic_provider`) |
|---|---|---|
| `DRAFT` | `gemini-2.5-pro` | `claude-3-5-sonnet` |
| `REASON` | `gemini-2.5-pro` | `claude-3-opus` |
| `PARSE` | `gemini-2.5-flash` | `claude-3-haiku` |
| `CLASSIFY` | `gemini-2.5-flash` | `claude-3-haiku` |
| `SCORE` | `gemini-2.5-flash` | `claude-3-haiku` |
| `SUMMARIZE` | `gemini-2.5-flash` | `claude-3-haiku` |

The router emits `ai.model.choice` trace attributes so per-call provider
selection is visible.

---

## Reliability primitives

- **Circuit breaker** (`ai_engine/client.py`): 5 failures in 60s opens;
  half-open after 30s; close on first success. Per-provider state
  (Gemini, Anthropic).
- **Retry**: 6 attempts within 120s with exponential jitter. Idempotent
  by design — duplicate completions are tolerated.
- **Throttle**: `GEMINI_MIN_INTERVAL_MS=100` between requests **per
  worker**. Anthropic uses provider-side rate limits.
- **Degraded mode**: when both primary + fallback are open, the router
  returns a `ProviderUnavailable` exception which surfaces as 503
  `pipeline.unavailable`. The frontend Mission-Control UI shows a
  graceful "service degraded" panel.

---

## Prompt management

`ai_engine/prompts/<name>.v<n>.txt` (or `.j2` for Jinja). Loader:

```python
prompt = load_prompt("role_profiler", v=3)
hash = sha256(prompt.encode()).hexdigest()[:12]
```

The hash is stored on every `ai_invocations` row as `prompt_version`.
When eval regression detects a quality drop, the diff is `prompt_version
A vs B` — root cause is one prompt change.

Prompts MUST be committed; never inlined into Python source. Templates
that interpolate user input MUST go through `wrap_user_input()` (see
[AUTH_SECURITY_CONTEXT.md](AUTH_SECURITY_CONTEXT.md)).

---

## Prompt cache

Two-tier (`ai_engine/cache.py`):

1. **In-process LRU** (per worker), TTL 10 min, max 1024 entries.
2. **Redis** keyed by `(model, prompt_hash, sha256(input))`, TTL 24h.

Hit rate metric: `ai.cache.hit_rate{tier=lru|redis}`. Tracked because
prompt cache is one of two cost-saving levers (the other is dynamic model
selection).

Disabled per-call via `cache=False` for stochastic chains where cache
defeats the purpose (e.g. variant generation in A/B Lab).

---

## Cost projection (× 1.10 safety margin)

```python
def project_cost(model, input_tokens, expected_output_tokens) -> Cents:
    return ceil(model.unit_cost(input_tokens, expected_output_tokens) * 1.10)
```

Every call is projected pre-flight. `usage_guard` checks projected cost
against remaining budget; calls that would exceed are rejected with
`billing.cap_exceeded`. The 1.10 multiplier covers retries and tail
output growth.

After the call, the actual cost is written to
`ai_invocations.cost_cents` (from provider response). The hourly rollup
to `org_cost_hourly` (via `pg_cron`) feeds the next request's check.

---

## `ai_invocations` flight recorder

Schema (simplified):

```sql
CREATE TABLE ai_invocations (
  id uuid PRIMARY KEY,
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  job_id uuid,
  phase text NOT NULL,
  chain text,
  agent text,
  provider text NOT NULL,
  model text NOT NULL,
  prompt_version text NOT NULL,        -- hash of template text
  input_tokens int NOT NULL,
  output_tokens int NOT NULL,
  cost_cents int NOT NULL,
  latency_ms int NOT NULL,
  cache_hit bool NOT NULL,
  status text NOT NULL,                -- ok | error | degraded
  trace_id text,
  span_id text,
  langfuse_trace_id text,
  created_at timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);     -- monthly via pg_partman
```

Powers:

- per-org cost attribution (P1-8)
- eval regression triage
- incident forensics ("which prompt-version was active when this drop
  happened?")
- model-A/B comparison

Retention: **84 months online** (compliance). Older partitions exported
to S3 Parquet via `EventArchiveWorkflow`.

---

## Tool registry

`ai_engine/registry/`:

- `dispatcher.py` — receives a structured tool request from the
  orchestrator; validates allowlist + schema + capability token; resolves
  via `RESOLVERS` allowlist; routes by `sandbox_tier`.
- `resolvers.py` — `RESOLVERS = {"company_lookup": company_lookup_tool,
  "rag_query": rag_query_tool, ...}`. New tools must be registered here.
- `schemas/` — JSON Schema for each tool's input + output.

Adding a tool requires:

1. Implementation under `ai_engine/tools/<tool>.py`.
2. Schema under `ai_engine/registry/schemas/<tool>.json`.
3. Entry in `RESOLVERS` (`ai_engine/registry/resolvers.py`).
4. Row in `ai_tools` table with `name, sandbox_tier, schema, version,
   owner_team`.
5. Test under `ai_engine/tests/tools/test_<tool>.py`.

---

## RAG (`ai_engine/rag/`)

- Embeddings: text-embedding-3-large (OpenAI) or Gemini embeddings (model
  router decides).
- Storage: pgvector tables alongside relational data
  (e.g. `aim_source_embeddings`).
- Retrieval: cosine similarity, top-k, with provenance attached
  (chunk id, source url, span).
- Provenance is **mandatory**: every retrieved chunk travels with its
  source so post-output guard can verify claims.

AIM module backfills source embeddings via
[`scripts/backfill_aim_source_embeddings.py`](../scripts/backfill_aim_source_embeddings.py).

---

## Evals (`ai_engine/evals/`)

- Gold sets per chain: input + expected output.
- Nightly `EvalRegressionWorkflow` re-runs every chain; compares to a
  baseline; if quality (rouge / model-judge) drops past threshold, opens
  a ticket and pages.
- Per-PR eval gate: chains touched in the PR re-run their gold set; a
  regression past threshold blocks merge.

---

## Observability (`ai_engine/observability/`)

- OTEL spans wrap every chain and every model call.
- Langfuse traces tag every model call with prompt-version, retrieved
  chunks, output, scores.
- Span attributes include: `ai.provider`, `ai.model`, `ai.prompt_version`,
  `ai.cache_hit`, `ai.cost_cents`, `pipeline.execution.path`,
  `chain.name`, `agent.name`.

---

## What "good AI code" looks like in this repo

- [ ] Calls go through `ai_engine.api`, not directly into agents/chains.
- [ ] Prompt is in `ai_engine/prompts/<name>.v<n>.txt`, not inline.
- [ ] Model selection via `model_router`, not hard-coded.
- [ ] Cost projection × 1.10 happens before the call.
- [ ] `ai_invocations` row written (no exceptions).
- [ ] Tool calls go through the registry; capability token signed by
      orchestrator; sandbox tier set on the `ai_tools` row.
- [ ] User input wrapped via `wrap_user_input()`.
- [ ] Provenance carried with retrieved chunks.
- [ ] OTEL span + Langfuse trace emitted.
- [ ] Eval gold set updated if behavior intentionally shifts.
