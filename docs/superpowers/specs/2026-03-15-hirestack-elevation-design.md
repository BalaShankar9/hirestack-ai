# HireStack AI — Full Elevation & Agent Swarm Design Spec

**Date:** 2026-03-15
**Status:** Approved
**Approach:** Vertical Slices (Approach C)

---

## 1. Overview

HireStack AI is an AI-powered career intelligence platform. This spec defines a comprehensive elevation covering three pillars:

1. **Agent Swarm Framework** — Backend orchestration agents that produce dramatically better AI outputs through multi-agent pipelines (drafting, critique, optimization, fact-checking, validation) running in parallel for speed.
2. **Feature Quality Polish** — Every feature fixed end-to-end: backend validation, error handling, response consistency, frontend UX, accessibility, type safety.
3. **Replit App Builder Style UI/UX** — Panel-based workspace, command palette, dual-font system, inline editing, real-time agent status, dense information display, micro-animations.

The user never sees individual agents. They see faster, dramatically better outputs with quality transparency (scores, fact-check reports, progress steps).

---

## 2. Agent Swarm Framework

### 2.1 Architecture

Seven specialized agent roles coordinated by an Orchestrator:

| Agent | Role | When Used |
|-------|------|-----------|
| **Orchestrator** | Routes work, manages pipeline, handles failures | Every pipeline |
| **Researcher** | Gathers context: industry signals, culture, emphasis, keywords | Before drafting |
| **Drafter** | Generates first-pass content (wraps existing chains) | Every pipeline |
| **Critic** | Reviews for quality, tone, completeness, consistency | After draft |
| **Optimizer** | ATS keyword density, readability, quantified impacts, section ordering | After draft |
| **Fact-Checker** | Cross-references every claim against source profile data, flags fabrication | After draft |
| **Validator** | Schema compliance, format correctness, completeness, length checks | Final stage |

### 2.2 Execution Model — Parallel for Speed

Agents run in parallel stages using `asyncio.gather`, not sequentially:

```
Stage 1 (sequential): Researcher gathers context
Stage 2 (uses research): Drafter generates first pass informed by research
Stage 3 (parallel):     Critic + Optimizer + Fact-Checker analyze draft
Stage 4 (if needed):    Drafter revision (single pass with ALL feedback merged)
Stage 5:                Validator
```

**Why Stage 1→2 is sequential, not parallel:** The Researcher's output (industry signals, resume format, keyword emphasis) directly shapes the Drafter's prompt context. Running them in parallel would mean the Drafter generates without research context, defeating the purpose. The Researcher is lightweight (context analysis, not generation), typically completing in 3–5s.

**Timing estimates** depend on model and hardware. With a local 120B model on high-end GPU (e.g., 80GB+ VRAM):
- Stage 1 (Researcher): ~5–10s
- Stage 2 (Drafter): ~15–40s (longest stage, generating full document)
- Stage 3 (parallel): ~10–20s (three agents share GPU, longest wins)
- Stage 4 (revision): ~15–30s if triggered, 0s if not
- Stage 5 (Validator): ~2–5s (schema check + brief validation prompt)
- **Total: ~35–75s** for full pipeline, ~25–45s if no revision needed

With a faster model (e.g., quantized 70B or cloud-hosted): times reduce proportionally. The key win is not speed over single-pass — it's dramatically better output quality. The parallel Stage 3 saves ~20–40s compared to running Critic, Optimizer, and Fact-Checker sequentially.

### 2.3 Quality Mode

Always maximum quality. No quality dial. Every request runs the full agent pipeline with max 2 iteration loops.

### 2.4 Agent Base Classes

```python
# ai_engine/agents/base.py

class AgentResult:
    content: dict              # structured output
    quality_scores: dict       # per-dimension scores (0-100)
    flags: list[str]           # warnings, fabrication flags
    latency_ms: int            # execution time
    metadata: dict             # agent-specific metadata

class BaseAgent(ABC):
    name: str                  # e.g., "critic"
    system_prompt: str         # loaded from prompts/ directory
    output_schema: dict        # JSON schema for structured output
    ai_client: AIClient        # uses existing AIClient (supports Ollama + fallback)

    async def run(self, context: dict) -> AgentResult: ...
    async def run_with_retry(self, context: dict, max_retries: int = 2) -> AgentResult: ...
```

**Important:** Agents use the existing `AIClient` facade, NOT direct Ollama HTTP calls. This gives agents automatic multi-provider fallback (Ollama → Gemini → OpenAI). If Ollama is down, agents degrade to the next available provider. The `AIClient` already handles connection pooling, retry with exponential backoff, and provider health detection.

### 2.5 Pipeline Engine

```python
# ai_engine/agents/orchestrator.py

class AgentPipeline:
    name: str                           # e.g., "cv_generation"
    stages: list[list[BaseAgent]]       # grouped by parallel execution stage
    max_iterations: int                 # max critic → drafter loops (always 2)
    lock_manager: PipelineLockManager   # prevents concurrent runs per user+task

    async def execute(self, context: dict) -> PipelineResult:
        pipeline_id = str(uuid4())
        user_id = context["user_id"]

        # Concurrency control: one active pipeline per (user_id, pipeline_name)
        async with self.lock_manager.acquire(user_id, self.name, pipeline_id):

            # Stage 1: Research (sequential — Drafter needs this output)
            research = await self.researcher.run(context)
            enriched_context = {**context, "research": research.content}

            # Stage 2: Draft (uses research context)
            draft = await self.drafter.run(enriched_context)

            # Stage 3: Parallel critique + optimize + fact-check
            critic, optimizer, fact_check = await asyncio.gather(
                self.critic.run(draft),
                self.optimizer.run(draft),
                self.fact_checker.run(draft, source=context),
            )

            # Stage 4: Revise if critic rejects (single pass with all feedback)
            if critic.needs_revision:
                draft = await self.drafter.revise(
                    draft,
                    feedback={
                        "critic": critic.feedback,
                        "optimizer": optimizer.suggestions,
                        "fact_check": fact_check.flags,
                    }
                )
            else:
                # Apply optimizer suggestions and fact-check fixes to the draft
                # without a full re-generation. Merges optimizer.suggestions
                # (keyword injection, readability fixes) and removes any
                # fact_check.flags marked as "fabricated" from draft.content.
                draft = AgentResult(
                    content=merge_optimizations(
                        draft.content, optimizer.content, fact_check.content
                    ),
                    quality_scores=critic.quality_scores,
                    flags=fact_check.flags,
                    latency_ms=draft.latency_ms,
                    metadata=draft.metadata,
                )

            # Stage 5: Validate
            validation = await self.validator.run(draft)

            # Assemble PipelineResult from all agent outputs
            return PipelineResult(
                content=validation.content,
                quality_scores=critic.quality_scores,
                optimization_report=optimizer.content,
                fact_check_report=fact_check.content,
                iterations_used=1 if critic.needs_revision else 0,
                total_latency_ms=sum(a.latency_ms for a in [research, draft, critic, optimizer, fact_check, validation]),
                trace_id=pipeline_id,
            )

class PipelineResult:
    content: dict              # final output
    quality_scores: dict       # aggregated from Critic
    optimization_report: dict  # from Optimizer
    fact_check_report: dict    # from Fact-Checker
    iterations_used: int       # how many critic loops
    total_latency_ms: int
    trace_id: str              # links to agent_traces table

class PipelineLockManager:
    """Prevents concurrent pipeline runs for the same (user_id, pipeline_name).

    Uses an in-memory asyncio.Lock per key. If a second request arrives while
    a pipeline is running for the same user+task, it waits (with timeout).
    Prevents race conditions on agent_memory writes and duplicate generation.
    """
    async def acquire(self, user_id: str, pipeline_name: str, pipeline_id: str):
        """Context manager that acquires a lock keyed on (user_id, pipeline_name)."""
        ...
```

### 2.6 Wrapping Existing Chains

The Drafter agent wraps existing chains. The initial `run()` delegates directly. The `revise()` method does NOT modify existing chain methods — instead, it constructs a new prompt that includes the original draft plus feedback, and calls the AIClient directly.

```python
class DrafterAgent(BaseAgent):
    def __init__(self, chain: Any, method_name: str):
        self.chain = chain           # e.g., DocumentGeneratorChain instance
        self.method_name = method_name  # e.g., "generate_cv"

    async def run(self, context: dict) -> AgentResult:
        # Delegates to existing chain method — NO modifications to chain
        method = getattr(self.chain, self.method_name)
        result = await method(
            profile=context["user_profile"],
            job_title=context["job_title"],
            ...
        )
        return AgentResult(content=result, ...)

    async def revise(self, draft: AgentResult, feedback: dict) -> AgentResult:
        # Does NOT call the chain again. Instead, uses AIClient directly
        # with a revision-specific prompt that includes the original draft
        # plus all agent feedback. This avoids modifying any existing chain.
        revision_prompt = REVISION_PROMPT_TEMPLATE.format(
            original_draft=draft.content,
            critic_feedback=feedback["critic"],
            optimizer_suggestions=feedback["optimizer"],
            fact_check_flags=feedback["fact_check"],
        )
        result = await self.ai_client.complete_json(
            system_prompt=REVISION_SYSTEM_PROMPT,
            user_prompt=revision_prompt,
            schema=self.output_schema,
        )
        return AgentResult(content=result, ...)
```

**Key design decision:** Existing chains are NOT modified at all. The `revise()` method is a separate code path that takes the original draft + feedback and asks the AI to produce an improved version. This means:
- Zero breaking changes to existing chain code
- Revision prompts are purpose-built for incorporating multi-agent feedback
- The revision prompt template lives in `agents/prompts/drafter_revision.md`

### 2.6.1 Fact-Checker vs. Strategic Enhancement — Boundary Definition

The existing `DocumentGeneratorChain` prompts instruct the AI to "strategically reframe experience" and "add realistic freelance or project-based roles." This is a deliberate product feature, not a bug.

The Fact-Checker operates with a **two-tier classification:**

| Classification | Definition | Action |
|---------------|-----------|--------|
| **Verified** | Claim directly maps to data in the user's profile (skills, titles, companies, dates) | Marked as verified |
| **Enhanced** | Claim is a strategic reframing of real experience (e.g., "Led cross-functional team" derived from "Worked with designers and backend engineers") | Marked as enhanced, kept in output |
| **Fabricated** | Claim has NO basis in any profile data (invented company, fake certification, non-existent technology) | Flagged for removal |

The Fact-Checker's system prompt explicitly defines these boundaries:
- **Enhancement is allowed** — reframing, quantifying, and elevating real experience
- **Fabrication is not allowed** — inventing experience, skills, or credentials that have zero basis in the profile
- The quality report shows: "14 claims verified, 8 claims enhanced, 0 fabrications"

This boundary is defined in `agents/prompts/fact_checker_system.md` and enforced via the Fact-Checker's output schema which requires each claim to be classified as `verified`, `enhanced`, or `fabricated` with a `source_reference` field pointing to the profile data that supports it.

### 2.7 Agent Memory (Per-User Learning)

The more a user uses HireStack, the better their outputs get.

**Database table:**

```sql
CREATE TABLE agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_type VARCHAR(50) NOT NULL,
    memory_key VARCHAR(255) NOT NULL,
    memory_value JSONB NOT NULL,
    relevance_score NUMERIC(3,2) DEFAULT 1.0,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, agent_type, memory_key)
);

CREATE INDEX idx_agent_memory_user ON agent_memory(user_id, agent_type);
```

**Memory service:**

```python
class AgentMemory:
    MAX_MEMORIES_PER_USER_AGENT = 50  # eviction threshold

    async def store(self, user_id: str, agent_type: str, key: str, value: dict):
        """Store a learned pattern. Upserts on (user_id, agent_type, key).
        If user+agent exceeds MAX_MEMORIES, evicts lowest-ranked memory."""

    async def recall(self, user_id: str, agent_type: str, limit: int = 10) -> list[dict]:
        """Retrieve relevant memories using weighted ranking:
        rank = relevance_score * 0.7 + recency_score * 0.3
        where recency_score = 1.0 / (1 + days_since_last_used)
        This prevents high-frequency but mediocre memories from dominating."""

    async def feedback(self, memory_id: str, was_useful: bool):
        """Adjust relevance_score:
        - Positive: relevance_score = min(1.0, relevance_score + 0.1)
        - Negative: relevance_score = max(0.0, relevance_score - 0.15)
        Negative feedback decays faster to quickly suppress unhelpful memories."""
```

**Ranking formula:** `rank = relevance_score * 0.7 + (1.0 / (1 + days_since_last_used)) * 0.3`

This ensures:
- Highly relevant recent memories rank highest
- Old but highly relevant memories still surface
- Frequently used but mediocre memories decay over time
- Memory eviction removes lowest-ranked entries when limit exceeded

**What agents learn (concrete examples):**

- **Critic** stores: `{key: "preferred_tone", value: {"tone": "formal", "evidence": "user edited 3 documents from casual to formal"}}` — triggered when user manually edits generated text in a consistent direction
- **Optimizer** stores: `{key: "confirmed_keyword:react", value: {"keyword": "React", "confirmed": true, "context": "user kept this keyword in 5 documents"}}` — triggered when user does NOT remove an ATS keyword across multiple documents
- **Drafter** stores: `{key: "writing_length_preference", value: {"cv_sections": "concise", "avg_edit_delta": -120}}` — triggered when user consistently shortens generated text
- **Researcher** stores: `{key: "target_industry", value: {"industry": "fintech", "seniority": "senior", "derived_from_jobs": 4}}` — triggered after analyzing 3+ job descriptions in the same industry

**When memories are written:** After each pipeline completes successfully, the Orchestrator calls a lightweight `learn()` pass that compares the pipeline's output against any user edits from the previous session. If patterns are detected (e.g., user consistently edits tone), a memory is stored.

**Measurement methodology for success criterion:** Compare Critic quality scores between:
- User's 1st–3rd pipeline runs (no memory) vs 6th–10th runs (with memory)
- Track "user edit distance" (how much users change generated output) — should decrease over time
- Both metrics stored in `agent_traces` for querying

**Memory is injected into agent context:**

```python
async def run(self, context: dict) -> AgentResult:
    memories = await self.memory.recall(context["user_id"], self.name)
    enriched_context = {**context, "agent_memories": memories}
    # Agent's system prompt includes: "Consider these learned preferences: {memories}"
    ...
```

### 2.8 Agent Observability

**Database table:**

```sql
CREATE TABLE agent_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pipeline_name VARCHAR(100) NOT NULL,
    stages JSONB NOT NULL,
    total_latency_ms INTEGER NOT NULL,
    iterations_used INTEGER DEFAULT 0,
    quality_scores JSONB,
    fact_check_flags JSONB,
    status VARCHAR(20) DEFAULT 'completed',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_traces_user ON agent_traces(user_id);
CREATE INDEX idx_agent_traces_pipeline ON agent_traces(pipeline_name);
```

Every pipeline execution is fully logged: each agent's input summary, output summary, latency, and scores. Queryable for debugging and quality monitoring.

### 2.9 Per-Feature Pipeline Configurations

| Feature | Agents | Parallel Groups | Max Iterations |
|---------|--------|-----------------|----------------|
| Resume Parse | Researcher, Drafter, Critic, FactChecker, Validator | R→D, (C+FC), V | 1 |
| Benchmark | Researcher, Drafter, Critic, Optimizer, FactChecker, Validator | R→D, (C+O+FC), V | 1 |
| Gap Analysis | Drafter, Critic, Optimizer, FactChecker, Validator | D, (C+O+FC), V | 1 |
| CV Generation | Researcher, Drafter, Critic, Optimizer, FactChecker, Validator | R→D, (C+O+FC), revise, V | 2 |
| Cover Letter | Researcher, Drafter, Critic, Optimizer, FactChecker, Validator | R→D, (C+O+FC), V | 2 |
| Personal Statement | Drafter, Critic, Validator | D, C, V | 2 |
| Portfolio | Drafter, Optimizer, Validator | D, O, V | 1 |
| ATS Scanner | Researcher, Drafter, Optimizer, Validator | R→D, O, V | 1 |
| Interview Sim (text) | Researcher, Drafter, Critic, Validator | R→D, C, V | 1 |
| Career Roadmap | Researcher, Drafter, Critic, Optimizer, Validator | R→D, (C+O), V | 1 |
| Salary Coach | Researcher, Drafter, FactChecker, Validator | R→D, FC, V | 1 |
| A/B Lab | Drafter(x3 with tone_instruction), Critic(comparative), Optimizer, Validator | D+D+D (parallel), (C+O), V | 1 |
| Learning | Drafter, Validator | D, V | 0 |

### 2.10 AI Provider Integration

**Agents use the existing `AIClient` facade** — not direct HTTP calls. This is critical for reliability.

**Configuration:**
- Primary provider: Ollama (local, model name configurable via `settings.ollama_model`)
- Fallback chain: Ollama → Gemini → OpenAI (existing AIClient behavior)
- The actual model name (e.g., `llama3:70b`, `qwen2:72b`, or whatever is pulled in Ollama) is read from `settings.ollama_model`, NOT hardcoded
- Connection pooling: handled by AIClient's existing `httpx.AsyncClient`
- Timeout: 180s per agent call (large models need headroom for full document generation)
- Retry: 2 attempts with 5s backoff on transient failures (existing AIClient retry logic)

**Concurrency constraints for large models:**
- Stage 3 runs Critic + Optimizer + Fact-Checker in parallel via `asyncio.gather`
- On consumer hardware with a single GPU, Ollama serializes concurrent requests internally (queues them)
- This means Stage 3's wall-clock time = longest single agent, NOT sum of all three
- On multi-GPU setups or with smaller quantized models, true parallel inference is possible
- The pipeline design is correct regardless — `asyncio.gather` handles both cases transparently

**Hardware baseline for reference:**
- 120B model: requires ~80GB VRAM (A100 80GB, or 2x RTX 4090 with model parallelism)
- 70B quantized (Q4): requires ~40GB VRAM (single RTX 4090 or A6000)
- Cloud-hosted API: no local hardware requirements, fastest option

### 2.11 File Structure

```
ai_engine/
├── agents/
│   ├── __init__.py              # exports all agent classes
│   ├── base.py                  # BaseAgent, AgentResult, AgentContext
│   ├── orchestrator.py          # AgentPipeline, PipelineResult, stage execution
│   ├── drafter.py               # DrafterAgent (wraps existing chains)
│   ├── critic.py                # CriticAgent (quality review, scoring)
│   ├── optimizer.py             # OptimizerAgent (ATS, readability, structure)
│   ├── fact_checker.py          # FactCheckerAgent (source verification)
│   ├── researcher.py            # ResearcherAgent (context gathering)
│   ├── schema_validator.py      # ValidatorAgent (renamed to avoid collision with chains/validator.py)
│   ├── memory.py                # AgentMemory service
│   ├── trace.py                 # AgentTrace logging service
│   ├── lock.py                  # PipelineLockManager (concurrency control)
│   └── prompts/
│       ├── drafter_revision.md  # Drafter's revision prompt (used by revise() method)
│       ├── critic_system.md     # Critic's system prompt
│       ├── optimizer_system.md  # Optimizer's system prompt
│       ├── fact_checker_system.md  # includes verified/enhanced/fabricated classification rules
│       ├── researcher_system.md
│       └── schema_validator_system.md  # Validator's system prompt
├── chains/                      # existing chains (unchanged, wrapped by Drafter)
│   ├── __init__.py
│   ├── role_profiler.py
│   ├── benchmark_builder.py
│   ├── gap_analyzer.py
│   ├── doc_generator.py
│   ├── career_consultant.py
│   ├── validator.py
│   ├── ats_scanner.py
│   ├── evidence_mapper.py
│   ├── doc_variant.py
│   ├── interview_simulator.py
│   ├── salary_coach.py
│   └── learning_challenge.py
├── schemas/
│   ├── profile_schema.json
│   ├── benchmark_schema.json
│   ├── gap_analysis_schema.json
│   ├── cv_schema.json
│   ├── cover_letter_schema.json
│   ├── ats_scan_schema.json
│   └── interview_schema.json
└── client.py                    # existing AI client (Ollama provider enhanced)
```

---

## 3. Feature Quality — Tier 1: Core Pipeline

Each feature is a vertical slice: backend fix + agent swarm + frontend fix, validated end-to-end.

### 3.1 Resume Parsing & Profile Extraction

**Agent pipeline:** Researcher → Drafter(RoleProfilerChain) | sequential, then Critic + FactChecker | sequential, then Validator. Max 1 iteration.

**What the swarm adds:**
- Researcher pre-identifies resume format (chronological/functional/hybrid) for targeted extraction
- Critic catches missed skills by cross-referencing section headers against extracted data
- Fact-Checker eliminates hallucinated skills/titles not present in source text
- Validator enforces ProfileSchema with strict typing on all fields

**Backend fixes:**
- Add input size validation (reject > 50KB text)
- Return structured errors with specific failure reasons (not generic 500)
- Return extraction confidence scores per section
- Add schema validation on RoleProfilerChain output
- Log parsing metrics (skills found, sections detected)

**Frontend fixes:**
- Show extraction confidence per section (e.g., "Skills: 95%, Experience: 78%")
- Allow user to correct/confirm extracted data inline before proceeding
- Add error state when parsing fails (currently only loading skeleton)
- Replace `Record<string, any>` in ParsedProfileData with strict interface

### 3.2 Benchmark Generation

**Agent pipeline:** Researcher + Drafter(BenchmarkBuilderChain) | sequential, then Critic + Optimizer + FactChecker | sequential, then Validator. Max 1 iteration.

**What the swarm adds:**
- Researcher extracts hidden JD signals (startup vs enterprise culture, growth vs maintenance role)
- Critic calibrates whether benchmark is achievable or unrealistic
- Optimizer tunes scoring weights to match JD emphasis
- Fact-Checker ensures every benchmark keyword traces to the actual JD text

**Backend fixes:**
- Add `UNIQUE(job_description_id)` constraint on benchmarks table (fixes race condition)
- Validate JD text is non-empty before generation
- Return benchmark confidence score
- Standardize response to `{success, data, meta}` format

**Frontend fixes:**
- Show which JD sections drove which benchmark requirements
- Add "Benchmark too aggressive?" feedback that triggers Critic re-evaluation
- Add error state for failed generation

### 3.3 Gap Analysis

**Agent pipeline:** Drafter(GapAnalyzerChain), then Critic + Optimizer + FactChecker | sequential, then Validator. Max 1 iteration.

**What the swarm adds:**
- Critic verifies score-to-gap consistency (85% score shouldn't have 10 critical gaps)
- Optimizer reorders recommendations by impact-to-effort ratio, surfaces quick wins first
- Fact-Checker cross-references every "gap" against actual profile (prevents false negatives)
- Validator enforces score ranges 0–100 and all required fields

**Backend fixes:**
- Fix N+1 query: use Supabase `.select("*, job_descriptions(*)")` for single-query fetch
- Add schema validation on GapAnalyzerChain JSON output
- Standardize response format with pagination
- Replace silent placeholder fallbacks with explicit validation errors

**Frontend fixes:**
- Show gap confidence levels
- Color-code recommendations by effort level (quick-win/medium/long-term)
- Add error state when analysis fails

### 3.4 Document Generation (CV, Cover Letter, Personal Statement, Portfolio)

**Agent pipeline (CV/Cover Letter):** Researcher + Drafter(DocumentGeneratorChain) | sequential, then Critic + Optimizer + FactChecker | parallel, revise if Critic score < 80, then Validator. Max 2 iterations.

**Agent pipeline (Personal Statement):** Drafter, Critic, Validator. Max 2 iterations.

**Agent pipeline (Portfolio):** Drafter, Optimizer, Validator. Max 1 iteration.

**What the swarm adds:**
- Researcher pre-identifies exact keywords, company tone, and emphasis before drafting
- Critic scores on 4 dimensions (impact, clarity, tone match, completeness) and triggers revision
- Optimizer does a dedicated ATS pass — injects keywords naturally, improves readability, ensures quantified achievements
- Fact-Checker enforces that every claim traces to real profile data (critical: prevents fabrication from "strategic enhancement")
- Validator checks HTML validity, document length appropriateness, all sections present

**Backend fixes:**
- Fix silent failure in `generate_all_documents()` — return which documents failed and why
- Add content length validation before storage
- Return quality scores (impact, ATS readiness, readability, fact accuracy) with response
- Fix `str(result)` casting in motivation generation — validate type before storage

**Frontend fixes:**
- Show quality report card: impact score, ATS readiness, readability, fact accuracy
- Show fact-check summary: "14 claims verified, 0 fabrications"
- Split 64KB `applications/[id]/page.tsx` into extracted components (see Section 5)
- Add Suspense boundaries around Tiptap editor imports
- Add error states for failed generation with retry button

### 3.5 Export (PDF/DOCX/ZIP)

**No agent swarm** — export is formatting, not AI. Significant quality fixes:

**Backend fixes:**
- Move DOCX generation entirely to backend using `python-docx` (proper .docx, not MHTML hack)
- Add export progress tracking for ZIP bundles
- Add retry logic for PDF generation failures
- Validate document content before export attempt
- Include quality_report.pdf in ZIP bundles (agent scores for the exported documents)

**Frontend fixes:**
- Replace 100ms `setTimeout` with `document.fonts.ready` + `requestAnimationFrame` for reliable PDF rendering
- Add progress indicator for multi-document ZIP bundles
- Error recovery: if PDF fails, offer HTML download fallback
- Fix filename sanitization (prevent path traversal)
- Remove MHTML-based DOCX; frontend calls backend DOCX endpoint and downloads result

**ZIP bundle manifest:**
```
application_package/
├── CV.pdf
├── CV.docx
├── Cover_Letter.pdf
├── Cover_Letter.docx
├── Personal_Statement.pdf
├── Portfolio.pdf
├── quality_report.pdf
└── manifest.json
```

**manifest.json schema:**
```json
{
  "version": "1.0",
  "generated_at": "2026-03-15T14:32:00Z",
  "application": {
    "job_title": "Senior Frontend Engineer",
    "company": "Stripe",
    "application_id": "uuid"
  },
  "documents": [
    {
      "filename": "CV.pdf",
      "type": "cv",
      "format": "pdf",
      "quality_scores": { "impact": 87, "ats_readiness": 92, "readability": 76, "fact_accuracy": 100 },
      "pipeline_trace_id": "uuid"
    }
  ],
  "quality_summary": {
    "avg_impact": 85,
    "avg_ats_readiness": 89,
    "total_claims_verified": 14,
    "total_claims_enhanced": 8,
    "total_fabrications": 0
  }
}
```

**quality_report.pdf generation:** Backend generates using `reportlab` (same library as document PDF export). Contains: per-document quality scores table, fact-check summary, ATS keyword coverage chart, and agent pipeline timing breakdown. Template defined in `backend/app/services/export.py`.

---

## 4. Feature Quality — Tier 2: Differentiators

### 4.1 ATS Scanner

**Agent pipeline:** Researcher + Drafter(ATSScannerChain) | sequential, then Optimizer, then Validator. Max 1 iteration.

**What the swarm adds:**
- Researcher analyzes the JD for industry-specific ATS patterns
- Optimizer cross-references scan results against the benchmark to suggest concrete fixes
- Validator ensures all score fields present and in valid ranges

**Backend fixes:**
- Add input size validation (document_content + jd_text combined token limit check)
- Add structured error for oversized inputs
- Log scan metrics

**Frontend fixes:**
- Show scan progress with agent steps
- Add error state for failed scans
- Add inline "fix this" actions next to each formatting issue

### 4.2 Interview Simulator (Text Only)

**Agent pipeline:** Researcher + Drafter(InterviewSimulatorChain) | sequential, then Critic, then Validator. Max 1 iteration.

**What the swarm adds:**
- Researcher uses gap report to target questions at weak areas (not random topics)
- Critic evaluates answer scoring for fairness and consistency
- Validator ensures STAR scores are in valid ranges

**Backend fixes:**
- Fix bare exception handler — log errors before raising
- Add session timeout handling (abandon sessions after 2 hours)
- Validate answer text is non-empty

**Frontend fixes:**
- Text-only interface (no audio/video)
- Show which gap each question targets
- Add error states for failed question generation and answer evaluation
- Add elapsed time per question

### 4.3 Career Consultant (Roadmaps)

**Agent pipeline:** Researcher + Drafter(CareerConsultantChain) | sequential, then Critic + Optimizer | sequential, then Validator. Max 1 iteration.

**What the swarm adds:**
- Researcher uses gap report + benchmark to prioritize roadmap milestones
- Critic verifies milestones are achievable and properly sequenced
- Optimizer orders learning resources by effectiveness and accessibility

**Backend fixes:**
- Add milestone dependency validation
- Standardize response format

**Frontend fixes:**
- Show milestone timeline with progress tracking
- Add error states

---

## 5. Feature Quality — Tier 3: Engagement

### 5.1 A/B Doc Lab

**Agent pipeline:** Drafter(x3 parallel — conservative/balanced/creative), then Critic(multi-doc mode) + Optimizer | sequential, then Validator. Max 1 iteration.

**Three-Drafter differentiation mechanism:** All three Drafter instances wrap the same `DocVariantChain` but receive different `tone_instruction` in their context:

```python
variants = await asyncio.gather(
    drafter.run({**context, "tone_instruction": CONSERVATIVE_TONE}),
    drafter.run({**context, "tone_instruction": BALANCED_TONE}),
    drafter.run({**context, "tone_instruction": CREATIVE_TONE}),
)
```

Where tone instructions are defined constants:
- `CONSERVATIVE_TONE`: "Use formal language, traditional structure, quantified achievements, no personality flair"
- `BALANCED_TONE`: "Professional but approachable, mix of quantified and narrative, moderate personality"
- `CREATIVE_TONE`: "Bold opening, storytelling elements, unique framing, personality-forward"

**Critic multi-document mode:** The Critic receives all three variants in a single call and scores them comparatively:

```python
critic_result = await critic.run({
    "variants": [conservative, balanced, creative],
    "evaluation_mode": "comparative",  # triggers multi-doc scoring prompt
})
# Returns: ranked list with per-variant scores and recommendation
```

**What the swarm adds:**
- Three Drafter instances generate variants in parallel (3x speed improvement over sequential)
- Critic scores all three comparatively in a single call, providing ranking and recommendation
- Optimizer provides ATS scores and readability for side-by-side comparison

### 5.2 Salary Coach

**Agent pipeline:** Researcher + Drafter(SalaryCoachChain) | sequential, then FactChecker, then Validator. Max 1 iteration.

**What the swarm adds:**
- Researcher contextualizes with benchmark seniority and gap scores
- Fact-Checker validates that salary ranges are plausible for the role/location

### 5.3 Job Board Sync

**No agent swarm** — this is a data sync feature, not AI generation. Polish backend CRUD and frontend UX only.

### 5.4 Micro-Learning

**Agent pipeline:** Drafter(LearningChallengeChain), then Validator. Max 0 iterations. (Fast path — learning challenges need speed over polish.)

**What the swarm adds:**
- Validator ensures question format is correct and all options are distinct
- Drafter uses gap report to generate challenges targeting actual weak areas

---

## 6. Replit App Builder Style UI/UX

### 6.1 Typography — Dual Font System

**New font:** IBM Plex Mono added alongside existing Inter.

| Element | Font | Weight |
|---------|------|--------|
| Scores, percentages, numbers | IBM Plex Mono | 600 |
| Agent pipeline steps, timestamps | IBM Plex Mono | 400 |
| Keyword chips, tags | IBM Plex Mono | 500 |
| Quality report values | IBM Plex Mono | 700 |
| Status indicators | IBM Plex Mono | 400 |
| Navigation, headings | Inter (unchanged) | 500–700 |
| Body text, descriptions | Inter (unchanged) | 400 |

### 6.2 Layout — Panel-Based Workspace

The application detail view (`/applications/[id]`) transforms from a scrolling page to a Replit-style panel workspace:

```
┌──────┬──────────────────────┬───────────────────────┐
│      │                      │                       │
│ Side │    MAIN PANEL        │   CONTEXT PANEL       │
│ bar  │    (resizable)       │   (resizable)         │
│      │                      │                       │
│      │  - Document editor   │  - Quality report     │
│      │  - Module cards      │  - Fact-check results │
│      │  - Gap analysis      │  - Coach panel        │
│      │                      │  - Version history    │
│      │                      │  - Agent trace log    │
│      │                      │                       │
│      ├──────────────────────┴───────────────────────│
│      │  BOTTOM PANEL (collapsible)                   │
│      │  Generation log  │  Task queue  │  Export     │
└──────┴──────────────────────────────────────────────┘
```

**Implementation:** `react-resizable-panels` library for draggable dividers.

**Behaviors:**
- Panels resize by dragging dividers
- Bottom panel collapses to a single-line status bar
- Context panel switches between quality/coach/history/traces tabs
- Main panel has document-type tabs + overview tab
- All panels update in real-time during agent pipeline execution

### 6.3 Command Palette (Cmd+K)

Global command palette for navigation and actions:

**Categories:**
- **Recent** — last 5 applications accessed
- **Actions** — New Application (Cmd+N), Generate CV (Cmd+G), Run ATS Scan (Cmd+S), Start Interview (Cmd+I), Export All (Cmd+E)
- **Navigate** — Dashboard (Cmd+1), Evidence Vault (Cmd+2), Career Analytics (Cmd+3), etc.

**Styling:** Uses existing `glass-panel` class (`bg-white/60 backdrop-blur-lg border border-white/20 rounded-xl`).

**Implementation:** `cmdk` library (lightweight, accessible, used by Vercel, Linear, Raycast).

### 6.4 Real-Time Agent Status

**Persistent status bar** (bottom of workspace, always visible):

```
● 2 agents active    CV: Optimizing (3/5)    CL: Queued    Last: 12s ago
```

**Expanded generation log** (bottom panel):

```
14:32:07  CV Pipeline      ✓ Researcher     1.8s
14:32:07  CV Pipeline      ✓ Drafter        5.2s
14:32:09  CV Pipeline      ● Critic         ━━━━░░  62%
14:32:09  CV Pipeline      ● Optimizer      ━━━░░░  48%
14:32:09  CV Pipeline      ○ Fact-Checker   waiting
14:32:09  CV Pipeline      ○ Validator      waiting
```

**Status colors** (existing palette):
- `✓` completed = `text-emerald-600` (score-excellent)
- `●` active = `text-primary` (indigo-violet)
- `○` waiting = `text-muted-foreground`

**Agent progress during generation** (replaces generic spinner):

```
Generating your CV...

✓ Analyzing job requirements        2.1s
✓ Creating first draft              5.8s
● Reviewing for quality...          ━━━━░░
○ Optimizing for ATS
○ Verifying facts
○ Final validation

[━━━━━━━━━━━━━━━━━░░░░░░░░░] 62%
```

**SSE events from backend** power this UI. Each agent stage emits a status event.

### 6.4.1 SSE Event Specification

**Endpoint:** `GET /api/generate/pipeline/stream?application_id={id}` (existing endpoint, enhanced)

**Event schema:**

```json
event: agent_status
data: {
  "pipeline_id": "uuid",
  "pipeline_name": "cv_generation",
  "stage": "critic",
  "status": "running" | "completed" | "failed" | "waiting",
  "progress_pct": 62,
  "latency_ms": 2100,
  "message": "Reviewing for quality...",
  "quality_scores": { "impact": 87, "clarity": 92 },
  "timestamp": "2026-03-15T14:32:09Z"
}

event: pipeline_complete
data: {
  "pipeline_id": "uuid",
  "pipeline_name": "cv_generation",
  "total_latency_ms": 45200,
  "iterations_used": 1,
  "quality_scores": { ... },
  "fact_check_summary": { "verified": 14, "enhanced": 8, "fabricated": 0 }
}

event: pipeline_error
data: {
  "pipeline_id": "uuid",
  "error_code": "AI_PROVIDER_UNAVAILABLE",
  "message": "AI generation temporarily unavailable",
  "retryable": true
}
```

**Frontend subscription:**

```tsx
// hooks/use-agent-status.ts
function useAgentStatus(applicationId: string) {
  // Uses EventSource API with auto-reconnect
  // Returns: { stages, isRunning, currentStage, qualityScores, error }
  // On disconnect: reconnects with Last-Event-ID header
  // On pipeline_complete: closes connection, returns final result
  // Timeout: 5 minutes (closes if no events received)
}
```

**Reconnection:** If SSE connection drops, frontend reconnects with `Last-Event-ID` header. Backend replays missed events from the `agent_traces` table for that `pipeline_id`. If pipeline already completed, backend sends `pipeline_complete` immediately.

**For A/B Lab (3 parallel Drafters):** Each Drafter emits its own `agent_status` events with a `variant` field (`conservative`, `balanced`, `creative`). Frontend shows three parallel progress tracks.

### 6.5 Inline Editing

Click-to-edit on data elements throughout the app:

- **Profile fields** — click any skill/title/company to correct inline
- **Benchmark keywords** — click to mark irrelevant or boost priority
- **Gap recommendations** — click to mark "done" or "not applicable"
- **Document sections** — click section header to jump to editor
- **Scores** — click to expand breakdown

**Shared component:**

```tsx
<InlineEditable
  value={skill.name}
  onSave={(newValue) => updateSkill(skill.id, newValue)}
  className="font-mono text-sm"
  hoverClassName="bg-primary/5 rounded px-1 -mx-1"
/>
```

### 6.6 Dense Score Dashboard

Workspace header shows all scores in a dense, monospace grid:

```
Compatibility  73%  ████████░░  │  Keywords  85%  █████████░
ATS Ready  92%  ██████████░     │  Facts  100%  ██████████████
Impact  87%  █████████░░        │  Readability  76%  ████████░░░░
```

All numbers in IBM Plex Mono. Progress bar colors:
- 90–100: `bg-emerald-500`
- 70–89: `bg-primary` (indigo-violet)
- 50–69: `bg-amber-500`
- 0–49: `bg-rose-500`

### 6.7 Micro-Animations

| Trigger | Animation | Duration |
|---------|-----------|----------|
| Score updates | Digit count-up with mono flip | 0.6s ease-out |
| Agent step completes | `check-pop` + row highlight | 0.3s |
| Document generated | `scale-in` + `shadow-glow-md` pulse | 0.4s |
| Error occurs | `shake` + destructive border flash | 0.3s |
| Panel resize | CSS transition on width/height | 0.15s |
| Tab switch | Underline slide | 0.2s |
| Keyword chip added | `bounce-sm` | 0.4s |

**New keyframes (additions to globals.css):**

```css
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-4px); }
  40% { transform: translateX(4px); }
  60% { transform: translateX(-3px); }
  80% { transform: translateX(2px); }
}

@keyframes digit-flip {
  0% { transform: translateY(100%); opacity: 0; }
  100% { transform: translateY(0); opacity: 1; }
}

@keyframes check-pop {
  0% { transform: scale(0); opacity: 0; }
  60% { transform: scale(1.2); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes bounce-sm {
  0%, 100% { transform: translateY(0); }
  40% { transform: translateY(-2px); }
  60% { transform: translateY(1px); }
}
```

All animations respect `prefers-reduced-motion: reduce` (existing behavior preserved).

### 6.8 Quality Report Card (Post-Generation)

Shown after every document generation:

```
CV Quality Report

Impact Score      ████████████░░  87/100
ATS Readiness     █████████████░  92/100
Readability       ██████████░░░░  76/100
Fact Accuracy     ████████████████ 100%

✓ 14 claims verified against your profile
✓ 23 target keywords embedded naturally
✓ Tone matches company culture

[View detailed report]
```

### 6.9 New Component File Structure

```
frontend/src/
├── components/
│   ├── workspace/
│   │   ├── panel-layout.tsx          # resizable panel system
│   │   ├── context-panel.tsx         # right panel (quality, coach, history)
│   │   ├── bottom-panel.tsx          # generation log, tasks, export
│   │   ├── status-bar.tsx            # persistent agent status
│   │   ├── agent-progress.tsx        # pipeline step visualization
│   │   ├── quality-report.tsx        # score cards with breakdowns
│   │   ├── workspace-header.tsx      # dense score dashboard
│   │   ├── module-grid.tsx           # benchmark, gaps, roadmap cards
│   │   ├── document-editor.tsx       # Tiptap wrapper per doc type
│   │   ├── document-tabs.tsx         # CV/CL/PS/Portfolio tab switcher
│   │   ├── export-panel.tsx          # PDF/DOCX/ZIP with progress
│   │   ├── fact-check-badge.tsx      # verification summary
│   │   ├── version-history.tsx       # extracted from monolith
│   │   └── coach-panel.tsx           # extracted from monolith
│   ├── command-palette/
│   │   ├── command-palette.tsx       # Cmd+K dialog
│   │   ├── command-list.tsx          # searchable command list
│   │   └── use-commands.ts           # command registry hook
│   ├── inline-edit/
│   │   ├── inline-editable.tsx       # click-to-edit wrapper
│   │   └── inline-tag-editor.tsx     # skill/keyword inline editing
│   ├── scores/
│   │   ├── score-bar.tsx             # animated progress bar
│   │   ├── score-grid.tsx            # dense score dashboard
│   │   └── digit-counter.tsx         # animated number counter
│   ├── feedback/
│   │   ├── error-card.tsx            # standardized error display
│   │   ├── loading-skeleton.tsx      # standardized loading states
│   │   └── retry-button.tsx          # retry with exponential backoff
│   └── ui/
│       └── ... (existing Radix components, unchanged)
├── fonts/
│   └── ibm-plex-mono.ts             # IBM Plex Mono config via next/font
└── app/(dashboard)/applications/[id]/
    ├── page.tsx                      # ~50 lines, layout + Suspense
    ├── _components/                  # extracted from 64KB monolith
    │   ├── workspace-header.tsx
    │   ├── module-grid.tsx
    │   ├── document-editor.tsx
    │   ├── document-tabs.tsx
    │   ├── export-panel.tsx
    │   ├── agent-quality-report.tsx
    │   ├── fact-check-badge.tsx
    │   ├── version-history.tsx
    │   └── coach-panel.tsx
    └── _hooks/
        ├── use-workspace.ts
        ├── use-documents.ts
        └── use-agent-status.ts
```

---

## 7. Frontend Systematic Fixes

Applied across ALL pages, not just the workspace:

### 7.1 Error States

Every data-loading component uses this pattern:

```tsx
if (loading) return <LoadingSkeleton />;
if (error) return <ErrorCard title="..." message={error.message} onRetry={retry} aria-live="assertive" />;
return <Content data={data} />;
```

### 7.2 Accessibility

| Fix | Where |
|-----|-------|
| `aria-live="polite"` | All loading states |
| `aria-live="assertive"` | All error states |
| `aria-label` | All icon-only buttons |
| Focus trap | Mobile menu, all dialogs |
| Focus return | Dialog close → trigger button |
| Color + icon | All status badges (not color-only) |
| `role="status"` | Score displays |
| Keyboard nav | Sidebar collapse, command palette |

### 7.3 Type Safety

Replace all `Record<string, any>` in `types/index.ts` with strict interfaces. Every API boundary type gets explicit fields. No `any` anywhere.

### 7.4 Performance

- `React.memo()` on all extracted components (StatCard, MiniMetric, ModuleCard, etc.)
- Suspense boundaries around Tiptap editor and heavy components
- Exponential backoff on retries (replace immediate retry in firestore/ops.ts)
- `react-resizable-panels` is lightweight (~5KB gzipped)
- `cmdk` is lightweight (~4KB gzipped)

---

## 8. Backend Systematic Fixes

### 8.1 Error Handling

Replace all bare `except Exception` with typed handlers:

```python
except ValueError as e:
    raise HTTPException(status_code=422, detail=str(e))
except AIProviderError as e:
    logger.error("ai_generation_failed", error=str(e), trace_id=trace_id)
    raise HTTPException(status_code=502, detail="AI generation temporarily unavailable")
except Exception as e:
    logger.error("unexpected_error", error=str(e), trace_id=trace_id)
    raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

### 8.2 Response Format

Standardize all routes to:

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "trace_id": "uuid",
    "quality_scores": { ... },
    "latency_ms": 1234
  }
}
```

Error responses:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "details": { ... }
  }
}
```

### 8.3 Pagination

All list endpoints gain `skip` and `limit` parameters:

```python
@router.get("/documents")
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    ...
    return {"success": True, "data": docs, "meta": {"total": total, "skip": skip, "limit": limit}}
```

### 8.4 Input Validation

Services validate inputs instead of falling back to placeholders:

```python
# BEFORE
job_title = job.get("title", "Target Role")  # silent fallback

# AFTER
job_title = job.get("title")
if not job_title:
    raise ValueError("Job title is required for benchmark generation")
```

### 8.5 AI Response Validation

After every AI chain call, validate against JSON schema:

```python
import jsonschema

result = await chain.generate_cv(...)
jsonschema.validate(result, cv_schema)  # raises ValidationError if malformed
```

Schemas stored in `ai_engine/schemas/` directory.

---

## 9. Database Fixes

| Fix | Table | Impact |
|-----|-------|--------|
| Add `UNIQUE(job_description_id)` | benchmarks | Prevents race condition duplicates |
| Add `agent_memory` table | new | Agent per-user learning |
| Add `agent_traces` table | new | Agent observability |
| Add composite index `(user_id, status)` | applications | Faster filtered queries |
| Add composite index `(application_id, document_type)` | documents | Faster document retrieval |
| Add composite index `(user_id, created_at DESC)` | multiple | Faster timeline views |
| Add RLS policy to `review_comments` | review_comments | User isolation (security fix) |
| Add CHECK constraints for elite enums | ats_scans, doc_variants, job_matches, learning_challenges | Data integrity |
| Add realtime publication | doc_variants, job_matches, review_comments, career_snapshots | Frontend reactivity |
| Enable PgBouncer | config | Connection pooling |

---

## 10. Full Elevation (Infrastructure)

### 10.1 Testing

```
backend/tests/
├── unit/
│   ├── test_agents/           # orchestrator, critic, fact-checker, validator
│   ├── test_services/         # benchmark, gap, document, interview
│   └── test_database/         # retry logic, query builder
├── integration/
│   ├── test_agent_pipelines.py  # full pipeline with mock Ollama
│   ├── test_api_routes.py
│   └── test_auth_flow.py
└── conftest.py                  # fixtures, mock Ollama server
```

### 10.2 CI/CD

GitHub Actions workflow:
- Lint (ruff + eslint)
- Type check (mypy + tsc)
- Unit tests (pytest + vitest)
- Integration tests
- Docker build verification
- Security scan (dependency audit)

### 10.3 Monitoring

- Sentry for error tracking (backend + frontend)
- Agent trace table for AI pipeline monitoring
- Structured logs with correlation IDs via structlog

### 10.4 Backend Hardening

- Fail fast on missing critical config (startup validation)
- Request/response logging with correlation IDs
- Fix Supabase connection pooling (enable PgBouncer)
- Docker network isolation, health check wait conditions, resource limits

---

## 11. Phase Plan

```
Phase 1: Agent Framework Foundation                    (~Week 1)
├── BaseAgent, AgentResult, AgentContext, PipelineLockManager
├── AgentPipeline execution engine with sequential research → draft, parallel critique
├── Orchestrator with stage management and SSE event emission
├── AIClient integration (agents use existing facade, not direct HTTP)
├── AgentMemory table + service (with ranking formula + eviction)
├── AgentTrace table + logging service
├── Agent system prompts (drafter_revision, critic, optimizer, fact_checker, researcher, schema_validator)
├── Fact-Checker boundary definition (verified/enhanced/fabricated classification)
├── JSON schemas for all output types
├── DB: agent_memory table, agent_traces table (required for framework)
├── DB: RLS policy on review_comments (security fix, should not be deferred)
├── Shared ErrorCard, LoadingSkeleton components
├── IBM Plex Mono font integration (via next/font/google)
└── Command palette (cmdk v1) skeleton

Phase 2: Tier 1 — Core Pipeline                       (~Weeks 2–4)
├── Resume Parsing (agents + backend fixes + frontend fixes)
├── Benchmark Generation (agents + backend fixes + frontend fixes)
├── DB: UNIQUE(job_description_id) on benchmarks (required before benchmark agents run)
├── Gap Analysis (agents + backend fixes + frontend fixes)
├── Document Generation — all 4 types (agents + backend fixes + frontend fixes)
├── Export overhaul (DOCX to backend python-docx, ZIP manifest, progress tracking)
├── applications/[id]/page.tsx refactor → panel workspace
├── Resizable panel layout (react-resizable-panels)
├── SSE endpoint for agent progress + frontend useAgentStatus hook
├── Agent progress UI + quality report card
├── Dense score dashboard
├── Inline editing components
├── Real-time status bar + generation log (bottom panel)
├── DB: composite indexes (user_id, status), (application_id, document_type)
└── End-to-end validation of entire core pipeline

Phase 3: Tier 2 — Differentiators                     (~Weeks 5–6)
├── ATS Scanner (agents + backend + frontend)
├── Interview Simulator — text only (agents + backend + frontend)
├── Career Consultant (agents + backend + frontend)
├── DB: CHECK constraints for ats_scans, interview_sessions enums
└── End-to-end validation

Phase 4: Tier 3 — Engagement                          (~Weeks 7–8)
├── A/B Doc Lab (3-Drafter variant + comparative Critic + agents + frontend)
├── Salary Coach (agents + backend + frontend)
├── Job Board Sync (backend + frontend polish)
├── Micro-Learning (agents + backend + frontend)
├── DB: CHECK constraints for doc_variants, job_matches, learning_challenges enums
├── DB: realtime publication for doc_variants, job_matches, review_comments, career_snapshots
└── End-to-end validation

Phase 5: Full Elevation                                (~Weeks 9–10)
├── Unit + integration test suite (conftest with mock AIClient)
├── CI/CD pipeline (GitHub Actions)
├── DB: remaining indexes (user_id, created_at DESC), enable PgBouncer
├── Backend hardening (error format, pagination, config validation, correlation IDs)
├── Monitoring setup (Sentry + agent trace dashboard)
├── Docker improvements (networks, health check conditions, resource limits)
└── Final end-to-end validation of all features
```

---

## 12. Success Criteria

- Every AI feature produces output that passes Fact-Checker with 0 fabrications (verified + enhanced only)
- Every agent pipeline completes within hardware-appropriate time limits (under 120s on recommended hardware)
- Every frontend page has proper loading, error, and empty states
- All `Record<string, any>` eliminated from TypeScript types
- `applications/[id]/page.tsx` reduced from 64KB to < 5KB (composition of extracted components)
- All list endpoints support pagination
- All error responses follow standardized `{success, data/error, meta}` format
- Agent memory demonstrates measurable quality improvement: user edit distance decreases by >20% after 5+ sessions (tracked via agent_traces)
- Full test coverage on agent framework (unit) and core pipeline (integration), using mock AIClient
- Zero bare `except Exception` blocks without logging
- SSE agent progress events delivered reliably with reconnection support
- Agents use AIClient facade with automatic provider fallback (no direct Ollama dependency)
