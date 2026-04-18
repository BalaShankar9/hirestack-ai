# HireStack AI — AI Engine & Generation Pipeline Audit

> **Date:** 2025-07-18 · **Scope:** Read-only architectural audit  
> **Purpose:** Inform redesign — exhaustive mapping of every model call, cost center, parallelism opportunity, and architectural constraint.

---

## Table of Contents

1. [Model Usage & Routing](#1-model-usage--routing)
2. [Agent Architecture](#2-agent-architecture)
3. [Chain Architecture](#3-chain-architecture)
4. [Generation Pipeline Flow](#4-generation-pipeline-flow)
5. [Caching Analysis](#5-caching-analysis)
6. [Cost Hotspots](#6-cost-hotspots)
7. [Parallelism Analysis](#7-parallelism-analysis)
8. [Summary Table of ALL Model Calls](#8-summary-table-of-all-model-calls)
9. [Redesign Risks & Recommendations](#9-redesign-risks--recommendations)

---

## 1. Model Usage & Routing

### Provider

**Google Gemini** is the sole AI backend, accessed via `google.genai` SDK. Supports both API-key and Vertex AI auth modes.

### Models Deployed

| Model | Role | Cost (per 1M tokens in/out) |
|-------|------|-----------------------------|
| `gemini-2.5-pro` | Reasoning, research, fact checking, structured output, optimization, quality docs, general | $1.25 / $5.00 |
| `gemini-2.5-flash` | Creative, drafting, critique, synthesis, validation | $0.075 / $0.30 |
| `gemini-2.0-flash` | Fast doc generation | $0.075 / $0.30 |

### Task-Type Routing (`ai_engine/model_router.py`)

14 task types are mapped to models. Cascade fallback lists are defined per task type (e.g., `reasoning` → Pro → Flash → 2.0-Flash).

| task_type | Primary Model | Cascade |
|-----------|--------------|---------|
| reasoning | gemini-2.5-pro | pro → flash → 2.0-flash |
| research | gemini-2.5-pro | pro → flash |
| fact_checking | gemini-2.5-pro | pro → flash |
| structured_output | gemini-2.5-pro | pro → flash → 2.0-flash |
| optimization | gemini-2.5-pro | pro → flash |
| quality_doc | gemini-2.5-pro | pro → flash |
| general | gemini-2.5-pro | pro → flash → 2.0-flash |
| creative | gemini-2.5-flash | flash → pro |
| drafting | gemini-2.5-flash | flash → 2.0-flash → pro |
| critique | gemini-2.5-flash | flash → pro |
| synthesis | gemini-2.5-flash | flash → pro |
| validation | gemini-2.5-flash | flash → pro |
| fast_doc | gemini-2.0-flash | 2.0-flash → flash |
| (default) | gemini-2.5-flash | flash → pro → 2.0-flash |

**Override mechanism:** `MODEL_ROUTES` and `MODEL_CASCADE` env vars (JSON).

### Health Tracking

Per-model circuit breaker: 3 failures → 120s unhealthy window. Cascade skips unhealthy models. Separate circuit breakers in `app.core.circuit_breaker` (5 failures → 60s recovery).

### Retry Policy

Tenacity-based: 6 attempts OR 120s max, exponential backoff 2–30s. Skips auth/permission errors.

### Budget Enforcement

`_DailyUsageTracker` tracks tokens per model per day. `BudgetExceededError` raised when daily budget hit.

---

## 2. Agent Architecture

### Framework

Custom 5-stage agentic pipeline (not LangChain/CrewAI). Implemented in `ai_engine/agents/`.

### Pipeline Stages

```
Research → Draft → [Critic ∥ Optimizer ∥ FactChecker] → Revision Loop → Validator
           ↑_______________________________________________|
                    (if needs_revision, max N iterations)
```

### Core Agents

| Agent | File | LLM Call | task_type | temp | max_tokens | Key Behavior |
|-------|------|----------|-----------|------|------------|--------------|
| **ResearcherAgent** | `researcher.py` | `complete_json()` | varies | — | — | 3 depth modes (QUICK/THOROUGH/EXHAUSTIVE). Deterministic tools first (parse_jd ∥ extract_profile_evidence ∥ keyword_overlap), then optional web search. LLM used for tool-step planning. |
| **DrafterAgent** | `drafter.py` | Delegates to chain | — | — | — | `run()` delegates to chain (e.g., `generate_tailored_cv()`). `revise()` calls `complete_json()` with structured revision prompt. |
| **CriticAgent** | `critic.py` | `complete_json()` | critique | 0.3 | 2048 | 4-dimension rubric (impact, clarity, tone_match, completeness, 0–100 each). Per-pipeline threshold calibration. Deterministic revision decision — not LLM opinion. |
| **OptimizerAgent** | `optimizer.py` | `complete_json()` | optimization | 0.3 | 3000 | Deterministic tools first (keyword_overlap, readability). LLM synthesizes constrained rewrite suggestions. Deterministic scores NEVER overridden by LLM. |
| **FactCheckerAgent** | `fact_checker.py` | `complete_json()` | fact_checking | 0.2 | 4000 | 4-tier classification: verified/inferred/embellished/fabricated. Deterministic claim-evidence matching first (≥0.80 confidence auto-verified). LLM only adjudicates ambiguous claims. Target: fabrication recall ≥0.90. |
| **ValidatorAgent** | `validator.py` | `complete_json()` | validation | — | — | Quality checks on generated documents vs source data. Checks accuracy, fabrication, consistency, professionalism, completeness, grammar. |

### Orchestrator (`orchestrator.py`)

`AgentPipeline` class:
- **Policy-driven:** `PipelinePolicy` controls which stages to skip, confidence thresholds, cost budgets, iteration limits, human-in-the-loop gates.
- **Pre-built policies:** `POLICY_FULL`, `POLICY_LIGHT`, `POLICY_STRICT` + 14 per-pipeline-name policies.
- **AdaptivePolicyTracker:** Rolling quality window — adjusts confidence_threshold ±0.03–0.05 automatically.
- **Durable execution:** `WorkflowEventStore` with event-sourced checkpoints. Resume from checkpoint supported.
- **Evidence ledger:** Flows through all stages — populated by researcher, cited by drafter, enforced by fact-checker/validator.
- **Contract validation:** TypedDict-style contracts enforced at stage boundaries (`contracts.py`).

### Sub-Agents (20+ files in `sub_agents/`)

| Domain | Sub-Agents |
|--------|------------|
| **Interview** | InterviewCoordinator (5-agent swarm) |
| **Career** | CareerCoordinator (5-agent swarm) |
| **Salary** | SalaryCoordinator (5-agent swarm) |
| **LinkedIn** | LinkedInCoordinator (5-agent swarm) |
| **Company Intel** | IntelCoordinator (7-agent swarm): WebsiteIntel, GitHubIntel, CareersIntel, JDIntel, MarketPosition, CompanyProfile, ApplicationStrategy |
| **Gap Analysis** | JDAnalystSubAgent, CompanyIntelSubAgent, ProfileMatchSubAgent, MarketIntelSubAgent, HistorySubAgent |
| **Optimizer** | ATSOptimizerSubAgent, ReadabilityOptimizerSubAgent |
| **Critic** | CriticSpecialists |
| **FactChecker** | FactCheckerSpecialists |
| **Misc** | ToneCalibratorSubAgent, KeywordStrategistSubAgent, SectionDrafterSubAgent |

**Pattern:** Every v2 chain delegates to its sub-agent coordinator, with automatic fallback to legacy single-LLM on failure.

### Tool System (`tools.py`)

`ToolRegistry` with `AgentTool` dataclass. Agents call deterministic tools in a loop before LLM synthesis. Tools include:
- `parse_jd`, `extract_profile_evidence`, `compute_keyword_overlap`, `compute_readability`
- `extract_claims`, `match_claims_to_evidence`
- Web search tools (for THOROUGH/EXHAUSTIVE research depth)
- `select_and_execute()` — LLM-driven tool selection for autonomous planning

---

## 3. Chain Architecture

### Chain Registry (20 chains in `ai_engine/chains/`)

| Chain | File | LLM Calls | task_type(s) | Key Notes |
|-------|------|-----------|-------------|-----------|
| **RoleProfilerChain** | `role_profiler.py` | 1× `complete_json()` | structured_output | Massive system prompt (~200 lines). Full Gemini schema for structured output. |
| **DocumentGeneratorChain** | `document_generator.py` | 1× per doc type via `complete()` | drafting | 4 tailored variants (CV/CL/PS/Portfolio) + 4 legacy variants. Prompts include full JD + profile + resume + gap analysis. **LARGEST PROMPTS IN SYSTEM.** |
| **BenchmarkBuilderChain** | `benchmark_builder.py` | 1× profile + 1× per artifact | structured_output / drafting | Ideal profile, then ideal CV/CL/portfolio/case studies/action plan. Up to 6 LLM calls per invocation. |
| **GapAnalyzerChain** | `gap_analyzer.py` | 1× `complete_json()` | reasoning | Large schema (~200 lines). Compares candidate vs benchmark. |
| **ATSScannerChain** | `ats_scanner.py` | 3× `complete_json()` | structured_output × 2 + reasoning | Pass 1: Keywords, Pass 2: Structure, Pass 3: Strategy. **3 sequential LLM calls per scan.** |
| **InterviewSimulatorChain** | `interview_simulator.py` | 1–2× `complete_json()` | creative + reasoning | v2: delegates to 5-agent swarm. Fallback: legacy single LLM. Evaluate answer is always direct LLM. |
| **CareerConsultantChain** | `career_consultant.py` | 1× `complete_json()` | reasoning | v2: delegates to 5-agent swarm. 12-week roadmap generation. |
| **SalaryCoachChain** | `salary_coach.py` | 1× `complete_json()` | reasoning | v2: delegates to 5-agent swarm. Market analysis + negotiation strategy. |
| **CompanyIntelChain** | `company_intel.py` | 7+ sub-agent calls | reasoning | v2: IntelCoordinator with 7 sub-agents. JD-only fallback on failure. |
| **LinkedInAdvisorChain** | `linkedin_advisor.py` | 1× `complete_json()` | creative | v2: delegates to 5-agent swarm. Profile optimization suggestions. |
| **DailyBriefingChain** | `daily_briefing.py` | 1× `complete_json()` | creative | Small prompt, 500 max_tokens. Low cost. |
| **LearningChallengeChain** | `learning_challenge.py` | 1× `complete_json()` | creative | Skill-building exercises with schema. |
| **ValidatorChain** | `validator.py` | 1× `complete_json()` | validation | Document + analysis validation. |
| **AdaptiveDocumentChain** | `adaptive_document.py` | 1× `complete()` | drafting/fast_doc | 35+ document type system prompts. Used for extra/required docs from doc pack plan. |
| **DocumentVariantChain** | `doc_variant.py` | 1× per variant | drafting | Tone/style variants of existing documents. |
| **MarketIntelligenceChain** | `market_intelligence.py` | 1× `complete_json()` | reasoning | Market analysis for job seekers. |
| **ApplicationCoachChain** | `application_coach.py` | 1× `complete_json()` | reasoning | Application strategy advice. |
| **DocumentDiscoveryChain** | `document_discovery.py` | 1× `complete_json()` | reasoning | Discovers which documents a JD requires. |
| **DocumentPackPlanner** | `document_pack_planner.py` | 1× `complete_json()` | reasoning | Plans optimal document set for application. |
| **UniversalDocGeneratorChain** | `universal_doc_generator.py` | 1× `complete()` | drafting | Generic document generation. |

### v2 Pattern

All v2 chains follow the same pattern:
1. Import sub-agent coordinator
2. Try coordinator swarm
3. On failure, fallback to `_legacy_*()` single-LLM method
4. Validate result with `_validate_result()`

---

## 4. Generation Pipeline Flow

### Entry Points

| Route | File | Mode |
|-------|------|------|
| `POST /pipeline/stream` | `generate/stream.py` | SSE streaming |
| `POST /generate/jobs` | `generate/jobs.py` | Background job (DB-backed) |
| Sync (via PipelineRuntime) | `pipeline_runtime.py` | Sync with CollectorSink |

### PipelineRuntime — Canonical Execution Engine

All 3 modes (sync/stream/job) use `PipelineRuntime` with pluggable `EventSink`:
- `NullSink` — sync mode
- `SSESink` — streaming mode
- `DatabaseSink` — job mode (persists events + updates `generation_jobs` row)
- `CollectorSink` — testing

### Pipeline Phases (7 named phases)

```
Phase 0: RECON    — Company intelligence gathering (CompanyIntelChain → 7 sub-agents)
                    30s timeout, best-effort, parallel-ready
                    SLO: 8,000ms

Phase 1: ATLAS    — Resume parsing (ResearcherAgent pipeline)
                    + Benchmark building (BenchmarkBuilderChain pipeline)
                    + Benchmark CV (async task, overlaps with gap analysis)
                    + Document pack planning (async task, overlaps with gap analysis)
                    SLO: 12,000ms

Phase 2: CIPHER   — Gap analysis (GapAnalyzerChain pipeline)
                    + Evidence graph canonicalization
                    + Plan artifact generation
                    + Await doc pack plan + benchmark CV from Phase 1
                    SLO: 10,000ms

Phase 3: QUILL    — CV pipeline ∥ Cover Letter pipeline ∥ Career Roadmap
                    (all three run in PARALLEL via asyncio.gather)
                    SLO: 20,000ms

Phase 4: FORGE    — Personal Statement pipeline ∥ Portfolio pipeline
                    (parallel via asyncio.gather)
                    + Extra required docs from doc pack plan
                    (batched in pairs via AdaptiveDocumentChain)
                    + Benchmark versions of required docs
                    SLO: 15,000ms

Phase 5: SENTINEL — Validation (quality scores, fact-check reports)
                    SLO: 5,000ms

Phase 6: NOVA     — Format final response + persist to document_library
                    SLO: 2,000ms
```

### Per-Document Agent Pipeline (within Phases 3–4)

Each document (CV, CL, PS, Portfolio) runs a full agent pipeline:

```
Research (policy-gated) → Draft → [Critic ∥ Optimizer ∥ FactChecker] → Revision → Validate
```

With default policies, this means each document may get 1–3 revision iterations.

### Data Flow

```
JD Text + Resume Text
    ↓
[RECON] company_intel (7 sub-agents)
    ↓
[ATLAS] user_profile ← RoleProfilerChain
        benchmark_data ← BenchmarkBuilderChain
    ↓
[CIPHER] gap_analysis ← GapAnalyzerChain(user_profile, benchmark)
    ↓
[QUILL/FORGE] doc_context = {
    user_profile, job_title, company, jd_text,
    gap_analysis, resume_text, company_intel
}
Each doc pipeline gets this full context.
    ↓
[SENTINEL] Validation scores
    ↓
[NOVA] Formatted response → DB persistence
```

---

## 5. Caching Analysis

### Implementation (`ai_engine/cache.py`)

- **Type:** In-memory LRU (OrderedDict-based)
- **Capacity:** 2,000 entries max
- **Key:** SHA-256 of `(prompt + system + model + schema + temperature + max_tokens)`
- **TTL:** Adaptive by temperature:
  - temp ≤ 0.3 → full base TTL
  - temp ≤ 0.5 → half base TTL
  - temp > 0.5 → 5 minutes
- **Singleton:** via `get_ai_cache()`

### Limitations

1. **In-memory only** — cache is lost on restart, not shared across workers/processes
2. **No Redis/external store** — single-process only
3. **Full prompt as key component** — nearly identical prompts with slight variations (different candidate names, different JD text) are all cache misses
4. **2,000 entry limit** — a single full pipeline run generates 15–30+ LLM calls, so cache fills quickly
5. **No semantic deduplication** — no embedding-based similarity matching
6. **No cross-user sharing** — identical JD analysis for different users is not shared
7. **Temperature gating is coarse** — creative outputs (temp >0.5) get only 5min TTL but may be reusable

### Cache Hit Patterns (Expected)

- **High hit rate:** Benchmark profiles for the same JD (if same user re-generates)
- **Low hit rate:** Document generation (unique per user+JD combo)
- **Zero hit rate:** Cross-user scenarios (different prompts due to different profiles)

---

## 6. Cost Hotspots

### Tier 1: Highest Cost (per invocation)

| Hotspot | Why | Est. Input Tokens | Est. Output Tokens | Model |
|---------|-----|-------------------|--------------------|-------|
| **CV Generation (Tailored)** | Prompt includes full JD + full profile + full resume text + gap analysis + company intel. System prompt ~100 lines. | 8,000–15,000 | 4,000–8,000 | Pro (drafting → Flash) |
| **Cover Letter (Tailored)** | Similar to CV — full context injection | 6,000–12,000 | 3,000–6,000 | Pro/Flash |
| **Personal Statement** | Full JD + profile + resume + gap analysis + company intel | 6,000–10,000 | 3,000–5,000 | Flash |
| **Portfolio** | Full JD + profile + resume + gap analysis | 6,000–10,000 | 3,000–5,000 | Flash |
| **Revision Loops** | Each revision re-sends the full draft + feedback + original context. With 2–3 iterations, this **MULTIPLIES** all document costs by 2–3× | Same as above × iterations | Same × iterations | Same |

### Tier 2: Moderate Cost

| Hotspot | Why | Est. Input | Est. Output | Model |
|---------|-----|-----------|------------|-------|
| **ATS Scanner** | 3 sequential LLM calls per scan (keywords + structure + strategy). Each includes 8KB doc + 6KB JD. | 14,000 × 3 = ~42,000 total | ~6,000 total | Pro (reasoning) |
| **Gap Analysis** | Large schema, full benchmark + full profile | 5,000–8,000 | 3,000–5,000 | Pro |
| **CompanyIntel (7 sub-agents)** | Up to 7 LLM calls for deep intel. JD-only fallback is 1 call. | 3,000–5,000 × 7 | 2,000–4,000 × 7 | Pro |
| **Benchmark Builder** | 1 profile + up to 5 artifacts (CV, CL, portfolio, case studies, action plan) | 3,000–5,000 × 6 | 2,000–4,000 × 6 | Pro + Flash |
| **FactChecker** | Full evidence + up to 25 claims + draft content | 4,000–8,000 | 2,000–4,000 | Pro |
| **Optimizer** | Draft + JD + tool results + improvement plan | 4,000–8,000 | 2,000–3,000 | Pro |

### Tier 3: Low Cost

| Hotspot | Est. Total Tokens | Model |
|---------|-------------------|-------|
| Career Roadmap | 3,000–6,000 | Flash |
| Interview Questions | 2,000–5,000 | Flash |
| Daily Briefing | 500–1,000 | Flash |
| Learning Challenge | 1,500–3,000 | Flash |
| Salary Analysis | 2,000–4,000 | Pro |

### Full Pipeline Cost Estimate

For a **single full generation run** (all modules, 1 revision iteration):

| Phase | Est. LLM Calls | Est. Input Tokens | Est. Output Tokens | Dominant Model |
|-------|----------------|-------------------|--------------------|----------------|
| RECON (company intel) | 7 | ~25,000 | ~20,000 | Pro |
| ATLAS (parse + benchmark) | 2–7 | ~20,000 | ~15,000 | Pro |
| CIPHER (gap analysis) | 1–2 | ~8,000 | ~5,000 | Pro |
| QUILL (CV + CL + roadmap) | 9–15 | ~50,000 | ~30,000 | Mixed |
| FORGE (PS + portfolio + extras) | 6–12 | ~40,000 | ~25,000 | Mixed |
| SENTINEL (validation) | 1–2 | ~5,000 | ~3,000 | Flash |
| **TOTAL** | **26–45 calls** | **~150,000** | **~100,000** | — |

**Estimated cost per full run:** $0.50–$1.20 (heavily dependent on Pro vs Flash routing and revision iterations).

With 2 revision iterations on documents, add ~40% to Quill+Forge costs.

---

## 7. Parallelism Analysis

### Current Parallelism

| Level | What's Parallel | How |
|-------|----------------|-----|
| **Phase 3 (Quill)** | CV pipeline ∥ CL pipeline ∥ Career Roadmap | `asyncio.gather()` |
| **Phase 4 (Forge)** | PS pipeline ∥ Portfolio pipeline | `asyncio.gather()` |
| **Phase 4b** | Extra required docs in batches of 2 | `asyncio.gather()` per batch |
| **Within Agent Pipeline (Stage 3)** | Critic ∥ Optimizer ∥ FactChecker | `asyncio.gather()` |
| **Researcher (Phase A)** | parse_jd ∥ extract_profile_evidence | Parallel deterministic tools |
| **Researcher (Phase C)** | Web search tools in parallel | Parallel tool calls |
| **Phase 1 overlap** | Benchmark CV task ∥ Doc pack plan task overlap with gap analysis | `asyncio.create_task()` |

### Sequential Bottlenecks

| Bottleneck | Why Sequential | Impact |
|------------|---------------|--------|
| **RECON → ATLAS → CIPHER** | Each depends on previous output | ~30s before doc gen can start |
| **Research → Draft → Eval → Revise** | Within each doc pipeline, stages are sequential | Each doc takes full pipeline latency |
| **ATS Scanner 3 passes** | Pass 3 depends on Pass 1 results | 3× sequential LLM latency |
| **Benchmark Builder artifacts** | Profile must complete before CV/CL/portfolio | Sequential after profile generation |
| **Extra doc batches** | Batched in pairs, not fully parallel | Adds latency for many extra docs |

### Parallelism Opportunities (Not Yet Exploited)

1. **RECON ∥ ATLAS:** Company intel and resume parsing are independent — could run concurrently (currently sequential: RECON fully completes → ATLAS starts)
2. **Multiple doc pipelines fully parallel:** Currently CV∥CL∥Roadmap and PS∥Portfolio are separate `gather()` calls. All 5 could run in one `gather()`.
3. **ATS Pass 1 ∥ Pass 2:** Keywords and structure analysis are independent; only Pass 3 (strategy) needs Pass 1 results.
4. **Cross-pipeline critic/optimizer sharing:** If CV and CL share the same JD keywords analysis, the optimizer tool results could be computed once and shared.

---

## 8. Summary Table of ALL Model Calls

| # | Location | Method | task_type | Model (default) | temp | max_tokens | Input Est. | Cache Potential | Downgrade Potential |
|---|----------|--------|-----------|-----------------|------|------------|------------|----------------|---------------------|
| 1 | `role_profiler.py` → `parse_resume()` | `complete_json()` | structured_output | Pro | 0.3 | — | 5–10K | Low (unique per resume) | Yes → Flash |
| 2 | `benchmark_builder.py` → ideal profile | `complete_json()` | structured_output | Pro | — | — | 3–5K | **Medium** (same JD = same benchmark) | Yes → Flash |
| 3 | `benchmark_builder.py` → ideal CV | `complete()` | drafting | Flash | — | — | 3–5K | Medium | Already Flash |
| 4 | `benchmark_builder.py` → ideal CL | `complete()` | drafting | Flash | — | — | 3–5K | Medium | Already Flash |
| 5 | `benchmark_builder.py` → ideal portfolio | `complete()` | drafting | Flash | — | — | 3–5K | Medium | Already Flash |
| 6 | `benchmark_builder.py` → case studies | `complete_json()` | — | Flash | — | — | 3–5K | Medium | Already Flash |
| 7 | `benchmark_builder.py` → action plan | `complete_json()` | — | Flash | — | — | 3–5K | Medium | Already Flash |
| 8 | `gap_analyzer.py` → analysis | `complete_json()` | reasoning | Pro | — | — | 5–8K | Low (unique per user+JD) | Maybe → Flash for simple gaps |
| 9 | `document_generator.py` → tailored CV | `complete()` | drafting | Flash | 0.5 | 8000 | 8–15K | **None** (unique) | Already Flash |
| 10 | `document_generator.py` → tailored CL | `complete()` | drafting | Flash | 0.7 | 6000 | 6–12K | None | Already Flash |
| 11 | `document_generator.py` → tailored PS | `complete()` | drafting | Flash | 0.7 | 5000 | 6–10K | None | Already Flash |
| 12 | `document_generator.py` → tailored portfolio | `complete()` | drafting | Flash | 0.5 | 5000 | 6–10K | None | Already Flash |
| 13 | `document_generator.py` → legacy CV | `complete()` | drafting | Flash | 0.5 | 4000 | 3–5K | None | Already Flash |
| 14 | `document_generator.py` → legacy CL | `complete()` | drafting | Flash | 0.7 | 4000 | 3–5K | None | Already Flash |
| 15 | `document_generator.py` → legacy motivation | `complete()` | drafting | Flash | 0.7 | 3000 | 3–5K | None | Already Flash |
| 16 | `document_generator.py` → legacy portfolio | `complete()` | drafting | Flash | 0.5 | 3000 | 3–5K | None | Already Flash |
| 17 | `ats_scanner.py` → Pass 1 (keywords) | `complete_json()` | structured_output | Pro | 0.1 | 2000 | 14K | Low | Yes → Flash |
| 18 | `ats_scanner.py` → Pass 2 (structure) | `complete_json()` | structured_output | Pro | 0.1 | 2000 | 8K | Low | Yes → Flash |
| 19 | `ats_scanner.py` → Pass 3 (strategy) | `complete_json()` | reasoning | Pro | 0.3 | 3000 | 14K | Low | Maybe |
| 20 | `interview_simulator.py` → questions (legacy) | `complete_json()` | creative | Flash | 0.3 | 3000 | 2–5K | Low | Already Flash |
| 21 | `interview_simulator.py` → evaluate | `complete_json()` | reasoning | Pro | 0.0 | 1500 | 2–4K | None | Yes → Flash |
| 22 | `career_consultant.py` → roadmap (legacy) | `complete_json()` | reasoning | Pro | — | — | 3–6K | Low | Maybe → Flash |
| 23 | `salary_coach.py` → analysis (legacy) | `complete_json()` | reasoning | Pro | 0.1 | 3000 | 2–4K | None | Maybe → Flash |
| 24 | `linkedin_advisor.py` → analyze (legacy) | `complete_json()` | creative | Flash | — | — | 2–4K | None | Already Flash |
| 25 | `daily_briefing.py` → generate | `complete_json()` | creative | Flash | 0.7 | 500 | 0.5–1K | None | Already Flash / 2.0-Flash |
| 26 | `learning_challenge.py` → generate | `complete_json()` | creative | Flash | — | — | 1–2K | Low | Already Flash |
| 27 | `validator.py` → validate document | `complete_json()` | validation | Flash | — | — | 3–6K | None | Already Flash |
| 28 | `validator.py` → validate analysis | `complete_json()` | validation | Flash | — | — | 3–6K | None | Already Flash |
| 29 | `company_intel.py` → JD-only fallback | `complete_json()` | reasoning | Pro | 0.2 | 4000 | 5K | Medium (same company+JD) | Maybe → Flash |
| 30 | `company_intel.py` → IntelCoordinator | 7× sub-agent calls | reasoning | Pro | — | — | 3–5K × 7 | Medium per company | Some sub-agents → Flash |
| 31 | `adaptive_document.py` → generate | `complete()` | drafting/fast_doc | Flash/2.0-Flash | — | — | 3–8K | None | Already Flash |
| 32 | `critic.py` → evaluate | `complete_json()` | critique | Flash | 0.3 | 2048 | 4K | None | Already Flash |
| 33 | `optimizer.py` → synthesize | `complete_json()` | optimization | Pro | 0.3 | 3000 | 6–8K | None | Maybe → Flash |
| 34 | `fact_checker.py` → classify claims | `complete_json()` | fact_checking | Pro | 0.2 | 4000 | 4–8K | None | Maybe → Flash |
| 35 | `drafter.py` → revise() | `complete_json()` | drafting | Flash | — | — | 4–8K | None | Already Flash |
| 36 | `researcher.py` → tool planning | `complete_json()` | varies | Pro | — | — | 2–4K | None | Maybe → Flash |
| 37+ | Sub-agent coordinators (interview, career, salary, linkedin, gap_analysis) | Multiple `complete_json()` | varies | Mixed | — | — | 2–4K × 5 per coordinator | Low | Some → Flash |

### Model Call Count per Full Pipeline Run

| Path | Minimum Calls | Typical Calls | Maximum Calls |
|------|--------------|---------------|---------------|
| RECON | 1 (fallback) | 7 | 7+ |
| ATLAS (parse) | 1 | 1 | 1 |
| ATLAS (benchmark) | 1 | 2–6 | 6 |
| CIPHER (gaps) | 1 | 1–2 | 2 |
| QUILL (CV pipeline) | 2 | 4–6 | 10+ (with revisions) |
| QUILL (CL pipeline) | 2 | 4–6 | 10+ |
| QUILL (roadmap) | 1 | 1–5 | 5 |
| FORGE (PS pipeline) | 2 | 4–6 | 10+ |
| FORGE (portfolio pipeline) | 2 | 4–6 | 10+ |
| FORGE (extra docs) | 0 | 2–6 | 12+ |
| SENTINEL | 1 | 1–2 | 2 |
| **TOTAL** | **14** | **30–50** | **75+** |

---

## 9. Redesign Risks & Recommendations

### Risk 1: Prompt Bloat in Document Generation

The tailored document prompts inject the ENTIRE JD + profile + resume + gap analysis + company intel into every prompt. For a typical job application, this can be 10–15K tokens of input per document — and with 4+ documents, that's 40–60K tokens of repeated context.

**Recommendation:** Extract shared context (JD analysis, company signals, key gaps) into a compact "application brief" (1–2K tokens) computed once, and inject that instead of raw data.

### Risk 2: Revision Loop Cost Multiplication

Each revision iteration re-sends the full draft + feedback + all original context. With 2–3 iterations × 4 documents, revision loops can double total costs.

**Recommendation:** Implement incremental revision prompts that only include the delta (feedback + specific sections to revise) rather than full context re-injection.

### Risk 3: In-Memory Cache is Production-Hostile

The LRU cache is lost on restart, not shared across workers, and has no external persistence.

**Recommendation:** Replace with Redis-backed cache. Consider embedding-based keys for semantic deduplication.

### Risk 4: Sequential Phase Dependencies

RECON → ATLAS → CIPHER must complete sequentially before any document generation starts, adding ~30s of latency before the user sees any document progress.

**Recommendation:** RECON and ATLAS can run in parallel. Gap analysis can start as soon as benchmark is ready (doesn't need RECON to complete).

### Risk 5: Sub-Agent Fallback Doubles Latency on Failure

Every v2 chain tries the sub-agent coordinator first, then falls back to legacy on failure. This means a timeout + retry cycle before the fallback even starts.

**Recommendation:** Implement circuit breakers at the coordinator level so repeated failures switch to fast-path fallback immediately.

### Risk 6: No Cross-User Cache Sharing

Identical JD benchmark analysis for different users generates separate LLM calls. For popular job postings, this is pure waste.

**Recommendation:** Cache benchmark profiles by JD hash (content-addressed) independent of user.

### Risk 7: ATS Scanner Sequential Passes

3 sequential LLM calls where 2 are independent.

**Recommendation:** Run Pass 1 (keywords) ∥ Pass 2 (structure) in parallel; only Pass 3 (strategy) depends on Pass 1.

---

*End of audit.*
