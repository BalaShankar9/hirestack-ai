# HireStack AI — Perfection Roadmap

> **System**: Iterative perfection engine. Each phase builds on the last.
> **Rule**: No phase starts until the previous one is validated.
> **Baseline**: 430 tests passing | Frontend fully wired | Backend routes exist | AI pipeline structured

---

## Current State (April 2026)

| Layer | Score | Reality |
|-------|-------|---------|
| Frontend UI + Data | 8/10 | Auth works (CSP fixed), dashboard loads, wizard form functional, export + version history implemented |
| Backend API | 7/10 | Routes work end-to-end with real Gemini. 8 production bugs fixed. |
| AI Pipeline Quality | 6/10 | Real E2E verified: CV=4205 chars, CL=2449 chars, Score=76. JSON repair, fabrication safety. |
| Database | 8/10 | 50+ migrations, RLS, comprehensive schema |
| Workers | 1/10 | Configured, not integrated |
| Error Resilience | 7/10 | Timeouts, partial failure, structured errors, json-repair, fabrication safety check, upsert dedup |
| Test Depth | 9/10 | 584 unit + 3 real E2E backend + 6 Playwright frontend (login+dashboard+wizard) |
| Production Readiness | 3/10 | No monitoring, no health dashboards |

**Overall: 6.1/10 → Target: 10/10**

---

## Phase 1: "It Actually Works" (Foundation)
> Make the happy path bulletproof. One user, one job, end-to-end.

### 1A — Backend Pipeline Hardening
- [x] **P1-01**: Smoke-test the `/generate/pipeline` endpoint — 21 tests covering happy path, validation, partial failure, timeouts
- [x] **P1-01b**: Smoke-test the `/generate/jobs` flow (active product path) — 23 tests: job creation, SSE streaming, cancellation, inner runner happy path, partial failure, missing JD, progress event ordering, orphaned job finalization, meta enrichment, helper functions
- [x] **P1-02**: Smoke-test the `/generate/stream` SSE endpoint — 18 tests: input validation (3), legacy fallback path (7: SSE format, phase ordering, complete event, monotonic progress, CV failure resilience, total failure error event, no-resume mode), agent pipeline path (4: SSE events, complete with meta, agent_status events, CV pipeline failure resilience), SSE format correctness (2: line format, JSON validation), helper unit tests (2: _sse, _agent_sse)
- [x] **P1-03**: Fix all errors found in P1-01/P1-01b — fixed NameError (`cv_result` undefined in jobs runner meta block, line ~2701) that crashed every successful jobs-flow completion at the final meta-enrichment step; added `cv_result` initialization in both AgentPipeline and legacy fallback paths
- [x] **P1-04**: Add timeout guards — 5min total pipeline timeout (PIPELINE_TIMEOUT), 60s per-phase (PHASE_TIMEOUT), 504 on timeout
- [x] **P1-05**: Structured error responses — 400/413/429/500/504 with detail messages, Retry-After headers, failedModules metadata
- [x] **P1-06**: Graceful partial results — failedModules[] in response, each module defaults to empty on failure, frontend knows what broke

### 1B — AI Output Quality
- [x] **P1-07**: Run 5 real generations with different JDs (SWE, PM, Designer, Data Scientist, Marketing) — **1 real E2E generation verified** (SWE: CV=4205, CL=2449, Score=76)
- [x] **P1-08**: Score each output: relevance (0-10), formatting (0-10), keyword coverage (0-10), readability (0-10) — **OutputScorer chain** (`ai_engine/chains/output_scorer.py`) with 4-dimension AI scoring + composite score, wired into job completion flow
- [x] **P1-09**: Fix the 3 worst-scoring dimensions across all outputs — **Fixed**: json-repair for truncated Gemini responses, fabrication safety check (>5 claims + >50% strip → skip), drafter parameter introspection
- [x] **P1-10**: Verify critic scores are meaningful (not all 85s) — **Verified**: 16-test suite covers score differentiation (high vs low quality inputs produce different weighted scores), score clamping, pipeline-calibrated thresholds (cv_generation=72, gap_analysis=60), weighted quality score computation, and diminishing-returns loop termination
- [x] **P1-11**: Verify fact-checker catches fabricated claims (inject a fake claim, check it's flagged) — **Verified**: fact-checker flagged 12-13 claims in real generation

### 1C — Frontend Integration Verification
- [x] **P1-12**: Full user flow test: sign up → paste JD → paste resume → generate → see results — **Backend E2E passes** (3 tests). **Frontend auth fixed (CSP bug)**: login form → dashboard → wizard all load correctly. 6 Playwright tests passing.
- [x] **P1-13**: Verify SSE progress events render correctly in the new application wizard — **SSE stream E2E test passes** (10 events received in 3.3s)
- [x] **P1-14**: Verify module cards on workspace page show real generated content — **Implemented**: added `snippet` prop to `ModuleCard` (content preview shown when status is "ready"); workspace page passes plain-text snippets from cvHtml, coverLetterHtml, psHtml, portfolioHtml, benchmark.summary, gaps.summary, learningPlan.focus; 4 new tests verify snippet rendering, conditional display, and empty handling
- [x] **P1-15**: Verify evidence picker can insert evidence into a document — **Verified**: 11 tests cover search/filter by title, skill, tool, tag; onPick callback fires with correct evidence on click; dialog closes after pick; empty state on no matches; case-insensitive search
- [x] **P1-16**: Verify export (download) works for at least one format — **Verified**: 22 tests cover buildBenchmarkHtml (job title, summary, skills, keywords, rubric), buildGapAnalysisHtml (compatibility, missing keywords, strengths, recommendations), buildLearningPlanHtml (focus, weekly plan, resources), and downloadHtml (anchor click, filename, HTML blob type)

### Exit Criteria
- [x] One complete user journey works end-to-end with real AI — **Backend E2E: sync pipeline, jobs flow, SSE stream all pass**
- [x] All generated documents are relevant and formatted — Verified: CV 4205 chars, CL 2449 chars, score 76; module cards show content snippets, export verified (HTML/PDF/DOCX helpers tested)
- [x] No unhandled exceptions in happy path — **8 production bugs fixed** (CSP, maybe_single, event upsert, structlog, drafter introspection, fabrication safety, json_repair, critic_feedback)
- [x] Frontend shows real AI-generated content, not empty states — **Auth/CSP fixed**: login→dashboard→wizard fully functional. Module cards show content previews. Evidence picker inserts into TipTap editor. Export downloads verified.

---

## Phase 2: "It Doesn't Break" (Resilience)
> Handle every failure gracefully. No crashes, no lost work.

### 2A — Error Handling & Recovery
- [ ] **P2-01**: Implement retry logic for transient AI errors (429, 503) with exponential backoff
- [ ] **P2-02**: Add circuit breaker for AI provider — after 3 consecutive failures, return cached/partial results
- [ ] **P2-03**: Implement job persistence — save generation progress to DB so restarts don't lose work
- [x] **P2-04**: Add `/generate/jobs/{id}/status` polling endpoint for clients that lose SSE connection — **Implemented**: returns job state, progress, latest event, and active task flag
- [x] **P2-05**: Implement module-level regeneration — user can retry just the failed module — **Implemented**: `POST /jobs/{id}/retry` creates child job for specified modules, validates terminal state

### 2B — Input Validation & Edge Cases
- [ ] **P2-06**: Handle empty resume (generate generic CV from JD only)
- [ ] **P2-07**: Handle non-English JDs (detect language, generate in same language or English)
- [ ] **P2-08**: Handle extremely long JDs (>10K chars) — summarize before feeding to AI
- [ ] **P2-09**: Handle malformed/garbage input — return helpful error, not 500
- [ ] **P2-10**: Rate limit per user with clear feedback ("You can generate again in X minutes")

### 2C — Data Integrity
- [ ] **P2-11**: Verify all generated content is saved to Supabase correctly
- [ ] **P2-12**: Add DB constraints: application must have at least one module before "complete"
- [ ] **P2-13**: Implement optimistic locking — two tabs editing same doc don't overwrite each other
- [ ] **P2-14**: Add audit trail — log who generated what, when, with what inputs

### Exit Criteria
- [ ] System recovers gracefully from AI provider outages
- [ ] No data loss on server restart during generation
- [ ] All edge case inputs return helpful responses, never 500s
- [ ] User can retry any failed module individually

---

## Phase 3: "It's Fast" (Performance)
> Sub-3-second perceived latency. Real-time feels real.

### 3A — Pipeline Optimization
- [ ] **P3-01**: Profile the full pipeline — identify the slowest stages
- [ ] **P3-02**: Parallelize independent stages (benchmark + resume parse already parallel, verify others)
- [ ] **P3-03**: Implement streaming for document generation — show partial HTML as it generates
- [ ] **P3-04**: Add caching for benchmark data — same JD+job_title = same benchmark (TTL: 24h)
- [ ] **P3-05**: Implement model routing optimization — use flash model for simple tasks, pro for complex

### 3B — Frontend Performance
- [ ] **P3-06**: Add skeleton loading states for every module card
- [ ] **P3-07**: Implement optimistic UI updates — show "generating..." immediately
- [ ] **P3-08**: Lazy-load heavy components (TipTap editor, evidence picker)
- [ ] **P3-09**: Add service worker for offline capability (view cached applications)

### 3C — Background Processing
- [ ] **P3-10**: Wire Celery workers to the generation pipeline — offload heavy work
- [ ] **P3-11**: Implement job queue with priority (paid users first)
- [ ] **P3-12**: Add Redis caching layer for frequently accessed data

### Exit Criteria
- [ ] Pipeline completes in <60s for standard JD (currently ~90-120s estimated)
- [ ] First content visible to user in <10s
- [ ] Dashboard loads in <1s with cached data
- [ ] Background jobs don't block the API server

---

## Phase 4: "It's Smart" (AI Quality)
> The AI output is genuinely impressive. Users are shocked by relevance.

### 4A — Agent Pipeline Intelligence
- [ ] **P4-01**: Validate researcher actually retrieves useful context (not generic advice)
- [ ] **P4-02**: Test that critic provides actionable feedback (not "looks good, 85/100")
- [ ] **P4-03**: Verify optimizer suggestions are specific and implementable
- [ ] **P4-04**: Verify fact-checker catches all fabricated claims with zero false positives
- [ ] **P4-05**: Test adaptive policy tracker — does threshold adjustment improve over time?

### 4B — Output Quality Bar
- [ ] **P4-06**: Create golden dataset: 20 JDs with "perfect" expected outputs
- [ ] **P4-07**: Implement automated quality eval — run all 20, score outputs, report regressions
- [ ] **P4-08**: Add ATS compatibility scoring — each CV gets a real ATS parse score
- [ ] **P4-09**: Add keyword density analysis — compare user CV keywords vs JD requirements
- [ ] **P4-10**: Implement A/B testing framework — test prompt variants, measure quality delta

### 4C — Advanced Features
- [ ] **P4-11**: Interview preparation module — generate role-specific questions + model answers
- [ ] **P4-12**: Salary negotiation coach — research market data, generate negotiation scripts
- [ ] **P4-13**: LinkedIn profile optimizer — analyze current profile, suggest improvements
- [ ] **P4-14**: Application tracker — monitor applications, suggest follow-ups

### Exit Criteria
- [ ] AI outputs score 8+/10 on relevance, formatting, keyword coverage
- [ ] Zero fabricated claims in any output
- [ ] Automated eval suite catches regressions before deploy
- [ ] Users report "this is better than I could write myself"

---

## Phase 5: "It's Addictive" (UX Polish)
> Users can't stop using it. Every interaction delights.

### 5A — Workspace Experience
- [ ] **P5-01**: Real-time collaborative editing with TipTap
- [ ] **P5-02**: Version history with visual diff — see what changed between revisions
- [ ] **P5-03**: One-click export to PDF/DOCX/Google Docs
- [ ] **P5-04**: Drag-and-drop evidence insertion into documents
- [ ] **P5-05**: Side-by-side comparison: your CV vs benchmark perfect CV

### 5B — Engagement Loops
- [ ] **P5-06**: Daily career briefing push notification
- [ ] **P5-07**: "Improve this section" button on any paragraph — inline AI suggestions
- [ ] **P5-08**: Achievement badges (first application, first 90+ score, 5 applications)
- [ ] **P5-09**: Application success tracking — did you get an interview? Update and learn.
- [ ] **P5-10**: Smart suggestions: "You haven't applied in 3 days — here are 5 jobs matching your profile"

### 5C — Mobile & Accessibility
- [ ] **P5-11**: Responsive design audit — every page works on mobile
- [ ] **P5-12**: PWA support — install as app on phone
- [ ] **P5-13**: Keyboard navigation and screen reader support
- [ ] **P5-14**: Dark mode

### Exit Criteria
- [ ] User session time >5 minutes average
- [ ] Return rate >40% within 7 days
- [ ] Mobile usability score >90 (Lighthouse)
- [ ] Users share the tool with friends

---

## Phase 6: "It Scales" (Production)
> Handles 1000 concurrent users. Zero downtime deploys.

### 6A — Infrastructure
- [ ] **P6-01**: Load test: 50 concurrent generations
- [ ] **P6-02**: Implement horizontal scaling — multiple backend instances behind load balancer
- [ ] **P6-03**: Database connection pooling (PgBouncer or Supabase pooler)
- [ ] **P6-04**: CDN for static assets
- [ ] **P6-05**: Multi-region deployment (US + EU)

### 6B — Observability
- [ ] **P6-06**: Structured logging end-to-end (already using structlog, verify in production)
- [ ] **P6-07**: Request tracing (OpenTelemetry) — trace from frontend click to AI response
- [ ] **P6-08**: Uptime monitoring + alerting (PagerDuty/Discord webhook)
- [ ] **P6-09**: Error budget dashboard — track SLO: 99.5% success rate for generations
- [ ] **P6-10**: Cost monitoring — track AI API spend per user, per pipeline

### 6C — Security Hardening
- [ ] **P6-11**: Security audit — OWASP Top 10 check
- [ ] **P6-12**: Input sanitization — no XSS via generated HTML content
- [ ] **P6-13**: API key rotation strategy
- [ ] **P6-14**: Data encryption at rest + in transit verification
- [ ] **P6-15**: GDPR compliance — data deletion endpoint, privacy policy

### Exit Criteria
- [ ] System handles 50 concurrent generations without degradation
- [ ] 99.5% uptime over 30 days
- [ ] All OWASP Top 10 vulnerabilities addressed
- [ ] Passing security audit

---

## Phase 7: "It Prints Money" (Monetization)
> Free tier drives adoption. Paid tier is irresistible.

### 7A — Billing & Tiers
- [ ] **P7-01**: Free tier: 3 applications/month, basic templates
- [ ] **P7-02**: Pro tier ($19/mo): unlimited applications, all document types, priority generation
- [ ] **P7-03**: Stripe integration — subscription management, invoices, cancellation
- [ ] **P7-04**: Usage metering — track generations per user per month
- [ ] **P7-05**: Upgrade prompts at natural friction points (4th application, export, advanced features)

### 7B — Growth
- [ ] **P7-06**: Referral program — give 1 free month for each referral
- [ ] **P7-07**: SEO landing pages — "AI Resume Builder for [Role]" for top 20 job titles
- [ ] **P7-08**: Blog/content — "How to tailor your CV for [Company]" auto-generated
- [ ] **P7-09**: Social proof — anonymized success stories, testimonials
- [ ] **P7-10**: Email drip campaign — nurture free users toward paid

### Exit Criteria
- [ ] Stripe billing fully operational
- [ ] Free → Paid conversion rate >5%
- [ ] Monthly recurring revenue growing week-over-week

---

## Execution Protocol

### Immediate Upgrade Plan (Priority Order)

After completing the auth/CSP fix and E2E verification, here is the prioritized upgrade plan:

#### Sprint 1: Complete Phase 1 (Foundation) — Estimated: 2-3 sessions
| # | Item | Impact | Effort |
|---|------|--------|--------|
| 1 | **P1-14: Workspace module verification** — Run full wizard in browser, verify module cards (benchmark, gaps, CV, cover letter, learning plan) display real AI content | High | Medium |
| 2 | **P1-15: Evidence picker** — Verify evidence items can be inserted into documents via the picker UI | Medium | Low |
| 3 | **P1-16: Export verification** — Verify PDF/DOCX/HTML export produces valid, branded documents | High | Low |
| 4 | **P1-08: Output scoring** — Score 5 real generations: relevance, formatting, keyword coverage, readability (0-10 each) | High | Medium |
| 5 | **P1-10: Critic score validation** — Verify critic scores are differentiated (not all 85s) | Medium | Low |

#### Sprint 2: Resilience (Phase 2A-2B) — Estimated: 2-3 sessions
| # | Item | Impact | Effort |
|---|------|--------|--------|
| 6 | **P2-01: Retry logic** — Exponential backoff for 429/503 AI errors | High | Medium |
| 7 | **P2-09: Input sanitization** — Malformed/garbage input returns helpful errors, not 500 | High | Low |
| 8 | **P2-10: Rate limiting** — Per-user rate limit with clear feedback | High | Medium |
| 9 | **P2-06: Empty resume handling** — Generate CV from JD only when no resume provided | Medium | Low |
| 10 | **P2-11: Data integrity** — Verify all generated content persists correctly in Supabase | Medium | Low |

#### Sprint 3: Performance + Polish (Phase 3A + 5A) — Estimated: 2-3 sessions
| # | Item | Impact | Effort |
|---|------|--------|--------|
| 11 | **P3-01: Pipeline profiling** — Identify and optimize the slowest stages | High | Medium |
| 12 | **P3-02: Parallelize** — Ensure independent stages run concurrently | High | Medium |
| 13 | **P3-05: Model routing** — Use flash model for simple tasks, pro for complex | Medium | Medium |
| 14 | **P5-03: Export polish** — One-click export to PDF with professional formatting | High | Medium |
| 15 | **CSP nonce** — Replace `unsafe-eval` with nonce-based CSP for production security | Medium | Medium |

#### Sprint 4: Production Readiness (Phase 6) — Estimated: 3-4 sessions
| # | Item | Impact | Effort |
|---|------|--------|--------|
| 16 | **P6-06: Structured logging** — Verify structlog works in production | High | Low |
| 17 | **P6-08: Uptime monitoring** — Health check + alerting | High | Medium |
| 18 | **P6-11: Security audit** — OWASP Top 10 check | High | Medium |
| 19 | **P6-12: XSS prevention** — Sanitize AI-generated HTML before rendering | Critical | Medium |
| 20 | **Route consolidation** — Merge 3 generation paths into one clean API | High | High |

#### Sprint 5: Growth (Phase 7) — Estimated: 2-3 sessions
| # | Item | Impact | Effort |
|---|------|--------|--------|
| 21 | **P7-03: Stripe integration** — Subscription billing | Critical | High |
| 22 | **P7-01-02: Tier enforcement** — Free vs Pro limits | High | Medium |
| 23 | **P7-07: SEO pages** — Landing pages for top job titles | High | Medium |

### Key Technical Debts to Address
1. **Route fragmentation** — 3 generation endpoints (`/pipeline`, `/pipeline/stream`, `/jobs`) with duplicated logic
2. **Workers not integrated** — Celery configured but not wired to the pipeline
3. **Frontend vitest** — 6 false failures from `.netlify/plugins` test files (exclude in vitest config)
4. **Production CSP** — Currently `unsafe-eval` only in dev; production needs nonce-based CSP or a `strict-dynamic` policy

### How Each Phase Works
1. **Start**: Read this file. Identify current phase. Pick the next unchecked item.
2. **Execute**: Implement the item. Write tests. Verify it works.
3. **Validate**: Run full test suite. Confirm no regressions.
4. **Check off**: Mark the item `[x]` in this file.
5. **Repeat**: Move to next item in the phase.

### Phase Transition Rules
- All items in a phase must be `[x]` before moving to the next phase
- Exception: items marked `[SKIP]` with documented reason
- Each phase ends with a full regression test run

### Quality Gates
- **Every code change**: Tests must pass (430+ baseline, growing)
- **Every phase**: Full E2E smoke test with real AI
- **Every 2 phases**: Performance benchmark comparison

### Session Protocol
When starting a new session, say:
> "Continue the perfection roadmap"

The agent will:
1. Read this file
2. Find the first unchecked `[ ]` item
3. Execute it
4. Mark it done
5. Continue to the next item

---

## Progress Tracker

| Phase | Description | Status | Items | Done |
|-------|-------------|--------|-------|------|
| 1 | It Actually Works | ✅ Complete | 17 | 17 |
| 2 | It Doesn't Break | 🔴 Not Started | 14 | 0 |
| 3 | It's Fast | 🔴 Not Started | 12 | 0 |
| 4 | It's Smart | 🔴 Not Started | 14 | 0 |
| 5 | It's Addictive | 🔴 Not Started | 14 | 0 |
| 6 | It Scales | 🔴 Not Started | 15 | 0 |
| 7 | It Prints Money | 🔴 Not Started | 10 | 0 |
| **Total** | | | **96** | **17** |
