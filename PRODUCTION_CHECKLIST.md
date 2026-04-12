# HireStack AI - Production Readiness Checklist

> Last updated: April 5, 2025

## ✅ Critical Fixes (COMPLETED)

| Issue | Status | Fix Applied |
|-------|--------|-------------|
| AI Provider misconfigured as "ollama" | ✅ FIXED | Changed to `AI_PROVIDER=gemini` in `backend/.env` |
| Procfile syntax error | ✅ FIXED | Corrected to `cd /app/backend && PYTHONPATH=/app python...` |
| Missing backend deployment in CI/CD | ✅ FIXED | Added `deploy-backend` job to deploy.yml |
| Missing LICENSE file | ✅ FIXED | Added MIT LICENSE file |

---

## 🚀 Deployment Requirements

### Required Secrets (GitHub)

Add these secrets to your GitHub repository (`Settings > Secrets and variables > Actions`):

| Secret Name | Description | Where to Get |
|-------------|-------------|--------------|
| `RAILWAY_TOKEN` | Railway API token | Railway Dashboard → Tokens |
| `NETLIFY_AUTH_TOKEN` | Netlify auth token | Netlify User Settings → Applications |
| `NETLIFY_SITE_ID` | Netlify site ID | Site Settings → General |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | Supabase Project Settings → API |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key | Supabase Project Settings → API |
| `NEXT_PUBLIC_API_URL` | Backend API URL | Railway deployed URL |
| `NEXT_PUBLIC_SENTRY_DSN` | Sentry error tracking (optional) | Sentry Project Settings |

### Required Variables (Railway)

Add these environment variables in Railway dashboard:

```bash
# Application
APP_NAME=HireStack AI
DEBUG=false
ENVIRONMENT=production

# Supabase (production)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# AI Provider (Gemini only)
AI_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-2.5-pro
GEMINI_MAX_TOKENS=8192

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# File Upload
MAX_UPLOAD_SIZE_MB=10
```

---

## 🔄 Pre-Launch Steps

### 1. Rotate API Keys (CRITICAL)

The following keys were potentially exposed and should be regenerated:

- [ ] `GEMINI_API_KEY` - Regenerate at [Google AI Studio](https://aistudio.google.com/app/apikey)
- [ ] `SUPABASE_SERVICE_ROLE_KEY` - Regenerate in Supabase Dashboard → Project Settings → API

### 2. Database Setup

- [ ] Run migrations on production database:
  ```bash
  supabase db push
  # OR manually apply: hirestack_full_migration.sql
  ```
- [ ] Verify RLS policies are enabled
- [ ] Test database connectivity from Railway

### 3. Domain Configuration

- [ ] Configure custom domain for Railway (e.g., `api.hirestack.tech`)
- [ ] Update CORS_ORIGINS in Railway env vars with production domain
- [ ] Configure custom domain for Netlify (e.g., `hirestack.tech`)
- [ ] Update `NEXT_PUBLIC_API_URL` to point to production backend

### 4. Monitoring Setup

- [ ] Create Sentry project and add DSN
- [ ] Set up Railway alerting
- [ ] Configure Supabase logs/monitoring

### 5. Testing

- [ ] Test complete user flow on staging
- [ ] Test AI generation with Gemini

---

## 🐛 Known Issues (Non-Critical)

| Issue | Priority | Impact | Workaround |
|-------|----------|--------|------------|
| Limited test coverage | Medium | Risk of regressions | Manual testing before releases |
| No API versioning | Low | Breaking changes affect all clients | Document API changes carefully |
| Basic rate limiting | Medium | Potential for abuse | Monitor and adjust limits |

---

## 📈 Post-Launch Monitoring

Monitor these metrics after launch:

- AI generation success rate
- API response times
- Error rates (Sentry)
- Database connection pool
- User sign-up conversion

---

## 🆘 Emergency Contacts/Procedures

- **Backend down**: Check Railway status, redeploy from GitHub Actions
- **Database issues**: Check Supabase status, review connection limits
- **AI failures**: Switch AI provider in env vars, restart service
- **Security incident**: Rotate all API keys immediately
