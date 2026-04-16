# HireStack AI — Deployment & Testing Guide

> Last updated: April 2026

## 🚀 Step-by-Step Deployment

Your CI pipeline (`.github/workflows/ci.yml`) passes — the code is ready.  
The Deploy workflow (`.github/workflows/deploy.yml`) **failed** because required
GitHub Secrets are not yet configured.

### Step 1: Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions** in your GitHub repository  
and add **all** of the following:

| Secret Name | Where to Get It | Required By |
|---|---|---|
| `RAILWAY_TOKEN` | [Railway Dashboard → Tokens](https://railway.com/account/tokens) | Backend deploy |
| `NETLIFY_AUTH_TOKEN` | Netlify User Settings → Applications → New access token | Frontend deploy |
| `NETLIFY_SITE_ID` | Netlify Site Settings → General → Site ID | Frontend deploy |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Project Settings → API → Project URL | Both |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase Project Settings → API → `anon` public key | Both |
| `NEXT_PUBLIC_API_URL` | Your Railway backend URL (e.g. `https://hirestack-production.up.railway.app`) | Frontend |
| `NEXT_PUBLIC_SENTRY_DSN` | *(Optional)* Sentry Project Settings → DSN | Frontend (optional) |

### Step 2: Configure Railway Environment Variables

In your Railway dashboard, set these environment variables for the backend service:

```env
APP_NAME=HireStack AI
DEBUG=false
ENVIRONMENT=production

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# AI Provider
AI_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-pro
GEMINI_MAX_TOKENS=8192

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# File Upload
MAX_UPLOAD_SIZE_MB=10
```

### Step 3: Run Database Migrations

```bash
# Option A: Using Supabase CLI
supabase db push

# Option B: Manually in Supabase SQL Editor
# Copy contents of hirestack_full_migration.sql and run
```

### Step 4: Trigger Deployment

The deploy workflow triggers automatically when CI passes on `main`.  
To manually trigger:

1. Push any change to `main` (or merge this PR)
2. CI will run → if green → Deploy triggers automatically
3. Backend deploys to Railway first
4. After backend health check passes, frontend deploys to Netlify

### Step 5: Verify Deployment

After deploy completes:

```bash
# Check backend health
curl https://your-backend-url.railway.app/health

# Check frontend
curl -I https://your-netlify-site.netlify.app
```

---

## 🧪 Testing Guide

### Create Test Users

A seed script creates 5 test personas with different profiles:

```bash
# Set your Supabase credentials
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"

# Create test users
python scripts/seed_test_users.py

# Clean up later
python scripts/seed_test_users.py --cleanup
```

This creates:

| User | Email | Role | Tests |
|---|---|---|---|
| Sarah Chen | sarah.swe@hirestack.test | Senior SWE | Core happy path, generation, workspace |
| Marcus Rivera | marcus.career@hirestack.test | Career Changer | ATS scanner, evidence vault, gaps |
| Priya Patel | priya.newgrad@hirestack.test | New Graduate | Interview prep, learning, salary |
| James O'Brien | james.recruiter@hirestack.test | Recruiter | Candidates, org admin, billing |
| Aisha Okafor | aisha.freelancer@hirestack.test | Freelancer | A/B lab, variants, export |

**All users use password: `TestPass!2026`**

### Manual Testing Checklist

For each test user, verify the following:

#### 🔐 Authentication
- [ ] Login with email/password
- [ ] Login with Google OAuth
- [ ] Register new account
- [ ] Switch between login/register modes
- [ ] Logout and session cleanup
- [ ] Protected routes redirect to login

#### 📊 Dashboard
- [ ] Stats cards load with real data
- [ ] Recent applications are listed
- [ ] "New Application" button works
- [ ] Sidebar navigation works
- [ ] User profile/avatar displayed

#### 🆕 New Application Wizard
- [ ] Step 1: Enter job title and company
- [ ] Step 2: Paste job description
- [ ] Step 3: Upload or paste resume
- [ ] Navigation between steps (next/back)
- [ ] Form validation (empty fields, too-short text)
- [ ] AI generation triggers and shows progress
- [ ] SSE progress events display correctly

#### 📄 Application Workspace
- [ ] Scoreboard header shows match score + ATS readiness
- [ ] Module cards display (Benchmark, Gap Analysis, CV, Cover Letter, etc.)
- [ ] Module cards show content snippets
- [ ] TipTap editor opens for document editing
- [ ] Evidence picker inserts evidence into document
- [ ] Version history is accessible

#### 📥 Export
- [ ] Download CV as HTML
- [ ] Download CV as PDF
- [ ] Download Cover Letter
- [ ] Bulk export (ZIP)

#### 🔍 ATS Scanner
- [ ] Scan a resume against a JD
- [ ] View keyword matches
- [ ] View improvement suggestions

#### 💼 Job Board
- [ ] Job listings load
- [ ] Can create job alerts
- [ ] Job matching scores display

#### 🎤 Interview Prep
- [ ] Create interview session
- [ ] View practice questions
- [ ] Record/submit answers

#### 📚 Learning
- [ ] Daily challenge loads
- [ ] Can submit solutions
- [ ] Learning progress tracked

#### 💰 Salary Coach
- [ ] Salary analysis loads
- [ ] Market data comparison
- [ ] Negotiation suggestions

#### 📈 Career Analytics
- [ ] Portfolio view loads
- [ ] Career snapshot works
- [ ] Skills chart displays

#### 🗃️ Evidence Vault
- [ ] Evidence items display
- [ ] Can add new evidence
- [ ] Filter by type works

#### 👥 Candidates (Recruiter)
- [ ] Candidate list loads
- [ ] Can add candidates
- [ ] Pipeline stats display

#### ⚙️ Settings
- [ ] Profile settings editable
- [ ] Organization settings (admin)
- [ ] Billing status visible
- [ ] API key management

#### 📱 Responsive Design
- [ ] Mobile (375px): All pages usable
- [ ] Tablet (768px): Layout adapts
- [ ] Desktop (1920px): Full layout
- [ ] Sidebar collapses on mobile

#### ♿ Accessibility
- [ ] Keyboard navigation works
- [ ] Form inputs have labels
- [ ] Buttons have accessible names
- [ ] Color contrast is sufficient

### Automated Tests

```bash
# Backend unit tests (844 tests)
cd backend
pip install -r requirements.txt
SUPABASE_URL=https://placeholder.supabase.co \
SUPABASE_ANON_KEY=placeholder \
SUPABASE_SERVICE_ROLE_KEY=placeholder \
SUPABASE_JWT_SECRET=placeholder_jwt_secret \
GEMINI_API_KEY=placeholder \
python -m pytest tests/ -v --ignore=tests/e2e

# Frontend unit tests (184 tests)
cd frontend
npm ci
npm test

# Frontend E2E tests (public pages — no auth needed)
npx playwright install chromium
npx playwright test e2e/comprehensive-features.spec.ts --project=chromium

# Frontend E2E tests (with auth — needs test users)
E2E_TEST_EMAIL=sarah.swe@hirestack.test \
E2E_TEST_PASSWORD=TestPass!2026 \
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key \
npx playwright test e2e/ --project=chromium
```

---

## 🔍 Troubleshooting

### Deploy workflow fails with "RAILWAY_TOKEN secret is not set"
→ Add `RAILWAY_TOKEN` in GitHub Settings → Secrets → Actions

### Backend health check fails after deploy
→ Check Railway logs: `railway logs --service=backend`  
→ Verify all env vars are set in Railway dashboard

### Frontend build fails
→ Verify `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_API_URL` are set

### AI generation returns empty results
→ Verify `GEMINI_API_KEY` is valid and not rate-limited  
→ Check `AI_PROVIDER=gemini` is set in Railway env vars

### Login fails with "Invalid login credentials"
→ Run `python scripts/seed_test_users.py` to create test accounts  
→ Verify `SUPABASE_URL` and `SUPABASE_ANON_KEY` match your project
