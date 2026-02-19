# HireStack AI

A career intelligence + job application workspace that helps candidates build compelling application packages by analyzing their profile against an ideal benchmark.

## Features

- **Evidence Vault**: Store links/files proving skills (reusable across applications)
- **AI Pipeline**: Benchmark → gaps → roadmap → tailored CV/cover letter/portfolio
- **Workspace**: Module cards, regeneration, version history, exports (PDF/DOCX/PNG/ZIP)
- **Realtime**: Instant updates via Supabase Realtime (with polling fallback)

## Tech Stack

### Frontend
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- shadcn/ui + Radix UI
- TipTap editor
- Supabase Auth + Storage + Realtime

### Backend
- FastAPI
- Supabase JWT verification + PostgREST access (via `SUPABASE_SERVICE_ROLE_KEY`)
- Structured logging (structlog)
- Redis + Celery (optional background jobs; scaffolding present)

### AI Engine
- Gemini (Google AI Studio) via `google-genai`
- Optional OpenAI fallback (provider switch via `AI_PROVIDER`)
- Chained prompt architecture under `ai_engine/`

## Project Structure

```
HireStack AI/
├── frontend/           # Next.js 14 application
├── backend/            # FastAPI application
├── ai_engine/          # AI prompt chains
├── workers/            # Celery workers
├── supabase/           # Local Supabase project (migrations + seed)
├── infra/              # Docker configs
└── docs/               # Documentation
```

## Getting Started

### Prerequisites

- Node.js 20+
- Python 3.11+ (recommended)
- Docker (required for `supabase start`)
- Supabase CLI (`supabase`) installed and on PATH

### Environment Setup

1. Start Supabase locally (runs Postgres, Auth, Storage, Realtime, Studio):
   ```bash
   cd supabase
   supabase start
   ```

2. Sync Supabase local credentials into `backend/.env` and `frontend/.env.local`:
   ```bash
   ./scripts/dev/sync_supabase_env.sh
   ```
   - By default this uses `http://127.0.0.1:54321` (avoids IPv6 `localhost` quirks in some browsers).
   - To force localhost instead: `HIRESTACK_SUPABASE_HOST=localhost ./scripts/dev/sync_supabase_env.sh`

3. Set your Gemini API key securely (input is hidden; updates `backend/.env`):
   ```bash
   ./scripts/dev/set_gemini_key.sh
   ```

4. Install deps:
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

   cd ../frontend
   npm install
   ```

### Running the Application

**Development Mode:**

1. Start the backend:
   ```bash
   cd backend
   python3 -m uvicorn main:app --reload --port 8000
   ```

2. Start the frontend:
   ```bash
   cd frontend
   npm run dev:3002
   ```

3. (Optional) Start Celery worker (if you enable background processing):
   ```bash
   cd backend
   celery -A workers.celery_app worker --loglevel=info
   ```

### Helpful flags

- Realtime debug logging (client):
  - `NEXT_PUBLIC_REALTIME_DEBUG=1`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/generate/pipeline` | POST | Run the full AI pipeline (non-streaming) |
| `/api/generate/pipeline/stream` | POST | Run the full AI pipeline (SSE streaming) |

## Deployment

This repo currently assumes a self-hosted setup where secrets are provided via environment variables.
Recommended production approach:
- Frontend on a modern platform (e.g. Vercel/Netlify)
- Backend on a container platform (e.g. Render/Fly/Railway)
- Supabase hosted for Postgres/Auth/Storage/Realtime

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 14)                        │
│  /login → /dashboard → /new → /applications/:id → /evidence        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                            │
│  Auth │ Generate (SSE) │ Export │ Analytics (WIP)                  │
└─────────────────────────────────────────────────────────────────────┘
                    │                           │
          ┌─────────┴─────────┐                 │
          ▼                   ▼                 ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   AI ENGINE      │ │   DATABASE       │ │   WORKERS        │
│ Gemini/OpenAI    │ │ Supabase Postgres│ │ Celery/Redis     │
│ Prompt Chains    │ │ + Realtime/Store │ │ Async Tasks      │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

## License

MIT License - see LICENSE file for details
