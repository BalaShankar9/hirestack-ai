# Contributing to HireStack AI

Welcome! This guide gets you up and running locally and explains the workflow for contributing to the platform.

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Local Setup](#local-setup)
3. [Development Workflow](#development-workflow)
4. [Code Standards](#code-standards)
5. [Testing](#testing)
6. [Submitting a PR](#submitting-a-pr)
7. [Architecture Overview](#architecture-overview)

---

## Prerequisites

| Tool | Minimum Version |
|------|----------------|
| Node.js | 20.x |
| Python | 3.11+ |
| Docker | 24+ |
| Git | 2.40+ |

---

## Local Setup

### 1. Clone the repo
```bash
git clone https://github.com/BalaShankar9/hirestack-ai.git
cd hirestack-ai
```

### 2. Start local services
```bash
docker-compose up -d   # starts Supabase (PostgreSQL) + Redis locally
```

### 3. Frontend
```bash
cd frontend
cp .env.example .env.local   # fill in NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
npm ci
npm run dev:3000
# → http://localhost:3000
```

### 4. Backend
```bash
cd backend
cp .env.example .env         # fill in SUPABASE_*, GEMINI_API_KEY
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# → http://localhost:8000/docs
```

### 5. AI Engine (optional — runs inside backend)
The AI engine is imported by the backend and shares its Python process.
Set `GEMINI_API_KEY` in `backend/.env` to enable generation endpoints.

---

## Development Workflow

```
main (protected) ← squash-merge ← feature/your-branch
```

1. Create a branch: `git checkout -b feat/your-feature` or `fix/your-fix`
2. Make changes in small, logical commits
3. Run linters and tests (see below) before pushing
4. Open a PR against `main`
5. CI must pass before merge

---

## Code Standards

### Frontend (TypeScript / Next.js)
- **Strict TypeScript** — `"strict": true` in `tsconfig.json`. No `any` unless unavoidable.
- **ESLint** — `npm run lint` must produce 0 warnings
- **Tailwind** — use design tokens, not arbitrary values
- **Components** — keep under ~300 lines; extract hooks for business logic
- **API calls** — always go through `src/lib/api.ts`; never call the backend directly from components

### Backend (Python / FastAPI)
- **Pydantic models** for all request/response bodies
- **`validate_uuid()`** on all `{id}` path parameters
- **Decorator order:** `@limiter.limit(...)` MUST come before `@router.method(...)` — violating this silently disables rate limiting
- **ruff** — `ruff check . --select E,W,F --ignore E501` must pass
- **Response format** — use `success_response(data)` from `app/api/response.py`
- **Structured logging** — always `structlog.get_logger(...)`, never `print()`

### SQL / Migrations
- Migration file naming: `YYYYMMDDHHMMSS_descriptive_name.sql`
- Always include `-- Description:` comment at top of file
- Test migrations locally with `docker-compose` before committing
- Never edit existing migrations — add a new one

---

## Testing

### Frontend
```bash
cd frontend
npm test               # unit tests (Vitest)
npm run test:e2e       # E2E tests (Playwright) — requires running app
```

### Backend
```bash
cd backend
pytest tests/ -v --tb=short --ignore=tests/e2e
```

### Running everything
```bash
# From repo root
npm --prefix frontend test
cd backend && pytest tests/ -v --ignore=tests/e2e
```

---

## Submitting a PR

### Checklist
- [ ] `npm run lint` passes with 0 warnings
- [ ] `npx tsc --noEmit` passes
- [ ] `pytest tests/ -v` passes (backend)
- [ ] All new code has at least one test
- [ ] PR description explains the *why*, not just the *what*
- [ ] No `.env` files committed
- [ ] No hardcoded API keys or secrets

### PR Title Format
```
feat: short description of feature
fix: short description of bug fix
chore: dependency update / tooling
refactor: code restructure with no behaviour change
docs: documentation only
```

---

## Architecture Overview

```
┌─────────────────┐     HTTPS      ┌──────────────────┐
│  Next.js 14     │ ────────────>  │  FastAPI backend  │
│  (Vercel/       │ <────────────  │  (Railway)        │
│   Netlify)      │                └─────────┬────────┘
└─────────────────┘                          │
                                             │ service role
                                    ┌────────▼────────┐
                                    │  Supabase        │
                                    │  (PostgreSQL +   │
                                    │   RLS + Auth)    │
                                    └─────────┬────────┘
                                              │
                               ┌──────────────┴───────────┐
                               │                          │
                      ┌────────▼──────┐         ┌────────▼──────┐
                      │  AI Engine    │         │  Redis         │
                      │  (Gemini 2.5) │         │  (cache + queue│
                      │  circuit      │         │   + streams)   │
                      │  breaker)     │         └───────────────┘
                      └───────────────┘
```

### Key Principles
1. **Auth** — Supabase JWT, verified server-side on every request via `get_current_user()`
2. **Data isolation** — Supabase RLS ensures users can only access their own data
3. **AI calls** — All AI calls go through `ai_engine/agents/orchestrator.py` with circuit breaker
4. **Async jobs** — Long-running generation pushed to Redis Streams queue, polled via Firestore or SSE
5. **Observability** — Every request gets an `X-Request-ID`; all logs are structured JSON
