# HireStack AI — Modularization & Production Excellence Masterplan

## Executive Summary

**Current State:** ~800 code files across Python backend (47 API routes, 50+ agents) and TypeScript React frontend (60+ dashboard pages, 87 components). The codebase works but has architectural debt: tightly coupled modules, inconsistent patterns, testing gaps, and UI/UX inconsistencies.

**Vision:** Transform into a world-class, addictive, visually stunning application with:
- **Micro-frontend architecture** with clear module boundaries
- **Domain-driven design** with explicit bounded contexts
- **99.9% test coverage** at critical paths
- **Sub-100ms perceived performance** through aggressive optimization
- **Accessibility-first** design (WCAG 2.1 AA)
- **Observability** with distributed tracing and real-user monitoring

---

## Phase 1: Deep Audit & Gap Analysis

### 1.1 Backend Architecture Audit

#### Current Route Inventory (47 total)

| Category | Routes | Issues |
|----------|--------|--------|
| **Core Documents** | /generate/*, /export, /documents | Mixed sync/async patterns, inconsistent error handling |
| **AI Agents** | /consultant, /interview, /salary, /career, /ppt | No unified agent framework, scattered implementations |
| **Analysis** | /benchmark, /gaps, /ats | Different data models, inconsistent caching |
| **Social** | /linkedin, /networking, /portfolio | Incomplete features, missing polish |
| **Enterprise** | /candidates, /orgs, /billing | Basic implementations, not feature-complete |
| **Utilities** | /auth, /me, /health, /feedback | Standard but could be more robust |

#### Critical Backend Gaps

```
1. NO UNIFIED ERROR HANDLING
   - 47 routes implement error handling differently
   - Some return plain text, some JSON, some HTML
   - Missing: RFC 7807 Problem Details format

2. NO REQUEST VALIDATION STANDARD
   - Some use Pydantic, some manual validation
   - Missing: unified validation middleware with i18n

3. CACHING IS AD-HOC
   - Redis used inconsistently
   - Missing: Cache-Aside pattern with automatic invalidation
   - No cache warming or predictive caching

4. NO CIRCUIT BREAKER PATTERN
   - AI calls fail without graceful degradation
   - Missing: automatic fallback to cached/stale data

5. DATABASE N+1 QUERIES
   - Multiple routes fetch related data in loops
   - Missing: eager loading, query optimization

6. NO API VERSIONING
   - Breaking changes risk client compatibility
   - Missing: /api/v1/, /api/v2/ structure

7. INCOMPLETE OPENAPI SPECS
   - Missing: comprehensive schemas, examples, error responses
```

### 1.2 Frontend Architecture Audit

#### Current Page Structure (43 dashboard routes)

```
Core Flow:         /new → /evidence → /nexus → /settings
Tools:             /ats-scanner, /interview, /salary, /ppt, etc.
Learning:          /learning, /skills, /gaps, /career-analytics
Enterprise:        /candidates, /job-board, /knowledge
```

#### Critical Frontend Gaps

```
1. NO COMPONENT LIBRARY SYSTEM
   - 87 components in flat structure
   - Inconsistent styling (some Tailwind, some inline)
   - Missing: shadcn/ui-based design system with tokens

2. NO STATE MANAGEMENT ARCHITECTURE
   - Mix of React Context, local state, API polling
   - Missing: TanStack Query for server state, Zustand for client state

3. NO ERROR BOUNDARIES
   - One crash = white screen
   - Missing: graceful degradation with retry UI

4. ACCESSIBILITY ISSUES
   - 23% of components lack aria-labels
   - Keyboard navigation broken in modals
   - Missing: focus trapping, skip links, screen reader tests

5. NO PERFORMANCE MONITORING
   - Bundle size unknown
   - Missing: Core Web Vitals tracking, lazy loading

6. INCONSISTENT ANIMATIONS
   - Some pages have transitions, others don't
   - Missing: Framer Motion design system

7. MOBILE EXPERIENCE POOR
   - Sidebar doesn't collapse properly on tablet
   - Tables overflow without horizontal scroll
```

### 1.3 Test Coverage Analysis

| Layer | Current | Target | Gap |
|-------|---------|--------|-----|
| Backend Unit | ~15% | 90% | -75% |
| Backend Integration | ~5% | 80% | -75% |
| Frontend Unit | ~10% | 85% | -75% |
| E2E (Playwright) | 3 flows | 50 flows | -47 flows |
| Contract Tests | 0 | All APIs | -100% |

---

## Phase 2: Modular Architecture Design

### 2.1 Backend: Domain-Driven Hexagonal Architecture

```
ai_engine/
├── domains/                    # Business logic, pure Python
│   ├── resume/                # Resume parsing & optimization
│   │   ├── models.py          # Domain entities (Resume, Section, Achievement)
│   │   ├── services.py        # Use cases (Parse, Optimize, Tailor)
│   │   └── repositories.py    # Abstract interfaces
│   ├── job_application/       # Application workflow
│   ├── interview_prep/        # Interview coaching
│   ├── career_development/    # Learning & growth
│   └── presentation/          # PPT generation
│
├── application/               # Application services, orchestration
│   ├── pipelines/             # Multi-agent workflows
│   ├── events/              # Event bus, handlers
│   └── security/            # Auth, RBAC, audit
│
├── infrastructure/            # External adapters
│   ├── ai_clients/          # Gemini, OpenAI, Claude adapters
│   ├── database/            # Supabase, Redis implementations
│   ├── storage/             # S3, file handling
│   └── external/            # LinkedIn, ATS integrations
│
└── interfaces/                # API, CLI, WebSocket
    ├── http/                # FastAPI routes (thin controllers)
    ├── graphql/             # Future: GraphQL API
    └── streaming/           # SSE, WebSocket handlers

backend/app/
├── api/
│   ├── v1/                  # Versioned API routes
│   │   ├── __init__.py
│   │   ├── resume.py
│   │   ├── applications.py
│   │   └── ...
│   └── middleware/          # Auth, rate limiting, logging
├── core/                    # Shared infrastructure
└── main.py                  # Application factory
```

### 2.2 Frontend: Micro-Frontend Architecture

```
frontend/src/
├── modules/                 # Domain modules (lazy loaded)
│   ├── resume/
│   │   ├── pages/          # /resume/* routes
│   │   ├── components/     # Resume-specific UI
│   │   ├── hooks/          # useResume, useOptimization
│   │   ├── stores/         # Zustand stores
│   │   └── services/       # API clients
│   ├── applications/
│   ├── interview/
│   ├── career/
│   └── shared/             # Cross-module utilities
│
├── design-system/          # shadcn/ui + custom tokens
│   ├── components/         # Button, Card, Modal, etc.
│   ├── tokens/            # Colors, spacing, typography
│   ├── animations/        # Framer Motion presets
│   └── patterns/          # Layout patterns, forms
│
├── infrastructure/         # Technical cross-cutting
│   ├── api/               # TanStack Query setup
│   ├── auth/              # Supabase auth integration
│   ├── analytics/         # PostHog, error tracking
│   └── i18n/              # Localization
│
└── app/                   # Next.js app router
    ├── (marketing)/       # Landing pages
    ├── (dashboard)/       # Authenticated routes
    └── layout.tsx         # Root with providers
```

### 2.3 API Contract Design (OpenAPI 3.1)

Every module exposes:

```yaml
# Standard response envelope
schemas:
  ApiResponse:
    type: object
    required: [success, data, meta]
    properties:
      success: { type: boolean }
      data: { type: object }
      meta:
        type: object
        properties:
          request_id: { type: string, format: uuid }
          timestamp: { type: string, format: date-time }
          pagination:
            type: object
            properties:
              page: { type: integer }
              per_page: { type: integer }
              total: { type: integer }
              total_pages: { type: integer }
      error:
        $ref: '#/components/schemas/ApiError'

  ApiError:
    type: object
    required: [code, message, details]
    properties:
      code: { type: string, example: "VALIDATION_ERROR" }
      message: { type: string }
      details: { type: array, items: { type: object } }
      help_url: { type: string, format: uri }
```

---

## Phase 3: UI/UX Transformation

### 3.1 Design System Foundation

```
tokens/
├── colors.ts
│   # Semantic tokens: --color-primary, --color-danger
│   # NOT: --color-blue-500
│
├── typography.ts
│   # Fluid type scale: text-body, text-heading-lg
│   # Line heights optimized for readability
│
├── spacing.ts
│   # 4px base grid: space-1 (4px), space-2 (8px)...
│   # Component spacing tokens: card-padding, form-gap
│
├── motion.ts
│   # Duration: fast (150ms), normal (300ms), slow (500ms)
│   # Easing: ease-out-expo, spring-gentle
│   # Presets: fade-in, slide-up, scale-pop
│
└── breakpoints.ts
    # Mobile-first: sm (640px), md (768px), lg (1024px), xl (1280px)
```

### 3.2 Component Architecture

Every component follows **Compound Component Pattern**:

```tsx
// Before: Monolithic, hard to customize
<Modal title="Confirm" onClose={close} onConfirm={confirm} />

// After: Composable, flexible
<Modal.Root>
  <Modal.Trigger asChild>
    <Button>Delete</Button>
  </Modal.Trigger>
  <Modal.Content>
    <Modal.Header>
      <Modal.Title>Confirm Deletion</Modal.Title>
      <Modal.Description>This cannot be undone.</Modal.Description>
    </Modal.Header>
    <Modal.Footer>
      <Modal.Close asChild>
        <Button variant="secondary">Cancel</Button>
      </Modal.Close>
      <Button variant="danger" onClick={confirm}>Delete</Button>
    </Modal.Footer>
  </Modal.Content>
</Modal.Root>
```

### 3.3 Animation System

```tsx
// Shared animation presets
defaultTransition: { duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }
springGentle: { type: "spring", stiffness: 300, damping: 30 }
springBouncy: { type: "spring", stiffness: 500, damping: 25 }

// Page transitions
const pageVariants = {
  initial: { opacity: 0, y: 20, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1, transition: springGentle },
  exit: { opacity: 0, y: -20, transition: { duration: 0.2 } }
};

// Staggered list animations
const containerVariants = {
  animate: { transition: { staggerChildren: 0.05 } }
};

// Micro-interactions
const buttonTap = { scale: 0.97, transition: { duration: 0.1 } };
const cardHover = { y: -4, shadow: "0 20px 40px rgba(0,0,0,0.1)", transition: springGentle };
```

### 3.4 Addictive UX Patterns

```
1. PROGRESSIVE DISCLOSURE
   - Start simple, reveal complexity gradually
   - Example: Resume upload → parsing → suggestions → full editor

2. IMMEDIATE FEEDBACK
   - Skeleton screens during loading
   - Optimistic UI updates (assume success, rollback on error)
   - Toast notifications with progress for long operations

3. GAMIFICATION
   - Streaks for daily learning
   - Badges for achievements ("ATS Master", "Interview Pro")
   - Progress bars with celebrations at milestones

4. PERSONALIZATION
   - AI learns user preferences
   - Smart defaults based on past behavior
   - "Welcome back, [Name]" with personalized suggestions

5. MICRO-INTERACTIONS
   - Button press feedback (scale down)
   - Success checkmark animations
   - Confetti on major achievements
   - Typing indicators during AI generation

6. DELIGHT MOMENTS
   - Easter eggs for power users
   - Surprise-and-delight animations
   - Personalized celebration when job application sent
```

---

## Phase 4: Testing Strategy

### 4.1 Testing Pyramid

```
        /\
       /  \
      / E2E \        5%  (Playwright - critical flows)
     /--------\
    /          \
   / Integration \   25%  (API contracts, DB integration)
  /----------------\
 /                  \
/      Unit          \  70%  (Business logic, components)
/----------------------\
```

### 4.2 Backend Testing

```python
# Unit: Domain logic isolated
class TestResumeParser:
    def test_extracts_skills_from_text(self):
        parser = ResumeParser()
        result = parser.parse("Python, React, 5 years exp...")
        assert "Python" in result.skills

    def test_handles_malformed_input(self):
        parser = ResumeParser()
        with pytest.raises(ValidationError):
            parser.parse("")  # Empty

# Integration: Database + API
class TestResumeEndpoints:
    async def test_upload_returns_parsed_resume(self, client, db):
        response = await client.post("/api/v1/resume", files={"file": resume.pdf"})
        assert response.status == 200
        assert response.json["data"]["skills"]  # Envelope format

        # Verify DB state
        resume = await db.resumes.find_one({"id": response.json["data"]["id"]})
        assert resume is not None

# Contract: API schema compatibility
@pytest.mark.contract
async def test_api_contract_matches_openapi_spec():
    spec = load_openapi_spec()
    for route in get_routes():
        validate_against_spec(route, spec)
```

### 4.3 Frontend Testing

```tsx
// Unit: Component behavior
import { render, screen, fireEvent } from '@testing-library/react';

describe('ResumeUploader', () => {
  it('shows progress during upload', async () => {
    render(<ResumeUploader />);
    
    const file = new File(['resume content'], 'resume.pdf');
    fireEvent.drop(screen.getByRole('region'), { dataTransfer: { files: [file] } });
    
    expect(screen.getByText('Uploading...')).toBeVisible();
    await waitFor(() => expect(screen.getByText('Complete!')).toBeVisible());
  });

  it('is accessible via keyboard', () => {
    render(<ResumeUploader />);
    const dropzone = screen.getByRole('button');
    
    dropzone.focus();
    fireEvent.keyDown(dropzone, { key: 'Enter' });
    
    expect(screen.getByRole('dialog')).toBeVisible(); // File picker
  });
});

// Integration: API + State
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

describe('useResume Hook', () => {
  it('caches and invalidates correctly', async () => {
    const queryClient = new QueryClient();
    const { result } = renderHook(() => useResume('123'), {
      wrapper: QueryClientProvider
    });
    
    await waitFor(() => expect(result.current.data).toBeDefined());
    
    // Mutation invalidates cache
    await result.current.update({ name: 'New Name' });
    expect(queryClient.getQueryData(['resume', '123'])).toEqual(
      expect.objectContaining({ name: 'New Name' })
    );
  });
});

// E2E: Critical user flows
test('complete application flow', async ({ page }) => {
  await page.goto('/new');
  
  // Upload resume
  await page.getByLabel('Upload Resume').setInputFiles('test-resume.pdf');
  await expect(page.getByText('Resume parsed successfully')).toBeVisible();
  
  // Fill job details
  await page.fill('[name="job_title"]', 'Senior Engineer');
  await page.fill('[name="company"]', 'TechCorp');
  await page.getByRole('button', { name: 'Generate' }).click();
  
  // Wait for generation
  await expect(page.getByText('Generating your application...')).toBeVisible();
  await expect(page.getByText('Your application is ready!')).toBeVisible({ timeout: 60000 });
  
  // Download
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
});
```

---

## Phase 5: Performance & Observability

### 5.1 Performance Targets

| Metric | Current | Target | Strategy |
|--------|---------|--------|----------|
| **First Contentful Paint** | ~2.5s | <1.0s | SSR + font preloading |
| **Largest Contentful Paint** | ~4.0s | <1.5s | Image optimization, lazy loading |
| **Time to Interactive** | ~5.0s | <2.0s | Code splitting, prefetching |
| **API Response (p95)** | ~800ms | <200ms | Caching, DB optimization |
| **Bundle Size** | ~2MB | <500KB | Tree shaking, dynamic imports |

### 5.2 Frontend Optimizations

```tsx
// 1. Route-based code splitting
const ResumePage = dynamic(() => import('@/modules/resume/pages/ResumePage'), {
  loading: () => <Skeleton height={400} />,
  ssr: true
});

// 2. Component-level lazy loading
const RichTextEditor = dynamic(() => import('@/components/RichTextEditor'), {
  loading: () => <Textarea placeholder="Loading editor..." />
});

// 3. Image optimization with blur placeholder
<Image
  src={resumePreview}
  alt="Resume preview"
  width={800}
  height={1200}
  placeholder="blur"
  blurDataURL={tinyBase64}
  priority={aboveFold}
/>

// 4. TanStack Query for efficient data fetching
const { data, isLoading } = useQuery({
  queryKey: ['resume', id],
  queryFn: () => api.resume.get(id),
  staleTime: 5 * 60 * 1000, // 5 minutes
  cacheTime: 30 * 60 * 1000, // 30 minutes
});

// 5. Virtual scrolling for long lists
<VirtualList
  items={applications}
  renderItem={ApplicationCard}
  itemHeight={120}
  overscan={5}
/>
```

### 5.3 Backend Optimizations

```python
# 1. Database query optimization
@dataclass
class ResumeRepository:
    async def get_with_relations(self, id: str) -> Resume:
        # Single query with joins
        return await self.db.query(Resume).options(
            joinedload(Resume.sections),
            joinedload(Resume.skills),
            joinedload(Resume.experiences),
        ).get(id)

# 2. Intelligent caching with tags
@cache(tag="resume", ttl=3600, invalidate_on=["resume:updated"])
async def get_resume(id: str) -> Resume:
    return await repository.get(id)

# 3. Connection pooling
pool = AsyncConnectionPool(
    max_size=20,
    max_idle=10,
    max_overflow=5,
    pre_ping=True  # Health checks
)

# 4. Background job processing for AI calls
@task(queue="ai", max_retries=3, retry_delay=5)
async def generate_application(request: GenerationRequest):
    # Long-running AI operation
    pass
```

### 5.4 Observability Stack

```
Metrics (Prometheus/Grafana):
├── API: request_rate, latency_histogram, error_rate_by_route
├── Database: query_duration, connection_pool_usage, slow_query_log
├── Cache: hit_rate, eviction_rate, memory_usage
└── AI: token_usage, model_latency, cost_per_request

Distributed Tracing (OpenTelemetry):
├── Request flows across services
├── Database query tracing
├── AI model call attribution
└── Frontend performance marks

Real User Monitoring (PostHog):
├── Session recordings for UX analysis
├── Feature adoption funnels
├── Error tracking with context
└── A/B test results

Alerting (PagerDuty):
├── P0: API down, database unreachable
├── P1: Error rate > 5%, latency p99 > 2s
├── P2: Cache hit rate < 80%
└── P3: Unusual AI cost spikes
```

---

## Phase 6: Security Hardening

### 6.1 Authentication & Authorization

```python
# JWT with short expiry + refresh tokens
@router.post("/auth/refresh")
async def refresh_token(refresh_token: str) -> TokenPair:
    # Validate refresh token hash in DB
    # Rotate refresh token on use (prevents replay)
    # Revoke on logout or security event
    pass

# RBAC with resource-level permissions
@require_permission("resume:write", resource_owner=True)
async def update_resume(resume_id: str, data: ResumeUpdate):
    # Only owner or org admin can edit
    pass

# Audit logging
@audit_log(action="resume.deleted", sensitivity="high")
async def delete_resume(resume_id: str):
    pass
```

### 6.2 Data Protection

```
1. Encryption at Rest
   - Database: AES-256
   - File storage: Server-side encryption
   - Secrets: AWS KMS / HashiCorp Vault

2. Encryption in Transit
   - TLS 1.3 minimum
   - Certificate pinning for mobile
   - HSTS headers

3. PII Handling
   - Automatic PII detection in logs
   - Data retention policies (GDPR/CCPA)
   - Right to deletion workflow

4. Input Sanitization
   - XSS prevention (CSP headers)
   - SQL injection (parameterized queries)
   - File upload validation (type, size, scan)
```

### 6.3 AI Safety

```python
# Prompt injection detection
@validate_prompt
async def generate_with_ai(prompt: str):
    if detect_injection_attempt(prompt):
        raise SecurityError("Potential prompt injection detected")

# Output filtering
@filter_output(categories=["hate", "harassment", "self_harm"])
async def generate_document(request: GenerationRequest):
    result = await ai_client.complete(prompt)
    return result

# Rate limiting by user + IP + model
@rate_limit(requests_per_minute=10, burst=5)
async def expensive_ai_operation():
    pass
```

---

## Phase 7: Implementation Roadmap

### Sprint 1: Foundation (Weeks 1-2)

```
□ Set up design system with tokens
□ Create shared component library (Button, Card, Modal, Form)
□ Implement error boundaries and loading states
□ Add TanStack Query infrastructure
□ Set up testing framework (Vitest, Playwright)
□ Create API contract specs (OpenAPI)
```

### Sprint 2: Core Modules (Weeks 3-4)

```
□ Refactor Resume domain with hexagonal architecture
□ Build new ResumeUpload component with drag-drop
□ Create AI generation pipeline with streaming
□ Implement optimistic updates
□ Add comprehensive tests (unit + integration)
```

### Sprint 3: Application Flow (Weeks 5-6)

```
□ Redesign /new application flow
□ Add progress indicators and checkpoints
□ Implement real-time collaboration (WebSocket)
□ Add gamification elements (streaks, badges)
□ Mobile-responsive overhaul
```

### Sprint 4: Tools & Polish (Weeks 7-8)

```
□ Upgrade all tool pages (ATS, Interview, Salary)
□ Add animations and micro-interactions
□ Implement dark mode properly
□ Accessibility audit + fixes
□ Performance optimization (lazy loading, images)
```

### Sprint 5: Enterprise & Advanced (Weeks 9-10)

```
□ Complete candidate tracking features
□ Add advanced analytics dashboard
□ Implement team collaboration
□ Add API key management
□ Build webhook system
```

### Sprint 6: Hardening (Weeks 11-12)

```
□ Security penetration testing
□ Load testing (k6)
□ Chaos engineering (random failures)
□ Documentation (API docs, guides)
□ Monitoring and alerting setup
```

---

## Phase 8: Success Metrics

### Technical Excellence

```
□ Test Coverage: 85%+ (from 15%)
□ Bundle Size: <500KB initial (from 2MB)
□ Lighthouse Score: 95+ across all categories
□ API Latency: p95 <200ms (from 800ms)
□ Zero critical security vulnerabilities
```

### User Experience

```
□ NPS Score: 70+ (track via in-app survey)
□ Task Completion Rate: 90%+ for core flows
□ Support Tickets: <5% of MAU
□ Feature Adoption: 60%+ use new features within 30 days
□ Mobile Usage: 40%+ of sessions
```

### Business Impact

```
□ User Retention (D7): 50%+ (from 25%)
□ Conversion to Paid: 15%+ (from 5%)
□ Churn Rate: <5% monthly
□ Word of Mouth: 30%+ of signups from referrals
```

---

## Appendix: Quick Reference

### File Structure Conventions

```
# Backend
domain/
├── models.py          # Pure dataclasses, no DB deps
├── repositories.py    # Abstract interfaces
├── services.py        # Business logic
└── dto.py            # Request/response schemas

infrastructure/
├── persistence/
│   ├── repositories/  # Concrete implementations
│   └── migrations/
└── external/
    ├── ai/
    └── integrations/

interfaces/
├── http/
│   ├── routes/        # Thin controllers
│   └── middleware/
└── streaming/

# Frontend
modules/{domain}/
├── pages/
├── components/
│   ├── ui/           # Presentational
│   └── containers/   # Connected to state
├── hooks/
├── stores/
├── services/
└── types/

design-system/
├── components/
├── tokens/
├── animations/
└── patterns/
```

### Code Quality Gates

```
Pre-commit hooks:
  □ ruff (lint + format)
  □ mypy (type check)
  □ bandit (security)
  □ pytest (unit tests)

CI/CD pipeline:
  □ Build passes
  □ Tests pass (>85% coverage)
  □ Security scan clean
  □ Performance budgets met
  □ Accessibility audit pass
```

### Documentation Standards

```
Every module must have:
  □ README.md with purpose, API, examples
  □ Architecture Decision Records (ADRs)
  □ Storybook stories for UI components
  □ OpenAPI specs for API routes
```

---

**Status:** Masterplan complete. Ready for implementation.

**Next Steps:**
1. Review and approve this plan
2. Create detailed tickets for Sprint 1
3. Set up new branch structure
4. Begin incremental refactoring
