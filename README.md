<p align="center">
  <img src="https://img.shields.io/badge/HireStack-AI-6366f1?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTEyIDJMMiA3bDEwIDUgMTAtNS0xMC01eiIvPjxwYXRoIGQ9Ik0yIDE3bDEwIDUgMTAtNSIvPjxwYXRoIGQ9Ik0yIDEybDEwIDUgMTAtNSIvPjwvc3ZnPg==&logoColor=white" alt="HireStack AI" height="40"/>
</p>

<h1 align="center">HireStack AI</h1>

<p align="center">
  <strong>AI-Powered Career Intelligence Platform</strong><br/>
  The world's most comprehensive application builder — from resume parsing to interview prep, powered by Gemini AI agents.
</p>

<p align="center">
  <a href="https://hirestack.tech">Live Demo</a> &bull;
  <a href="#features">Features</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#getting-started">Getting Started</a> &bull;
  <a href="#deployment">Deployment</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-14-black?style=flat-square&logo=next.js" alt="Next.js"/>
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/TypeScript-5.0-3178C6?style=flat-square&logo=typescript" alt="TypeScript"/>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3FCF8E?style=flat-square&logo=supabase" alt="Supabase"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License"/>
</p>

---

## What is HireStack AI?

HireStack AI is a full-stack career intelligence platform that transforms how professionals build job applications. Instead of manually crafting resumes and cover letters, HireStack deploys a swarm of specialized AI agents that analyze your profile, research the target company, identify skill gaps, and generate a complete, tailored application package — all in real-time with a streaming mission-control interface.

**For job seekers:** Sign up, upload your resume, paste a job description, and watch 6 AI agents build a world-class application with CV, cover letter, portfolio, learning plan, and more.

**For recruitment agencies (Enterprise):** Manage candidates at scale with organization workspaces, team roles, candidate pipelines, and bulk operations.

---

## Features

### Core Platform

| Feature | Description |
|---------|-------------|
| **Application Builder** | 6-agent AI pipeline: Atlas (Resume Analyst), Cipher (Gap Detector), Quill (Document Architect), Forge (Portfolio Builder), Sentinel (Quality Inspector), Nova (Final Assembler) |
| **Career Nexus** | Career identity hub — upload resume, connect LinkedIn/GitHub/Twitter, auto-import skills, AI profile analysis |
| **ATS Scanner** | Multi-pass ATS analysis with keyword matching, readability scoring, format analysis, and actionable rewrite suggestions |
| **Interview Prep** | AI interview simulator with behavioral, technical, and case modes. Real-time feedback, STAR scoring, timer |
| **Salary Coach** | Market-data-driven salary negotiation with regional benchmarks, counter-offer scripts, and negotiation strategies |
| **Evidence Vault** | Proof library for storing certifications, projects, awards — reusable across all applications |
| **Career Lab** | Skill sprints and learning paths tailored to your career gaps |
| **Job Board** | AI-curated job discovery with match scoring |
| **Daily Learn** | Gamified daily skill challenges with streaks and XP |
| **A/B Lab** | Compare document variants side-by-side to optimize application quality |
| **Analytics** | Track application success rates, skill growth, and career trajectory |

### AI Agent Pipeline (Mission Control)

The application builder uses a streaming mission-control interface inspired by Replit/Cursor, showing 6 named AI agents working in real-time:

```
Atlas (Resume Analyst)     → Parses resume, builds candidate benchmark
Cipher (Gap Detector)      → Analyzes skill gaps against job requirements
Quill (Document Architect) → Generates CV, cover letter, learning plan
Forge (Portfolio Builder)  → Builds personal statement and portfolio
Sentinel (Quality Inspector) → Validates document quality and ATS compliance
Nova (Final Assembler)     → Packages complete application
```

Each agent streams its progress with collapsible log panels, timing badges, and a real-time progress bar.

### Company Intelligence

Before building documents, the platform gathers company intel:
- Company overview, culture, and values
- Tech stack and engineering practices
- Recent news and funding
- Glassdoor-style interview insights
- Competitor landscape
- Hiring patterns and team structure

This intelligence is woven into every generated document for maximum relevance.

### Adaptive Document Discovery

The platform doesn't just generate fixed documents — it analyzes the job type and discovers additional required documents:

- **Standard set:** CV, Cover Letter, Portfolio, Personal Statement, Learning Plan
- **Discovered extras:** Research Statement (academic), Case Study (consulting), Teaching Philosophy (education), Security Clearance forms, Writing Samples, etc.

### Enterprise Features

| Feature | Description |
|---------|-------------|
| **Multi-tenant Organizations** | Create org accounts, invite team members, assign roles (owner/admin/recruiter/member) |
| **Candidate Pipeline** | Kanban-style candidate tracking (New → Screening → Interview → Offer → Placed) |
| **Team Analytics** | Organization-wide stats, member activity, placement rates |
| **API Platform** | RESTful API with rate limiting for third-party integrations |
| **Audit Logs** | Track all actions for compliance |
| **Audit Logs** | Track all actions for compliance |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 14 + TypeScript)                │
│                                                                          │
│  Landing ─── Auth ─── Dashboard ─── New Application ─── Workspace       │
│  Career Nexus ─── ATS Scanner ─── Interview ─── Salary Coach            │
│  Evidence Vault ─── Career Lab ─── Job Board ─── Daily Learn            │
│  Analytics ─── Settings (Org/Members/Audit)                              │
│  404                                                                      │
│                                                                          │
│  UI: shadcn/ui + Tailwind CSS + Framer Motion                           │
│  State: React hooks + Supabase Realtime                                  │
│  Auth: Supabase Auth (email/password + Google + GitHub OAuth)           │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI + Python)                        │
│                                                                          │
│  Routes: auth, profile, generate, ats-scan, interview, salary,          │
│          evidence, career-lab, job-board, daily-learn, ab-lab,           │
│          analytics, candidates, organizations                            │
│                                                                          │
│  Services: ProfileService, InterviewService, SalaryService,             │
│            EvidenceService, CandidateService, OrgService                │
│                                                                          │
│  Middleware: CORS, rate limiting, JWT verification, org context          │
└──────────────────────────────────────────────────────────────────────────┘
                    │                           │
          ┌─────────┴──────────┐                │
          ▼                    ▼                ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   AI ENGINE      │  │   DATABASE       │  │   WORKERS        │
│                  │  │                  │  │                  │
│  Gemini 2.5      │  │  Supabase        │  │  Celery/Redis    │
│  Flash           │  │  PostgreSQL      │  │  (background     │
│                  │  │  35+ tables      │  │   processing)    │
│                  │  │  + Auth          │  │                  │
│                  │  │  + Storage       │  │                  │
│                  │  │  + Realtime      │  │                  │
│  Chains:         │  │                  │  │                  │
│  ├─ RoleProfiler │  │  RLS policies    │  │                  │
│  ├─ GapAnalyzer  │  │  for multi-      │  │                  │
│  ├─ DocGenerator │  │  tenant          │  │                  │
│  ├─ ATSScanner   │  │  isolation       │  │                  │
│  ├─ CompanyIntel │  │                  │  │                  │
│  ├─ Discovery    │  │                  │  │                  │
│  └─ Benchmark    │  │                  │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### AI Chains

All inference is powered by Gemini 2.5 Flash via `ai_engine.client.AIClient`.

Specialized chains:
- **RoleProfilerChain** — Resume parsing with 60+ skill normalizations
- **GapAnalyzerChain** — Skill gap detection against job requirements
- **DocGeneratorChain** — Tailored document generation (CV, cover letter, etc.)
- **ATSScannerChain** — Multi-pass ATS compliance analysis
- **CompanyIntelChain** — Web scraping + AI analysis of target companies
- **DiscoveryChain** — Job-type-aware document requirement discovery
- **BenchmarkChain** — Ideal application benchmark generation

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Framer Motion, Lucide Icons |
| **Backend** | FastAPI, Python 3.11+, Pydantic, structlog |
| **Database** | Supabase (PostgreSQL + Auth + Storage + Realtime) |
| **AI Models** | Google Gemini 2.5 Flash |
| **Hosting** | Netlify (frontend), Railway (backend) |
| **CI/CD** | GitHub Actions |
| **Containerization** | Docker (multi-stage builds) |

---

## Project Structure

```
HireStack AI/
├── frontend/                # Next.js 14 application
│   ├── src/
│   │   ├── app/            # App Router pages
│   │   │   ├── (dashboard)/ # Authenticated pages
│   │   │   ├── auth/       # Auth callbacks
│   │   │   ├── login/      # Login page
│   │   │   └── page.tsx    # Landing page
│   │   ├── components/     # Shared components
│   │   └── lib/            # Utilities, API client, auth
│   └── public/             # Static assets
│
├── backend/                 # FastAPI application
│   └── app/
│       ├── api/routes/     # API route handlers
│       ├── core/           # Database, config, middleware
│       └── services/       # Business logic services
│
├── ai_engine/               # AI prompt chains
│   ├── client.py           # Gemini AIClient
│   └── chains/             # Specialized AI chains
│
├── supabase/                # Database
│   └── migrations/         # SQL migrations (35+ tables)
│
├── infra/                   # Docker configs
│   ├── Dockerfile.frontend
│   └── Dockerfile.backend
│
├── .github/workflows/       # CI/CD
│   └── ci.yml
│
└── scripts/                 # Development utilities
```

---

## Getting Started

### Prerequisites

- **Node.js 20+** and **npm**
- **Python 3.11+**
- **Supabase account** ([supabase.com](https://supabase.com))
- **Gemini API key** ([aistudio.google.com](https://aistudio.google.com))

### 1. Clone and Install

```bash
git clone https://github.com/BalaShankar9/hirestack-ai.git
cd hirestack-ai

# Frontend
cd frontend && npm install && cd ..

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

### 2. Configure Environment

**Backend** (`backend/.env`):
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
GEMINI_API_KEY=your-gemini-api-key
```

**Frontend** (`frontend/.env.local`):
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Run Database Migrations

Apply all migrations via the Supabase Dashboard SQL editor, or use the CLI:
```bash
supabase db push
```

### 4. Start Development Servers

```bash
# Terminal 1: Backend
cd backend && source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

Visit **http://localhost:3000** to start using HireStack AI.

---

## Deployment

### Production Stack

| Service | Platform | Purpose |
|---------|----------|---------|
| Frontend | **Netlify** | Static + SSR hosting |
| Backend | **Railway** | Container hosting |
| Database | **Supabase** | Managed PostgreSQL |
| AI | **Google AI Studio** (Gemini) | AI inference |

### Deploy with Docker

```bash
# Build frontend
docker build -f infra/Dockerfile.frontend -t hirestack-frontend .

# Build backend
docker build -f infra/Dockerfile.backend -t hirestack-backend .
```

### Environment Variables for Production

See `backend/.env.example` and `frontend/.env.local.example` for all required variables.

---

## API Endpoints

### Core
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with uptime and version |
| `/api/generate/pipeline/stream` | POST | Full AI pipeline (SSE streaming) |
| `/api/generate/pipeline` | POST | Full AI pipeline (non-streaming) |

### Profile & Career
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/profile/upload` | POST | Upload and parse resume |
| `/api/profile/me` | GET | Get current user profile |
| `/api/profile/connect/{platform}` | POST | Connect social profiles |

### Features
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ats/scan` | POST | ATS compliance scan |
| `/api/interview/start` | POST | Start interview session |
| `/api/interview/answer` | POST | Submit answer for AI feedback |
| `/api/salary/analyze` | POST | Salary analysis |
| `/api/career-lab/sprints` | GET | Get available skill sprints |
| `/api/job-board/search` | GET | Search job listings |
| `/api/daily-learn/challenge` | GET | Get daily challenge |

### Enterprise
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/organizations` | POST | Create organization |
| `/api/organizations/{id}/members` | GET/POST | Manage team members |
| `/api/candidates` | GET/POST | Candidate pipeline CRUD |
| `/api/analytics/dashboard` | GET | Dashboard statistics |

---

## Contributing

We welcome contributions! Please read our contributing guidelines before submitting PRs.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with AI, for ambitious professionals.<br/>
  <a href="https://hirestack.tech">hirestack.tech</a>
</p>
