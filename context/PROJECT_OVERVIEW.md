---
title: Project Overview
last_synced: 2026-05-08
watch_paths:
  - README.md
  - frontend/package.json
  - backend/requirements.txt
  - pyproject.toml
canonical_sources:
  - README.md
  - docs/PROJECT_JOURNAL.md
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#1-architectural-principles
update_when:
  - product positioning shifts
  - tech stack row changes (frontend framework, primary AI provider, hosting)
  - new headline feature ships
  - new persona/audience targeted
---

# HireStack AI — Project Overview

> Authoritative narrative of what we build, who it serves, and the constraints
> that shape every architectural choice. For the engineering constitution see
> [`docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`](../docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md).

---

## TL;DR — 10 lines

1. HireStack AI is a multi-tenant career-intelligence platform for job seekers
   and recruitment agencies.
2. The differentiator is a **streaming six-agent AI pipeline** (Atlas, Cipher,
   Quill, Forge, Sentinel, Nova) that produces a complete tailored application
   pack — CV, cover letter, portfolio, learning plan, ATS scan — in real time
   on a Mission-Control UI.
3. Production stack: **Next.js 14** (Netlify) + **FastAPI / Python 3.13**
   (Railway) + **Supabase Postgres** + **Redis Streams** + **Temporal Cloud**
   for durability + **Google Gemini 2.5 Pro** with **Anthropic Claude** as
   cascade tail (flag `ff_anthropic_provider`).
4. We are a **modular monolith with four deployables** — `api`, `worker`,
   `scheduler`, `temporal_worker` — plus the `web` frontend. No Kubernetes,
   no Kafka, no microservices beyond these four.
5. Data plane is **Postgres-of-record + Redis-bus**, with all multi-tenant
   tables enforcing **PostgreSQL RLS keyed on `org_id`** (64/64 user-data
   tables today). RLS coverage is a CI-enforced invariant.
6. Five architectural principles govern every decision: **P1 Durability >
   throughput · P2 Contracts > coordination · P3 Cells > clusters · P4 Boring
   infra, opinionated runtime · P5 Observability is build-time.** See
   blueprint §1.
7. Pricing tiers: Free / Pro (individual) and Team / Enterprise (agency).
   Enterprise gets dedicated cells; EU customers get an EU cell (GDPR).
   Tier-to-cell mapping is in blueprint §5.4.
8. Live URLs: <https://hirestack.tech> (frontend on Netlify) and
   <https://hirestack-ai-production.up.railway.app> (backend on Railway).
   E2E test user: `e2e-test@hirestack.local` / `E2ETestPass!2026`.
9. The codebase has **251 backend test files**, **61 Supabase migrations**,
   **25 ADRs**, **6 runbooks**, and ships behind **12 production feature
   flags** registered in `config/feature_flags.yaml` with mandatory sunset
   dates enforced by CI.
10. We explicitly **do not** ship: K8s, Kafka/NATS, GraphQL/gRPC, event
    sourcing, multi-region deployments (in Q1), or any microservice beyond
    the four deployables. See blueprint §17.

---

## Mission and product

HireStack AI helps people who are trying to land a job run that effort as a
structured operation. The classical workflow — write a CV, hand-tailor a
cover letter, hope for an interview — is replaced by an AI pipeline that:

1. **Researches the target company** (Recon agent) — public web, news,
   tech-stack signals, hiring patterns.
2. **Parses the candidate's resume** (Atlas) and benchmarks them against the
   "ideal" hire for that role.
3. **Detects gaps** (Cipher) between candidate and benchmark.
4. **Drafts tailored documents** (Quill) — CV, cover letter, learning plan.
5. **Builds portfolio assets** (Forge) — personal statement, project deck,
   bespoke artifacts.
6. **Inspects quality** (Sentinel) — ATS compliance, factual accuracy,
   evidence backing for every claim.
7. **Assembles and ships** (Nova) — final pack, ready for export.

Each agent streams progress over Server-Sent Events to a Mission-Control UI
inspired by Replit and Cursor — collapsible per-agent log panels, timing
badges, and a real-time progress bar. This visible reasoning is the product;
it is what users tell us they remember.

### Audiences

| Audience | What they get | Where it lives |
|---|---|---|
| Individual job-seeker (Free / Pro) | Self-service generation, ATS scan, interview prep, salary coach | `frontend/src/app/(dashboard)/**` |
| Recruitment agency (Team) | Multi-user org, candidate Kanban, bulk operations | `frontend/src/app/(dashboard)/candidates/**`, `orgs/**` |
| Enterprise customer | Dedicated cell, SSO/SCIM (Stage B), audit log, SLAs | (cell architecture per blueprint §5) |
| API integrator (Stage B) | REST + OpenAPI, rate-limited per key | `backend/app/api/routes/api_keys.py` |

### Headline features (registered surfaces)

The dashboard pages under `frontend/src/app/(dashboard)/` are the canonical
list of user-facing surfaces. Today: ab-lab, api-keys, applications,
assignments, ats-scanner, batch, benchmark, builder, candidates, career,
career-analytics, consultant, dashboard, evidence, export, gaps, insights,
interview, job-board, knowledge, learning, new, nexus, ppt, salary, settings,
skills, tracked-companies, upload. Each is wired to a backend route family of
the same name in `backend/app/api/routes/`.

---

## Tech stack — current

| Layer | Choice | Version pin | Why |
|---|---|---|---|
| Frontend framework | Next.js (App Router) | `14.1.0` | RSC + streaming, mature ecosystem, Netlify-friendly |
| UI primitives | Radix + shadcn/ui + Tailwind | latest | Accessible primitives, no design-system rebuild |
| Frontend state | TanStack Query v5 + React hooks | `^5.17.0` | Caches the entire REST surface; SSE on top |
| Editor | TipTap | `^2.1.16` | Rich text for cover letters / personal statements |
| Frontend hosting | Netlify | n/a | Free CDN, simple deploys |
| Backend framework | FastAPI | `>=0.115,<0.130` | Async, Pydantic-native, OpenAPI for free |
| Backend language | Python | `3.11` (CI) / `3.13` (local) | TD-5 — see context/TECH_DEBT.md |
| Validation | Pydantic v2 + jsonschema | `>=2.10` / `>=4.21` | Same model used for events and APIs |
| Backend hosting | Railway | n/a | Simple multi-process, free tier sufficient for Stage A |
| Database | Supabase Postgres | n/a | RLS, Realtime, Storage all in one |
| Async / queue | Redis Streams (via `redis>=5.0,<7.0`) | n/a | Single dependency, supports outbox + cache + slowapi store |
| Workflow engine | Temporal Cloud | `temporalio>=1.7,<2.0` | Durability for long generations |
| Primary LLM | Google Gemini 2.5 Pro | `google-genai>=1.0,<2.0` | Fast, cheap, high-quality structured output |
| Secondary LLM | Anthropic Claude | `anthropic>=0.40,<1.0` | Cascade tail behind `ff_anthropic_provider` |
| Tertiary LLM (planned) | OpenAI | `openai>=1.30,<2.0` | Stage B, not yet wired |
| LLM observability | Langfuse | `langfuse>=2.40,<3.0` | Per-prompt tracing |
| Tracing / metrics | OpenTelemetry → Grafana / Honeycomb | `opentelemetry-* >=1.25` | Standard pipeline |
| Logging | structlog | `>=24.1,<26.0` | JSON logs to stdout |
| Errors | Sentry | `sentry-sdk[fastapi]>=2.0,<3.0` | Multi-process |
| Rate limiting | slowapi (Redis-backed) | `>=0.1.9,<0.2` | 246 `@limiter.limit` decorators across 46/48 route files |
| HTML sanitisation | nh3 | `>=0.2,<0.4` | Defense for AI-generated HTML |
| HTTP client | httpx | `>=0.24,<1.0` | Same client across SDKs |
| Stripe | stripe | `>=8.0,<13.0` | Billing wired but partially deferred |
| Mobile (Android) | Native + Kotlin | n/a | `mobile/android/` |

The pinned ranges in [`backend/requirements.txt`](../backend/requirements.txt)
are intentional: minimum floors close known CVEs, maximum ceilings prevent
silent breakage. There is no lockfile yet — see TD-4.

---

## What we are explicitly NOT building

Reproduced from blueprint §17 and `docs/ARCHITECTURE.md` §12 because every
new contributor reaches for one of these:

- **No Kubernetes.** Fly.io / Railway machines + Vercel/Netlify until 100K
  MAU. K8s is dramatic complexity that adds nothing at our scale.
- **No Kafka / NATS.** Redis Streams through Stage B at minimum. Kafka added
  as a *parallel* bus only when Stage B starts (analytics + customer
  webhooks).
- **No microservices** beyond `api`, `worker`, `scheduler`, `temporal_worker`,
  `web`. Modular monolith with `import-linter`-enforced contexts.
- **No GraphQL / gRPC** at the public surface. REST + OpenAPI only. gRPC is
  used internally between the AI runtime and the L2 tool-runner sidecar
  (m11-pr44).
- **No event sourcing.** Outbox pattern + idempotent consumers, full stop.
- **No multi-region** in Q1. Single region (us-east). EU cell is Stage B.

---

## Operating model

- **Engineering team:** small (founder-led). Single on-call rotation gated by
  hiring a second engineer (open item in blueprint §25.3).
- **Branch strategy:** stacked PRs on top of `main`, named
  `m<milestone>-pr<NN>-<slug>`. Each PR is ≤ 600 LOC net (documentation PRs
  exempt — see this PR for the precedent).
- **Commit messages:** heredoc only (`cat > /tmp/msg.txt <<'EOF' ... EOF;
  git commit -F /tmp/msg.txt`). Plain ASCII; no em-dashes; no backticks
  inside `-m "..."` strings (zsh interprets them as command substitution).
- **Release cadence:** push-based — `main` auto-deploys to staging, manual
  promote to production. Every change is feature-flagged; default off unless
  explicitly stated.
- **Definition of done:** all CI gates green + matching context file updated
  + matching runbook updated (if a new failure mode introduced) +
  observability wired (per blueprint §13.2).

---

## Roadmap snapshot

| Stage | Scale target | Focus | Exit gate |
|---|---|---|---|
| A (today → 10×) | ~50K generations / day | Close all P0 fixes; ship per-stage Temporal; wire SSE resumption | All P0 closed; SLO instrumentation live; DR drill green |
| B (10× → 100×) | ~5M generations / day | Cell architecture; realtime gateway; Kafka parallel bus; SSO/SCIM; SOC 2 II | First enterprise on dedicated cell; EU cell live |
| C (100× → 1000×) | hyperscale | Active-active cells; vector store off pgvector; cold tier on Iceberg | $50M+ ARR; multi-region paid customers |

Detail: [SCALABILITY_ROADMAP.md](SCALABILITY_ROADMAP.md) and
[`docs/architecture/SCALING_PHASES.md`](../docs/architecture/SCALING_PHASES.md).

---

## What is "done" today

P0 register status (blueprint §18):

- P0-1 partition rotation — **SHIPPED** (m7-pr27a)
- P0-2 in-process fallback gated — **SHIPPED** (m7-pr27b)
- P0-3 ACK-on-success + DLQ — **SHIPPED** (m7-pr27c)
- P0-4 per-org $ cap + cascade breaker — **SHIPPED** (m12-pr08)
- P0-5 capability tokens + sandbox tiers — **SHIPPED** (m7-pr29)
- P0-6 idempotency middleware ON — **SHIPPED**
- P0-7 SSE Last-Event-ID resumption — **SHIPPED** (m12-pr05)

P1 register: 14 of 15 SHIPPED. P1-13 (realtime gateway extraction)
DEFERRED — gates on SSE > 1000 concurrent.

The remaining open work for Stage A is in [TECH_DEBT.md](TECH_DEBT.md).

---

## Where to look next

| If you want to know… | Read |
|---|---|
| How a request becomes a generated CV | [ARCHITECTURE.md](ARCHITECTURE.md) → [AI_CONTEXT.md](AI_CONTEXT.md) |
| Which DB tables exist and who owns them | [DATABASE_CONTEXT.md](DATABASE_CONTEXT.md) |
| Which routes exist and which middleware they go through | [BACKEND_CONTEXT.md](BACKEND_CONTEXT.md), [API_CONTEXT.md](API_CONTEXT.md) |
| What the frontend looks like and how it streams | [FRONTEND_CONTEXT.md](FRONTEND_CONTEXT.md) |
| What might break at 10× | [SCALABILITY_ROADMAP.md](SCALABILITY_ROADMAP.md) |
| What we're carrying that isn't broken yet | [TECH_DEBT.md](TECH_DEBT.md) |

---

## Update protocol

This file is rewritten when **any** of the following happens:

- New tech-stack row (e.g. swap UI library, add new LLM provider).
- New audience tier (e.g. add per-developer self-serve API tier).
- Headline feature ships or is removed (e.g. add Slack integration).
- Live URL or hosting provider changes.
- Stage exit gate is met (advance the roadmap snapshot).
