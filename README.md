# HireStack AI

A production-grade career intelligence and job application platform that helps candidates build compelling application packages by analyzing their profiles against ideal benchmarks.

## Features

- **Benchmark Generator**: Creates ideal candidate profiles for any job role
- **Gap Analyzer**: Compares user profiles against benchmarks with compatibility scoring
- **Career Consultant**: Generates personalized improvement roadmaps
- **Document Builder**: Creates tailored CVs, cover letters, and portfolios
- **Export Engine**: Exports documents as PDF/DOCX

## Tech Stack

### Frontend
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- ShadCN UI Components
- TipTap Editor
- React Query
- Firebase Auth

### Backend
- FastAPI
- Firebase Admin SDK (token verification)
- Firebase Firestore (database)
- Redis + Celery (optional background processing)

### AI Engine
- Claude API (Anthropic)
- Chained Prompt Architecture

## Project Structure

```
hirestack-ai/
├── frontend/           # Next.js 14 application
├── backend/            # FastAPI application
├── ai_engine/          # AI prompt chains
├── workers/            # Celery workers
├── database/           # Migrations and schema
├── infra/              # Docker configs
└── docs/               # Documentation
```

## Getting Started

### Prerequisites

- Node.js 20+
- Python 3.10+ (recommended)
- Firebase project (Auth + Firestore)
- Redis (optional, only if you run Celery)
- Anthropic API key

### Environment Setup

1. **Clone the repository**
   ```bash
   cd hirestack-ai
   ```

2. **Backend Setup**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env with your credentials

   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Frontend Setup**
   ```bash
   cd frontend
   cp .env.example .env.local
   # Edit .env.local with your credentials

   npm install
   ```

4. **Firebase Setup**
   - Create a Firebase project in the Firebase Console
   - Enable **Firestore** (Build → Firestore Database → Create database)
   - Enable **Authentication** (Build → Authentication → Sign-in method)
     - Email/Password (required for email login)
     - Google (optional)
   - Create a **Service Account** key for the backend:
     - Project settings → Service accounts → Generate new private key
     - Save the JSON as `backend/firebase-admin-sdk.json` (this file is gitignored)

### Running the Application

**Development Mode:**

1. Start the backend:
   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```

2. Start the frontend:
   ```bash
   cd frontend
   # If port 3000 is in use, run on 3002:
   npm run dev -- -p 3002
   ```

3. (Optional) Start Celery worker:
   ```bash
   cd backend
   celery -A workers.celery_app worker --loglevel=info
   ```

**Using Docker:**

```bash
cd infra
docker-compose up --build
```

### Environment Variables

#### Backend (.env)
```
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_CREDENTIALS_PATH=./firebase-admin-sdk.json
ALLOWED_ORIGINS=http://localhost:3002
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=sk-ant-...
DEBUG=true
```

#### Frontend (.env.local)
```
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=...
NEXT_PUBLIC_FIREBASE_PROJECT_ID=...
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=...
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=...
NEXT_PUBLIC_FIREBASE_APP_ID=...
NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID=...   # optional
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/auth/verify` | GET | Verify Firebase ID token |
| `/api/auth/me` | GET | Get current user (Firestore) |
| `/api/auth/me` | PUT | Update current user |
| `/api/auth/sync` | POST | Ensure user exists in Firestore |

Note: The remaining feature APIs (profiles/jobs/benchmark/gaps/builder/export/analytics) are being migrated to Firestore and are currently disabled in the backend router.

## Deployment

### Vercel (Frontend)
1. Connect your repository to Vercel
2. Set environment variables
3. Deploy

### Railway (Backend)
1. Create a new project
2. Add Redis (optional)
3. Set environment variables
4. Deploy from Dockerfile

### Firebase (Auth + Firestore)
1. Create a Firebase project
2. Enable Auth providers
3. Enable Firestore
4. Upload the service account JSON as a secret in your backend hosting platform

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 14)                        │
│  /login → /dashboard → /upload → /benchmark → /gaps → /builder     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                            │
│  Auth │ Upload │ Profile │ Benchmark │ Gap │ Consultant │ Export   │
└─────────────────────────────────────────────────────────────────────┘
                    │                           │
          ┌─────────┴─────────┐                 │
          ▼                   ▼                 ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   AI ENGINE      │ │   DATABASE       │ │   WORKERS        │
│   Claude API     │ │   Firestore      │ │   Celery/Redis   │
│   Prompt Chains  │ │   (Firebase)     │ │   Async Tasks    │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

## License

MIT License - see LICENSE file for details
