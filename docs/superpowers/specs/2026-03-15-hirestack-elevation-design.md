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
Stage 1 (parallel):  Researcher + Drafter
Stage 2 (parallel):  Critic + Optimizer + Fact-Checker
Stage 3 (if needed): Drafter revision (single pass with ALL feedback merged)
Stage 4:             Validator
```

Estimated timing: 12–16s for full swarm vs 8–12s for current single-pass, with dramatically better output quality.

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
    ollama_model: str          # "gpt-oss-120b"

    async def run(self, context: dict) -> AgentResult: ...
    async def run_with_retry(self, context: dict, max_retries: int = 2) -> AgentResult: ...
```

### 2.5 Pipeline Engine

```python
# ai_engine/agents/orchestrator.py

class AgentPipeline:
    name: str                           # e.g., "cv_generation"
    stages: list[list[BaseAgent]]       # grouped by parallel execution stage
    max_iterations: int                 # max critic → drafter loops (always 2)
    ollama_model: str                   # "gpt-oss-120b"

    async def execute(self, context: dict) -> PipelineResult:
        # Stage 1: parallel research + draft
        research, draft = await asyncio.gather(
            self.researcher.run(context),
            self.drafter.run(context),
        )
        enriched_draft = merge(draft, research)

        # Stage 2: parallel critique + optimize + fact-check
        critic, optimizer, fact_check = await asyncio.gather(
            self.critic.run(enriched_draft),
            self.optimizer.run(enriched_draft),
            self.fact_checker.run(enriched_draft, source=context),
        )

        # Stage 3: revise if critic rejects (single pass with all feedback)
        if critic.needs_revision:
            enriched_draft = await self.drafter.revise(
                enriched_draft,
                feedback={
                    "critic": critic.feedback,
                    "optimizer": optimizer.suggestions,
                    "fact_check": fact_check.flags,
                }
            )
        else:
            enriched_draft = apply_optimizations(enriched_draft, optimizer, fact_check)

        # Stage 4: validate
        return await self.validator.run(enriched_draft)

class PipelineResult:
    content: dict              # final output
    quality_scores: dict       # aggregated from Critic
    optimization_report: dict  # from Optimizer
    fact_check_report: dict    # from Fact-Checker
    iterations_used: int       # how many critic loops
    total_latency_ms: int
    trace_id: str              # links to agent_traces table
```

### 2.6 Wrapping Existing Chains

The Drafter agent wraps existing chains without modifying them:

```python
class DrafterAgent(BaseAgent):
    def __init__(self, chain: Any):
        self.chain = chain  # e.g., DocumentGeneratorChain instance

    async def run(self, context: dict) -> AgentResult:
        # Delegates to existing chain method
        result = await self.chain.generate_cv(
            profile=context["user_profile"],
            job_title=context["job_title"],
            ...
        )
        return AgentResult(content=result, ...)

    async def revise(self, draft: dict, feedback: dict) -> AgentResult:
        # New method: re-generates with critic feedback injected into prompt
        result = await self.chain.generate_cv(
            ...,
            revision_feedback=feedback,  # added parameter to chain
        )
        return AgentResult(content=result, ...)
```

Existing chains gain one new optional parameter (`revision_feedback`) but are otherwise unchanged. Zero breaking changes.

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
    async def store(self, user_id: str, agent_type: str, key: str, value: dict):
        """Store a learned pattern. Upserts on (user_id, agent_type, key)."""

    async def recall(self, user_id: str, agent_type: str, limit: int = 10) -> list[dict]:
        """Retrieve relevant memories for this agent, ordered by relevance_score * usage_count."""

    async def feedback(self, memory_id: str, was_useful: bool):
        """Adjust relevance_score based on whether the memory improved output."""
```

**What agents learn:**
- **Critic** learns the user's preferred tone and style (formal vs conversational)
- **Optimizer** learns which keywords the user has confirmed as relevant
- **Drafter** adapts to the user's writing patterns and vocabulary
- **Researcher** remembers the user's target industries and seniority level

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
| Resume Parse | Researcher, Drafter, Critic, FactChecker, Validator | (R+D), (C+FC), V | 1 |
| Benchmark | Researcher, Drafter, Critic, Optimizer, FactChecker, Validator | (R+D), (C+O+FC), V | 1 |
| Gap Analysis | Drafter, Critic, Optimizer, FactChecker, Validator | D, (C+O+FC), V | 1 |
| CV Generation | Researcher, Drafter, Critic, Optimizer, FactChecker, Validator | (R+D), (C+O+FC), revise, V | 2 |
| Cover Letter | Researcher, Drafter, Critic, Optimizer, Validator | (R+D), (C+O), V | 2 |
| Personal Statement | Drafter, Critic, Validator | D, C, V | 2 |
| Portfolio | Drafter, Optimizer, Validator | D, O, V | 1 |
| ATS Scanner | Researcher, Drafter, Optimizer, Validator | (R+D), O, V | 1 |
| Interview Sim (text) | Researcher, Drafter, Critic, Validator | (R+D), C, V | 1 |
| Career Roadmap | Researcher, Drafter, Critic, Optimizer, Validator | (R+D), (C+O), V | 1 |
| Salary Coach | Researcher, Drafter, FactChecker, Validator | (R+D), FC, V | 1 |
| A/B Lab | Drafter(x3), Critic, Optimizer, Validator | D+D+D, (C+O), V | 1 |
| Learning | Drafter, Validator | D, V | 0 |

### 2.10 Ollama Integration

**Provider configuration:**
- Model: `gpt-oss-120b` for all agents
- Connection: localhost Ollama API
- Connection pooling via `httpx.AsyncClient` with `limits=httpx.Limits(max_connections=8)`
- Parallel inference: GPU handles concurrent requests (stages 1 and 2 benefit from batching)
- Timeout: 120s per agent call (120B model needs headroom)
- Retry: 2 attempts with 5s backoff on transient failures

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
│   ├── validator.py             # ValidatorAgent (schema, format, completeness)
│   ├── memory.py                # AgentMemory service
│   ├── trace.py                 # AgentTrace logging service
│   └── prompts/
│       ├── critic_system.md     # Critic's system prompt
│       ├── optimizer_system.md  # Optimizer's system prompt
│       ├── fact_checker_system.md
│       ├── researcher_system.md
│       └── validator_system.md
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

**Agent pipeline:** Researcher → Drafter(RoleProfilerChain) | parallel, then Critic + FactChecker | parallel, then Validator. Max 1 iteration.

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

**Agent pipeline:** Researcher + Drafter(BenchmarkBuilderChain) | parallel, then Critic + Optimizer + FactChecker | parallel, then Validator. Max 1 iteration.

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

**Agent pipeline:** Drafter(GapAnalyzerChain), then Critic + Optimizer + FactChecker | parallel, then Validator. Max 1 iteration.

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

**Agent pipeline (CV/Cover Letter):** Researcher + Drafter(DocumentGeneratorChain) | parallel, then Critic + Optimizer + FactChecker | parallel, revise if Critic score < 80, then Validator. Max 2 iterations.

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

---

## 4. Feature Quality — Tier 2: Differentiators

### 4.1 ATS Scanner

**Agent pipeline:** Researcher + Drafter(ATSScannerChain) | parallel, then Optimizer, then Validator. Max 1 iteration.

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

**Agent pipeline:** Researcher + Drafter(InterviewSimulatorChain) | parallel, then Critic, then Validator. Max 1 iteration.

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

**Agent pipeline:** Researcher + Drafter(CareerConsultantChain) | parallel, then Critic + Optimizer | parallel, then Validator. Max 1 iteration.

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

**Agent pipeline:** Drafter(x3 parallel — conservative/balanced/creative), then Critic + Optimizer | parallel, then Validator. Max 1 iteration.

**What the swarm adds:**
- Three Drafter instances generate variants in parallel (3x speed improvement)
- Critic scores all three for comparative ranking
- Optimizer provides ATS scores and readability for side-by-side comparison

### 5.2 Salary Coach

**Agent pipeline:** Researcher + Drafter(SalaryCoachChain) | parallel, then FactChecker, then Validator. Max 1 iteration.

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

**New keyframes:**

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
├── BaseAgent, AgentResult, AgentContext
├── AgentPipeline execution engine with parallel stages
├── Orchestrator with stage management
├── OllamaProvider enhancement (connection pooling, parallel inference)
├── AgentMemory table + service
├── AgentTrace table + logging service
├── Agent system prompts (critic, optimizer, fact-checker, researcher, validator)
├── JSON schemas for all output types
├── Shared ErrorCard, LoadingSkeleton components
├── IBM Plex Mono font integration
└── Command palette (cmdk) skeleton

Phase 2: Tier 1 — Core Pipeline                       (~Weeks 2–4)
├── Resume Parsing (agents + backend fixes + frontend fixes)
├── Benchmark Generation (agents + backend fixes + frontend fixes)
├── Gap Analysis (agents + backend fixes + frontend fixes)
├── Document Generation — all 4 types (agents + backend fixes + frontend fixes)
├── Export overhaul (DOCX fix, ZIP manifest, progress tracking)
├── applications/[id]/page.tsx refactor → panel workspace
├── Resizable panel layout implementation
├── Agent progress UI + quality report card
├── Dense score dashboard
├── Inline editing components
├── Real-time status bar + generation log
└── End-to-end validation of entire core pipeline

Phase 3: Tier 2 — Differentiators                     (~Weeks 5–6)
├── ATS Scanner (agents + backend + frontend)
├── Interview Simulator — text only (agents + backend + frontend)
├── Career Consultant (agents + backend + frontend)
└── End-to-end validation

Phase 4: Tier 3 — Engagement                          (~Weeks 7–8)
├── A/B Doc Lab (agents + backend + frontend)
├── Salary Coach (agents + backend + frontend)
├── Job Board Sync (backend + frontend polish)
├── Micro-Learning (agents + backend + frontend)
└── End-to-end validation

Phase 5: Full Elevation                                (~Weeks 9–10)
├── Unit + integration test suite
├── CI/CD pipeline (GitHub Actions)
├── Database fixes (indexes, RLS, constraints, pooling)
├── Backend hardening (error format, pagination, config validation, logging)
├── Monitoring setup (Sentry + agent traces)
├── Docker improvements (networks, health checks, resource limits)
└── Final end-to-end validation of all features
```

---

## 12. Success Criteria

- Every AI feature produces output that passes Fact-Checker with 0 fabrications
- Every agent pipeline completes in under 20 seconds
- Every frontend page has proper loading, error, and empty states
- All `Record<string, any>` eliminated from TypeScript types
- `applications/[id]/page.tsx` reduced from 64KB to < 5KB (composition of components)
- All list endpoints support pagination
- All error responses follow standardized format
- Agent memory demonstrates measurable quality improvement after 5+ user sessions
- Full test coverage on agent framework (unit) and core pipeline (integration)
- Zero bare `except Exception` blocks without logging
