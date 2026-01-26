# HireStack AI - Project Development Journal

## Project Overview

**HireStack AI** is an AI-powered career intelligence platform that helps job seekers optimize their applications by:
1. Generating benchmark "ideal candidate" profiles for target roles
2. Analyzing user profiles against benchmarks
3. Identifying skill gaps and creating personalized improvement roadmaps
4. Building tailored application documents (CV, cover letters, portfolios)
5. Providing AI-powered career consulting

---

## Technology Stack

### Frontend
- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: Custom components with Lucide icons
- **State Management**: React Query (@tanstack/react-query)
- **Authentication**: Firebase Auth (client-side)

### Backend
- **Framework**: FastAPI (Python)
- **Language**: Python 3.9+
- **Database**: Firebase Firestore (NoSQL)
- **Authentication**: Firebase Admin SDK (token verification)
- **AI**: Anthropic Claude API

### Infrastructure
- **Auth & Database**: Firebase (Authentication + Firestore)
- **File Storage**: Firebase Storage
- **Hosting**:
  - Frontend: Firebase Hosting / Vercel
  - Backend: Railway / Google Cloud Run

---

## Development Timeline

### Session 1: Initial Project Setup

**Date**: January 2025

#### What Was Built
1. **Project Scaffold**
   - Created monorepo structure with `frontend/` and `backend/` directories
   - Set up Next.js 14 with TypeScript and Tailwind CSS
   - Set up FastAPI with Python

2. **Backend Architecture** (Initially with Supabase/PostgreSQL)
   - SQLAlchemy models for all entities
   - FastAPI routes for auth, profile, jobs, benchmark, gaps, consultant, builder, export
   - AI Engine with Claude prompt chains

3. **Frontend Pages**
   - Login/Register page
   - Dashboard
   - Upload (resume)
   - Benchmark view
   - Gap analysis
   - Consultant (roadmap)
   - Document builder
   - Export center

4. **AI Engine**
   - Claude API client
   - Prompt chains for:
     - Role profiling
     - Benchmark building
     - Gap analysis
     - Career consulting
     - Document generation

#### Issues Encountered & Fixed
1. **httpx version conflict**: supabase required httpx<0.26
   - Fix: Changed to `httpx>=0.24,<0.26`

2. **Python 3.9 union type syntax**: `Client | None` not supported
   - Fix: Changed to `Optional[Client]` with proper imports

3. **SQLAlchemy reserved attribute**: `metadata` is reserved in DeclarativeBase
   - Fix: Renamed to `doc_metadata`

4. **Missing ai_engine module**: Backend couldn't import ai_engine
   - Fix: Added parent directory to sys.path in main.py

5. **Missing imports**: Various missing imports (List, markdown module)
   - Fix: Added missing imports and installed packages

6. **Tailwind prose class error**: Typography plugin not installed
   - Fix: `npm install @tailwindcss/typography`

---

### Session 2: Firebase Migration

**Date**: January 2025

#### Decision: Switch from Supabase to Firebase

**Reason**: User preference for Firebase ecosystem

#### Migration Steps Completed

1. **Frontend Firebase Setup**
   - Created `/frontend/src/lib/firebase.ts` - Firebase client configuration
   - Updated `/frontend/.env.local` with Firebase web config:
     ```
     NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSyDGLHyDQIgqqWDKo8_QX7nhX1sRloCXo2o
     NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=hirestack-ai.firebaseapp.com
     NEXT_PUBLIC_FIREBASE_PROJECT_ID=hirestack-ai
     NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=hirestack-ai.firebasestorage.app
     NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=653123981374
     NEXT_PUBLIC_FIREBASE_APP_ID=1:653123981374:web:538baa677644100f88816f
     NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID=G-2NEF23KLB7
     ```
   - Updated `/frontend/src/components/providers.tsx` - Firebase Auth context
   - Updated `/frontend/src/hooks/use-auth.ts` - Firebase auth methods
   - Updated `/frontend/src/app/login/page.tsx` - Firebase login UI

2. **Backend Firebase Setup**
   - Saved Firebase Admin SDK credentials to `/backend/firebase-admin-sdk.json`
   - Updated `/backend/.env`:
     ```
     FIREBASE_PROJECT_ID=hirestack-ai
     FIREBASE_CREDENTIALS_PATH=./firebase-admin-sdk.json
     ```
   - Updated `/backend/requirements.txt`:
     - Removed: sqlalchemy, asyncpg, alembic, pgvector, supabase, gotrue
     - Added: firebase-admin, google-cloud-firestore

3. **Database Migration (PostgreSQL → Firestore)**
   - Rewrote `/backend/app/core/database.py` for Firestore
   - Created `FirestoreDB` class with CRUD operations
   - Defined Firestore collections:
     ```python
     COLLECTIONS = {
         'users': 'users',
         'profiles': 'profiles',
         'jobs': 'job_descriptions',
         'benchmarks': 'benchmarks',
         'gap_reports': 'gap_reports',
         'roadmaps': 'roadmaps',
         'projects': 'projects',
         'documents': 'documents',
         'exports': 'exports',
         'analytics': 'analytics',
     }
     ```

4. **Authentication Flow Update**
   - Updated `/backend/app/api/deps.py` - Firebase token verification
   - Updated `/backend/app/api/routes/auth.py` - Simplified for Firebase
   - Updated `/backend/app/services/auth.py` - Firestore user management
   - Updated `/backend/app/core/config.py` - Removed PostgreSQL config

5. **Security Setup**
   - Created `/.gitignore` to exclude:
     - Firebase credentials files
     - Environment files
     - Node modules
     - Python cache

---

## Current Project Structure

```
HireStack AI/
├── frontend/                    # Next.js 14 application
│   ├── src/
│   │   ├── app/                 # App router pages
│   │   │   ├── login/           # Login page
│   │   │   ├── dashboard/       # Main dashboard
│   │   │   ├── upload/          # Resume upload
│   │   │   ├── benchmark/       # Benchmark view
│   │   │   ├── gaps/            # Gap analysis
│   │   │   ├── consultant/      # Career roadmap
│   │   │   ├── builder/         # Document builder
│   │   │   └── export/          # Export center
│   │   ├── components/          # React components
│   │   │   └── providers.tsx    # Auth & Query providers
│   │   ├── lib/                 # Utilities
│   │   │   ├── firebase.ts      # Firebase client
│   │   │   └── api.ts           # API client
│   │   └── hooks/               # Custom hooks
│   │       └── use-auth.ts      # Auth hook
│   ├── .env.local               # Firebase config
│   ├── package.json
│   └── tailwind.config.ts
│
├── backend/                     # FastAPI application
│   ├── app/
│   │   ├── api/                 # API routes
│   │   │   ├── routes/
│   │   │   │   ├── auth.py
│   │   │   │   ├── profile.py
│   │   │   │   ├── jobs.py
│   │   │   │   ├── benchmark.py
│   │   │   │   ├── gaps.py
│   │   │   │   ├── consultant.py
│   │   │   │   ├── builder.py
│   │   │   │   └── export.py
│   │   │   └── deps.py          # Dependencies
│   │   ├── core/
│   │   │   ├── config.py        # Settings
│   │   │   └── database.py      # Firestore client
│   │   ├── services/            # Business logic
│   │   └── schemas/             # Pydantic schemas
│   ├── firebase-admin-sdk.json  # Firebase credentials
│   ├── .env                     # Environment variables
│   ├── main.py                  # Entry point
│   └── requirements.txt
│
├── ai_engine/                   # AI prompt chains
│   ├── chains/
│   │   ├── role_profiler.py
│   │   ├── benchmark_builder.py
│   │   ├── gap_analyzer.py
│   │   ├── career_consultant.py
│   │   ├── document_generator.py
│   │   └── validator.py
│   ├── prompts/
│   └── client.py                # Claude API client
│
├── docs/
│   └── PROJECT_JOURNAL.md       # This file
│
└── .gitignore
```

---

## Firebase Configuration

### Firestore Collections Schema

```
users/
├── {userId}
│   ├── firebase_uid: string
│   ├── email: string
│   ├── full_name: string
│   ├── avatar_url: string
│   ├── is_active: boolean
│   ├── is_premium: boolean
│   ├── created_at: timestamp
│   └── updated_at: timestamp

profiles/
├── {profileId}
│   ├── user_id: string
│   ├── raw_resume_text: string
│   ├── parsed_data: map
│   ├── skills: array
│   ├── experience: array
│   ├── education: array
│   └── ...

job_descriptions/
├── {jobId}
│   ├── user_id: string
│   ├── title: string
│   ├── company: string
│   ├── description: string
│   ├── requirements: map
│   └── ...

benchmarks/
├── {benchmarkId}
│   ├── job_description_id: string
│   ├── ideal_profile: map
│   ├── ideal_cv: string
│   ├── ideal_cover_letter: string
│   └── ...

gap_reports/
├── {reportId}
│   ├── user_id: string
│   ├── profile_id: string
│   ├── benchmark_id: string
│   ├── compatibility_score: number
│   ├── skill_gaps: array
│   └── ...

roadmaps/
├── {roadmapId}
│   ├── user_id: string
│   ├── gap_report_id: string
│   ├── learning_path: array
│   ├── milestones: array
│   └── ...

documents/
├── {documentId}
│   ├── user_id: string
│   ├── document_type: string
│   ├── content: string
│   ├── version: number
│   └── ...
```

### Firebase Security Rules (Recommended)

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Users can only access their own data
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == resource.data.firebase_uid;
    }

    match /profiles/{profileId} {
      allow read, write: if request.auth != null && request.auth.uid == resource.data.user_id;
    }

    // Similar rules for other collections...
  }
}
```

---

## Environment Variables Reference

### Frontend (.env.local)
```env
NEXT_PUBLIC_FIREBASE_API_KEY=your-api-key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your-sender-id
NEXT_PUBLIC_FIREBASE_APP_ID=your-app-id
NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID=G-XXXXXXX
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Backend (.env)
```env
# Firebase
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CREDENTIALS_PATH=./firebase-admin-sdk.json

# AI
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
ANTHROPIC_MAX_TOKENS=4096

# App
DEBUG=true
ALLOWED_ORIGINS=http://localhost:3000
```

---

## Running the Application

### Prerequisites
- Node.js 18+
- Python 3.9+
- Firebase project with Authentication and Firestore enabled

### Frontend
```bash
cd frontend
npm install
# Default is port 3000. If 3000 is in use, pick another port (example: 3002).
npm run dev -- -p 3002
# Runs on http://localhost:3002
```

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
# Runs on http://localhost:8000
```

---

## API Endpoints

Note: As of **January 25, 2026**, only the **Authentication** routes are enabled in the backend router. The remaining feature routes are being migrated to Firestore and are temporarily disabled in `backend/app/api/routes/__init__.py`.

### Authentication
- `GET /api/auth/verify` - Verify Firebase token
- `GET /api/auth/me` - Get current user
- `PUT /api/auth/me` - Update user profile
- `POST /api/auth/sync` - Sync Firebase user to Firestore

### Profile (planned / currently disabled)
- `POST /api/profile/upload` - Upload resume
- `GET /api/profile` - List profiles
- `GET /api/profile/primary` - Get primary profile

### Jobs (planned / currently disabled)
- `POST /api/jobs` - Create job description
- `GET /api/jobs` - List jobs
- `GET /api/jobs/{id}` - Get job details

### Benchmark (planned / currently disabled)
- `POST /api/benchmark/generate` - Generate benchmark
- `GET /api/benchmark/{id}` - Get benchmark

### Gap Analysis (planned / currently disabled)
- `POST /api/gaps/analyze` - Analyze gaps
- `GET /api/gaps` - List gap reports
- `GET /api/gaps/{id}` - Get gap report

### Consultant (planned / currently disabled)
- `POST /api/consultant/roadmap` - Generate roadmap
- `GET /api/consultant/roadmaps` - List roadmaps

### Document Builder (planned / currently disabled)
- `POST /api/builder/generate` - Generate document
- `GET /api/builder/documents` - List documents
- `PUT /api/builder/documents/{id}` - Update document

### Export (planned / currently disabled)
- `POST /api/export` - Create export
- `GET /api/export/{id}/download` - Download export

---

## Next Steps

1. **Enable Firestore in Firebase Console**
   - Go to Firebase Console → Firestore Database → Create Database
   - Start in test mode for development

2. **Enable Authentication Methods**
   - Firebase Console → Authentication → Sign-in method
   - Enable Email/Password
   - Enable Google (optional)

3. **Test Authentication Flow**
   - Register a new user on frontend
   - Verify token verification on backend

4. **Update Remaining Routes for Firestore**
   - Profile routes
   - Jobs routes
   - Benchmark routes
   - etc.

5. **Deploy**
   - Frontend to Firebase Hosting or Vercel
   - Backend to Railway or Google Cloud Run

---

## Troubleshooting

### Common Issues

1. **Firebase Admin SDK initialization fails**
   - Ensure `firebase-admin-sdk.json` exists and path is correct in `.env`
   - Check file permissions

2. **CORS errors**
   - Ensure `ALLOWED_ORIGINS` in backend `.env` matches frontend URL
   - Check `cors_origins` in `config.py`

3. **Token verification fails**
   - Ensure Firebase project ID matches between frontend and backend
   - Check that the Firebase Admin SDK credentials are for the same project

4. **Firestore permission denied**
   - Check Firestore security rules
   - For development, use test mode rules

5. **Firestore “database (default) does not exist”**
   - Some newer Firebase projects are created with Firestore multi-database ID `default` (no parentheses).
   - Older SDK defaults may still try to connect to `(default)` and you’ll see 404 errors.
   - Fix:
     - Backend: set `FIREBASE_DATABASE_ID=default` (or `(default)` for older projects).
     - Frontend: set `NEXT_PUBLIC_FIREBASE_DATABASE_ID=default` (or `(default)`).
   - Health check: `curl -s http://localhost:8000/health | python3 -m json.tool`

6. **Resume upload “stuck” / never finishes**
   - Symptom: the `/new` wizard shows upload progress that doesn’t complete (often around early percentages).
   - Most common causes:
     - **Firebase Storage not enabled** yet (no default bucket created).
     - **Storage Rules** blocking the upload for authenticated users.
     - Local network / VPN interfering with uploads.
   - Fix:
     - Firebase Console → **Build → Storage → Get started** → create the default bucket.
     - Note: some projects require attaching a **billing account** to create the Cloud Storage bucket (you can still stay within free quotas, but billing must be enabled to provision the bucket).
     - For development, set Storage Rules to allow authenticated users to write to their own paths.
     - Verify `frontend/.env.local` has `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` matching the Firebase web config (`storageBucket`).
     - Quick check: `curl -s http://localhost:8000/health | python3 -m json.tool` and look for `firebase.storage.ok`.
     - Local dev alternative (no billing): run the Storage emulator and point the frontend to it:
       - Start: `firebase emulators:start --only storage`
       - Set in `frontend/.env.local`:
         - `NEXT_PUBLIC_FIREBASE_STORAGE_EMULATOR_HOST=localhost`
         - `NEXT_PUBLIC_FIREBASE_STORAGE_EMULATOR_PORT=9199`
   - App behavior (current): parsed resume text is saved to Firestore first, and the file upload runs in the background with stall detection + cancel.
   - If Storage is not enabled, the wizard stores **small resume files** in Firestore (`resume.inlineBytes`) as a fallback, so you can keep moving.
   - PDF parsing note: PDF.js needs a worker file. The repo auto-copies it on install via `frontend/scripts/copy-pdf-worker.mjs` and serves it as `/pdf.worker.mjs`.

---

7. **Sign-in completes but you get bounced back to `/login`**
   - Symptom: clicking **Sign in** looks like it “does nothing”, or you briefly hit `/dashboard` and get redirected back.
   - Cause: a short client-side timing window where Firebase has a user, but the React auth context hasn’t re-rendered yet.
   - Fix: the dashboard auth gate now listens to `onIdTokenChanged` to avoid redirect races (`frontend/src/app/(dashboard)/layout.tsx`).

---

*Last Updated: January 26, 2026*

---

## UI/UX Redesign Addendum (Application Intelligence Workspace)

On January 25, 2026, the frontend was redesigned from a generic dashboard into a premium, coach-driven “application intelligence workspace” built directly on Firebase (Auth + Firestore + Storage).

- UX/IA spec: `docs/WORKSPACE_UX_SPEC.md`
- New core routes: `/dashboard`, `/new`, `/applications/[id]`, `/evidence`, `/career`
- Key UX objects: AppShell, ScoreboardHeader, CoachPanel, Action Queue, Evidence Vault, Diff + Versioning, per-module regeneration

### Dev server stability (Next.js)

To avoid `.next` corruption (e.g., runtime errors after running multiple dev servers or running `next build` while dev is running), the frontend now supports **separate dev output folders** via `NEXT_DIST_DIR`.

- Default dev: `cd frontend && npm run dev` (runs on `3002` with `NEXT_DIST_DIR=.next-dev-3002`)
- Optional: `cd frontend && npm run dev:3000` (runs on `3000` with `NEXT_DIST_DIR=.next-dev-3000`)
- Production build remains `cd frontend && npm run build` (uses `.next`)

### Wizard resume upload resilience

The New Application Wizard is designed to be unblockable:
- Parsed resume text + initial facts are saved to Firestore immediately.
- Firebase Storage upload is **optional** and runs in the background (progress + stall detection + cancel).
- If Storage is disabled or misconfigured, the user can still continue the workflow using the parsed/pasted resume text.
- If the Cloud Storage bucket is not provisioned, small resume files are stored in Firestore as a fallback (`resume.inlineBytes`) to keep the workflow moving.
