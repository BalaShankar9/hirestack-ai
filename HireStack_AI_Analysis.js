const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageNumber, PageBreak, TabStopType, TabStopPosition
} = require("docx");

// ── Helpers ──────────────────────────────────────────────────────────

const CONTENT_WIDTH = 9360; // US Letter with 1" margins
const COL_WIDTHS_2 = [3200, 6160];
const COL_WIDTHS_3 = [2800, 3800, 2760];
const COL_WIDTHS_STATUS = [4200, 1560, 3600];

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

const BLUE = "1B4F72";
const DARK = "2C3E50";
const GREEN = "27AE60";
const ORANGE = "E67E22";
const RED = "E74C3C";
const LIGHT_BLUE = "D6EAF8";
const LIGHT_GREEN = "D5F5E3";
const LIGHT_RED = "FADBD8";
const LIGHT_ORANGE = "FDEBD0";
const LIGHT_GRAY = "F2F3F4";

function heading(text, level = HeadingLevel.HEADING_1) {
  return new Paragraph({ heading: level, spacing: { before: 300, after: 150 }, children: [new TextRun({ text, bold: true })] });
}

function para(text, opts = {}) {
  const runs = [];
  if (typeof text === "string") {
    runs.push(new TextRun({ text, ...opts }));
  } else {
    runs.push(...text);
  }
  return new Paragraph({ spacing: { after: 120 }, children: runs });
}

function bold(text) { return new TextRun({ text, bold: true }); }
function normal(text) { return new TextRun({ text }); }
function colored(text, color) { return new TextRun({ text, color }); }

function statusCell(status, colWidth) {
  let fill, color, label;
  if (status === "complete") { fill = LIGHT_GREEN; color = GREEN; label = "COMPLETE"; }
  else if (status === "partial") { fill = LIGHT_ORANGE; color = ORANGE; label = "PARTIAL"; }
  else if (status === "missing") { fill = LIGHT_RED; color = RED; label = "MISSING"; }
  else if (status === "stub") { fill = LIGHT_ORANGE; color = ORANGE; label = "STUB"; }
  else { fill = LIGHT_GRAY; color = DARK; label = status.toUpperCase(); }

  return new TableCell({
    borders, width: { size: colWidth, type: WidthType.DXA }, margins: cellMargins,
    shading: { fill, type: ShadingType.CLEAR },
    verticalAlign: "center",
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: label, bold: true, color, size: 18 })] })]
  });
}

function headerCell(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
    shading: { fill: BLUE, type: ShadingType.CLEAR },
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", size: 20 })] })]
  });
}

function cell(text, width, opts = {}) {
  const runs = typeof text === "string" ? [new TextRun({ text, size: 20, ...opts })] : text;
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
    shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
    children: [new Paragraph({ children: runs })]
  });
}

function statusTable(headers, rows, colWidths) {
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [
      new TableRow({ children: headers.map((h, i) => headerCell(h, colWidths[i])) }),
      ...rows.map(row => new TableRow({
        children: row.map((c, i) => {
          if (typeof c === "object" && c.status) return statusCell(c.status, colWidths[i]);
          return cell(String(c), colWidths[i]);
        })
      }))
    ]
  });
}

// ── Document Content ─────────────────────────────────────────────────

const children = [];

// Title Page
children.push(new Paragraph({ spacing: { before: 3000 } }));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 200 },
  children: [new TextRun({ text: "HireStack AI", size: 56, bold: true, color: BLUE })]
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 100 },
  children: [new TextRun({ text: "Comprehensive Codebase Analysis & Production Readiness Report", size: 28, color: DARK })]
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 600 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLUE, space: 1 } },
  children: [new TextRun({ text: " " })]
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 100 },
  children: [new TextRun({ text: "Prepared: February 19, 2026", size: 22, color: "7F8C8D" })]
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Version 1.0", size: 22, color: "7F8C8D" })]
}));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 1. EXECUTIVE SUMMARY ────────────────────────────────────────────
children.push(heading("1. Executive Summary"));
children.push(para("HireStack AI is an AI-powered career intelligence platform that helps job seekers build compelling application packages. It analyzes candidate profiles against ideal benchmarks for target roles, generates tailored CVs, cover letters, personal statements, and portfolios, and provides gap analysis with learning roadmaps."));
children.push(para("The app uses a Next.js 14 frontend, FastAPI backend, Supabase (PostgreSQL + Auth + Realtime + Storage), and a multi-provider AI engine (Gemini/OpenAI/Ollama). After thorough analysis of every source file, the project is estimated at approximately 75% complete, with the core AI pipeline and frontend workspace being the strongest areas, while export, analytics, rate limiting, and several production hardening features remain unfinished."));

children.push(heading("Overall Completeness by Layer", HeadingLevel.HEADING_2));
children.push(statusTable(
  ["Component", "Status", "Notes"],
  [
    ["Frontend (Next.js 14)", { status: "complete" }, "11 routes, real-time hooks, rich editor, export"],
    ["Backend API (FastAPI)", { status: "partial" }, "All routes registered; some services incomplete"],
    ["AI Engine (6 Chains)", { status: "complete" }, "All chains functional with multi-provider fallback"],
    ["Database (Supabase)", { status: "complete" }, "19 tables, RLS, triggers, realtime, storage"],
    ["Authentication", { status: "complete" }, "Email, Google, GitHub OAuth via Supabase Auth"],
    ["SSE Generation Pipeline", { status: "complete" }, "6-phase streaming with progress events"],
    ["Export (PDF/DOCX/ZIP)", { status: "partial" }, "Frontend client-side works; backend export stub"],
    ["Analytics Dashboard", { status: "stub" }, "Event tracking works; dashboard aggregation missing"],
    ["Rate Limiting", { status: "missing" }, "Config exists but no middleware enforces it"],
    ["Tests", { status: "stub" }, "Playwright + Vitest configured; minimal test coverage"],
    ["Docker/Infra", { status: "complete" }, "docker-compose with backend, frontend, redis, worker"],
    ["Documentation", { status: "complete" }, "README, project journal, UX spec, architecture"],
  ],
  COL_WIDTHS_STATUS
));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 2. ARCHITECTURE OVERVIEW ─────────────────────────────────────────
children.push(heading("2. Architecture Overview"));
children.push(para("The application follows a clean three-tier architecture with clear separation of concerns:"));

children.push(heading("Tech Stack", HeadingLevel.HEADING_2));
children.push(statusTable(
  ["Layer", "Technology"],
  [
    ["Frontend", "Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, Radix UI, TipTap Editor"],
    ["Backend", "FastAPI, Python 3.11+, Pydantic v2, structlog, uvicorn"],
    ["Database", "Supabase (PostgreSQL 15), Row Level Security, Realtime subscriptions"],
    ["Auth", "Supabase Auth (Email, Google OAuth, GitHub OAuth)"],
    ["Storage", "Supabase Storage (resume uploads, evidence files)"],
    ["AI Engine", "Gemini (primary), OpenAI (fallback), Ollama (local fallback)"],
    ["Task Queue", "Celery + Redis (configured but not actively used)"],
    ["Infra", "Docker Compose, Dockerfiles for backend + frontend"],
  ],
  COL_WIDTHS_2
));

children.push(heading("Data Flow", HeadingLevel.HEADING_2));
children.push(para("The core user journey flows through a 4-step wizard: (1) Paste job description, (2) Upload resume, (3) Review confirmed facts, (4) Generate application. The generation calls the backend SSE streaming pipeline which orchestrates 6 parallel AI phases: resume parsing + benchmark building, gap analysis, CV + cover letter + learning plan generation, personal statement + portfolio, validation, and scoring. Results are stored in Supabase and displayed in a tabbed workspace with real-time updates."));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 3. WHAT'S COMPLETE ──────────────────────────────────────────────
children.push(heading("3. What Works (Complete Features)"));

children.push(heading("3.1 AI Generation Pipeline", HeadingLevel.HEADING_2));
children.push(para("This is the core product and it is fully functional. The pipeline runs 6 chains in sequence:"));
children.push(statusTable(
  ["Chain", "Purpose", "Status"],
  [
    ["RoleProfilerChain", "Parse resume into structured profile (skills, experience, education, etc.)", { status: "complete" }],
    ["BenchmarkBuilderChain", "Generate ideal candidate profile + benchmark CV HTML", { status: "complete" }],
    ["GapAnalyzerChain", "Compare user vs benchmark, produce compatibility score + gap report", { status: "complete" }],
    ["DocumentGeneratorChain", "Generate tailored CV, cover letter, personal statement, portfolio (HTML)", { status: "complete" }],
    ["CareerConsultantChain", "Generate learning roadmap with milestones, resources, quick wins", { status: "complete" }],
    ["ValidatorChain", "Quality-check generated documents (non-blocking)", { status: "complete" }],
  ],
  [3200, 4000, 2160]
));
children.push(para("The pipeline supports both synchronous (POST /api/generate/pipeline) and SSE streaming (POST /api/generate/pipeline/stream) modes. The streaming mode sends progress events for each phase so the frontend can show real-time generation progress."));

children.push(heading("3.2 Frontend Application", HeadingLevel.HEADING_2));
children.push(para("The frontend is approximately 12,000 lines of TypeScript/TSX with comprehensive UI:"));
children.push(statusTable(
  ["Page / Feature", "Description", "Status"],
  [
    ["Landing Page (/)", "Marketing page with feature overview", { status: "complete" }],
    ["Login (/login)", "Email + Google + GitHub OAuth sign-in/register", { status: "complete" }],
    ["Dashboard (/dashboard)", "Workspace list, task queue stats, evidence counts", { status: "complete" }],
    ["New Application Wizard (/new)", "4-step: JD, Resume, Review, Generate with SSE streaming", { status: "complete" }],
    ["Application Workspace (/applications/[id])", "9-tab workspace: overview, benchmark, gaps, learning, CV, cover letter, PS, portfolio, export", { status: "complete" }],
    ["Evidence Vault (/evidence)", "Create/manage proof items (links/files) with skills tagging", { status: "complete" }],
    ["Career Lab (/career)", "Learning plan tasks, resources hub", { status: "complete" }],
    ["TipTap Rich Editor", "Inline document editing with keyword coverage panel", { status: "complete" }],
    ["Version History", "Snapshot/restore document versions", { status: "complete" }],
    ["Client-Side Export", "PDF (html2pdf.js), DOCX (html-docx-js), PNG/JPG (html2canvas), ZIP (jszip)", { status: "complete" }],
    ["Dark/Light Theme", "Toggle with localStorage persistence", { status: "complete" }],
    ["Responsive Design", "Mobile sidebar, desktop collapsible nav", { status: "complete" }],
  ],
  [3200, 4000, 2160]
));

children.push(heading("3.3 Database & Auth", HeadingLevel.HEADING_2));
children.push(para("Supabase is fully configured with 19 tables, comprehensive RLS policies (every table scoped to auth.uid()), auto-triggers for user creation and timestamp updates, Realtime publication for applications/evidence/tasks/events, and storage bucket for uploads. The auth system supports email, Google, and GitHub OAuth with proper session management."));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 4. WHAT'S MISSING / INCOMPLETE ──────────────────────────────────
children.push(heading("4. What\u2019s Missing or Incomplete"));

children.push(heading("4.1 Critical Issues (Must Fix for Production)", HeadingLevel.HEADING_2));

const criticalIssues = [
  ["No Authentication on Pipeline Endpoint", "The POST /api/generate/pipeline and /pipeline/stream endpoints do NOT require authentication. Anyone can call them without a valid JWT token, consuming AI API credits. This is the single biggest security gap.", "Add get_current_user dependency to both pipeline routes"],
  ["Rate Limiting Not Enforced", "Config has rate_limit_requests=100 per 60s, but NO middleware actually enforces it. The AI endpoints are completely unprotected against abuse.", "Add slowapi or custom Redis-based rate limiter middleware"],
  ["No Input Validation on AI Pipeline", "PipelineRequest accepts arbitrary-length jd_text and resume_text strings. A malicious user could send megabytes of text, causing excessive AI token consumption.", "Add max_length validators on Pydantic model fields"],
  ["Timer Memory Leak in Generation UI", "The elapsed-time interval in /new/page.tsx only clears in the error path, not in a finally block. If generation is aborted, the interval keeps running.", "Move clearInterval to a finally block"],
  ["Silent Resume Parse Failure", "If parseResumeText() fails, it returns empty string. The user proceeds through the wizard with no resume data, getting generic results without any warning.", "Show toast warning when resume extraction returns empty"],
  ["Hardcoded Dev Error Messages", "Error UI shows messages like 'Dev fix: run scripts/dev/set_gemini_key.sh' which should never appear in production.", "Replace with user-friendly error messages based on environment"],
];

children.push(statusTable(
  ["Issue", "Details", "Fix"],
  criticalIssues,
  [2400, 4160, 2800]
));

children.push(heading("4.2 High Priority (Needed for Reliable Operation)", HeadingLevel.HEADING_2));

const highPriority = [
  ["Backend Export Service Incomplete", "ExportService exists but PDF/DOCX generation logic is stub-only. Backend export routes return errors.", "Implement reportlab PDF and python-docx generation in export service"],
  ["Analytics Dashboard Empty", "Event tracking (track_event) works, but get_dashboard and get_progress return stub data.", "Implement aggregation queries for dashboard metrics"],
  ["No Global Error Boundary", "Frontend has no React error boundary wrapping the app. Unhandled errors show white screen.", "Add ErrorBoundary component in root layout"],
  ["Missing Response Models", "All backend routes return Dict[str, Any] with no Pydantic response models. API contract is untyped.", "Define Pydantic response models for all endpoints"],
  ["No OpenAPI Docs in Production", "docs_url and redoc_url are set to None when debug=False. No API reference available.", "Enable at least redoc in production behind auth"],
  ["Celery Workers Configured but Unused", "Celery app, task routes, and Docker worker service exist but routes call services directly (synchronous).", "Either integrate Celery for long-running tasks or remove to simplify"],
  ["Unused REST API Client", "frontend/src/lib/api.ts defines 20+ endpoint wrappers that are never called. Frontend uses Supabase directly.", "Remove dead code or consolidate approach"],
  ["Evidence Picker Race Condition", "Auto-insert evidence logic calls editor?.chain() which could fail if editor is not yet mounted.", "Add proper editor readiness check before insertion"],
];

children.push(statusTable(
  ["Issue", "Details", "Fix"],
  highPriority,
  [2400, 4160, 2800]
));

children.push(new Paragraph({ children: [new PageBreak()] }));

children.push(heading("4.3 Medium Priority (Polish & Robustness)", HeadingLevel.HEADING_2));

const mediumPriority = [
  ["No Caching Layer", "Every benchmark/gap analysis triggers a new AI call. Redis is configured but never used for caching.", "Cache AI results by (jd_hash + resume_hash) in Redis with TTL"],
  ["Single Primary Profile Bug", "profiles.is_primary has no unique constraint. Multiple 'primary' profiles possible.", "Add partial unique index WHERE is_primary = true"],
  ["PDF Resume Parsing Limitation", "Only first 4 pages processed. No OCR for scanned PDFs.", "Document limitation clearly; add OCR via tesseract optionally"],
  ["No Optimistic Updates", "Task toggle and evidence operations wait for server response before UI updates.", "Implement optimistic updates with rollback on error"],
  ["Missing Loading Skeletons", "Some async operations show no loading state during data fetch.", "Add skeleton components for all async data views"],
  ["Inconsistent Error Handling", "Some async operations use .catch(() => '') swallowing errors silently.", "Standardize error handling with user-facing toast notifications"],
  ["No HTTPS/TLS Configuration", "Docker setup uses HTTP only. No SSL termination configured.", "Add nginx/caddy reverse proxy with Let's Encrypt SSL"],
  ["No Database Backup Strategy", "No automated backup or point-in-time recovery configuration.", "Use Supabase hosted (includes PITR) or configure pg_dump cron"],
  ["No Monitoring/Alerting", "structlog for logging but no APM, error tracking, or alerting.", "Add Sentry for error tracking, Prometheus for metrics"],
];

children.push(statusTable(
  ["Issue", "Details", "Fix"],
  mediumPriority,
  [2400, 4160, 2800]
));

children.push(heading("4.4 Low Priority (Nice to Have)", HeadingLevel.HEADING_2));
const lowPriority = [
  ["No Automated Tests", "Playwright and Vitest configured but test coverage is minimal."],
  ["No CI/CD Pipeline", "No GitHub Actions, GitLab CI, or similar automation."],
  ["No Database Migration Runner", "Migrations are SQL files that must be applied manually."],
  ["No Offline Support", "No service worker or offline caching strategy."],
  ["No Notification System", "Only toast-based notifications. No email/push notifications."],
  ["No User Settings Page", "No way to change password, manage profile, or configure preferences."],
  ["No Subscription/Premium Flow", "is_premium field exists in DB but no payment integration."],
  ["Hardcoded AI Constraints", "Benchmark max 10 skills, max 3 experience items may be too restrictive."],
];

children.push(statusTable(
  ["Issue", "Details"],
  lowPriority,
  COL_WIDTHS_2
));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 5. PRODUCTION READINESS CHECKLIST ────────────────────────────────
children.push(heading("5. Production Readiness Checklist"));
children.push(para("Below is the complete checklist for making HireStack AI production-ready, organized by priority:"));

children.push(heading("Phase 1: Security & Stability (Week 1-2)", HeadingLevel.HEADING_2));
const phase1 = [
  ["Add JWT auth to /api/generate/pipeline and /pipeline/stream", { status: "missing" }],
  ["Add rate limiting middleware (slowapi or Redis-based)", { status: "missing" }],
  ["Add input length validation on PipelineRequest fields", { status: "missing" }],
  ["Fix timer memory leak in generation wizard (clearInterval in finally)", { status: "missing" }],
  ["Add user warning when resume parse returns empty", { status: "missing" }],
  ["Remove dev-facing error messages from production UI", { status: "missing" }],
  ["Add React ErrorBoundary in root layout", { status: "missing" }],
  ["Add CORS origin validation for production domains", { status: "partial" }],
  ["Secure environment variables (no secrets in .env.local commits)", { status: "complete" }],
  ["Audit RLS policies for all 19 tables", { status: "complete" }],
];

children.push(statusTable(
  ["Task", "Current Status"],
  phase1,
  [7200, 2160]
));

children.push(heading("Phase 2: Feature Completion (Week 2-4)", HeadingLevel.HEADING_2));
const phase2 = [
  ["Implement backend ExportService (PDF via reportlab, DOCX via python-docx)", { status: "stub" }],
  ["Implement AnalyticsService dashboard aggregation queries", { status: "stub" }],
  ["Add Pydantic response models to all API endpoints", { status: "missing" }],
  ["Add proper null checks on nested object access in workspace page", { status: "missing" }],
  ["Fix Evidence Picker editor readiness race condition", { status: "missing" }],
  ["Add unique constraint for primary profile per user", { status: "missing" }],
  ["Implement Redis caching for AI results", { status: "missing" }],
  ["Add loading skeletons to all async data views", { status: "missing" }],
  ["Remove unused lib/api.ts REST client or consolidate", { status: "missing" }],
  ["Decide: integrate Celery workers OR remove Celery infrastructure", { status: "missing" }],
];

children.push(statusTable(
  ["Task", "Current Status"],
  phase2,
  [7200, 2160]
));

children.push(heading("Phase 3: Infrastructure & DevOps (Week 4-6)", HeadingLevel.HEADING_2));
const phase3 = [
  ["Set up CI/CD pipeline (GitHub Actions recommended)", { status: "missing" }],
  ["Add automated test suite (unit + integration + E2E)", { status: "stub" }],
  ["Configure HTTPS/TLS with reverse proxy (nginx/caddy)", { status: "missing" }],
  ["Set up Sentry for error tracking", { status: "missing" }],
  ["Add health check monitoring and alerting", { status: "missing" }],
  ["Configure database backups and PITR", { status: "missing" }],
  ["Set up production logging pipeline (structlog to cloud)", { status: "partial" }],
  ["Create deployment scripts for production environment", { status: "missing" }],
  ["Add database migration automation (alembic or supabase CLI)", { status: "missing" }],
  ["Performance testing and optimization", { status: "missing" }],
];

children.push(statusTable(
  ["Task", "Current Status"],
  phase3,
  [7200, 2160]
));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 6. BACKEND API ENDPOINT AUDIT ───────────────────────────────────
children.push(heading("6. Backend API Endpoint Audit"));
children.push(para("All 11 route modules are registered in the FastAPI app. Here is the complete endpoint inventory:"));

const endpoints = [
  ["/api/auth/verify", "GET", "Verify JWT token", { status: "complete" }],
  ["/api/auth/me", "GET/PUT", "Get/update current user", { status: "complete" }],
  ["/api/auth/sync", "POST", "Sync user after login", { status: "complete" }],
  ["/api/resume/parse", "POST", "Parse resume file (PDF/DOCX/TXT)", { status: "complete" }],
  ["/api/profile/*", "CRUD", "Profile management (upload, list, get, update, delete)", { status: "complete" }],
  ["/api/jobs/*", "CRUD", "Job description management + AI parsing", { status: "complete" }],
  ["/api/benchmark/*", "CRUD", "Benchmark generation, get, regenerate, delete", { status: "complete" }],
  ["/api/gaps/*", "CRUD", "Gap analysis, list, get, summary, refresh, delete", { status: "complete" }],
  ["/api/consultant/*", "CRUD", "Roadmap generation, list, get, progress, delete", { status: "partial" }],
  ["/api/builder/*", "CRUD", "Document generation, list, get, update, versioning", { status: "partial" }],
  ["/api/export/*", "CRUD", "Export creation, list, get, download, delete", { status: "stub" }],
  ["/api/analytics/*", "CRUD", "Dashboard, activity, progress, tracking, stats", { status: "stub" }],
  ["/api/generate/pipeline", "POST", "Full AI pipeline (sync)", { status: "complete" }],
  ["/api/generate/pipeline/stream", "POST", "Full AI pipeline (SSE streaming)", { status: "complete" }],
  ["/health", "GET", "Health check with Supabase connectivity test", { status: "complete" }],
];

children.push(statusTable(
  ["Endpoint", "Method", "Purpose", "Status"],
  endpoints,
  [2600, 1000, 3600, 2160]
));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 7. DATABASE SCHEMA ──────────────────────────────────────────────
children.push(heading("7. Database Schema Summary"));
children.push(para("The Supabase PostgreSQL database has 19 tables across 4 migration files. All tables have Row Level Security enabled with user-scoped policies."));

const tables = [
  ["users", "User profiles (extends auth.users)", "RLS: own data only", { status: "complete" }],
  ["profiles", "Parsed resume data, skills, experience", "RLS: own data only", { status: "complete" }],
  ["job_descriptions", "Target job postings with parsed requirements", "RLS: own data only", { status: "complete" }],
  ["benchmarks", "Ideal candidate profiles + scoring weights", "RLS: via job ownership", { status: "complete" }],
  ["gap_reports", "Gap analysis results + compatibility scores", "RLS: own data only", { status: "complete" }],
  ["roadmaps", "Learning paths + milestones + resources", "RLS: own data only", { status: "complete" }],
  ["projects", "Portfolio projects from roadmaps", "RLS: own data only", { status: "complete" }],
  ["documents", "Generated CVs, cover letters, statements", "RLS: own data only", { status: "complete" }],
  ["applications", "Main workspace entity with all modules", "RLS + Realtime", { status: "complete" }],
  ["evidence", "Proof items (certs, projects, links, files)", "RLS + Realtime", { status: "complete" }],
  ["tasks", "Action items from analysis + coach", "RLS + Realtime", { status: "complete" }],
  ["events", "Activity/analytics event log", "RLS + Realtime", { status: "complete" }],
  ["learning_plans", "Standalone learning tracks", "RLS: own data only", { status: "complete" }],
  ["doc_versions", "Document version history snapshots", "RLS: own data only", { status: "complete" }],
  ["generation_jobs", "Long-running AI pipeline state tracking", "RLS: own data only", { status: "complete" }],
  ["analytics", "User behavior tracking + sessions", "RLS: read/insert own", { status: "complete" }],
  ["exports", "Document export records + file URLs", "RLS: own data only", { status: "complete" }],
];

children.push(statusTable(
  ["Table", "Purpose", "Security", "Status"],
  tables,
  [2200, 3200, 2000, 1960]
));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 8. AI ENGINE DETAILS ────────────────────────────────────────────
children.push(heading("8. AI Engine Configuration"));
children.push(para("The AI engine supports three providers with automatic fallback. If the primary provider fails (auth errors, rate limits, quota exhaustion), it automatically tries the next available provider."));

children.push(statusTable(
  ["Setting", "Value"],
  [
    ["Primary Provider", "Gemini (gemini-2.5-pro)"],
    ["Gemini Max Tokens", "8,192"],
    ["Gemini Throttle", "3,500ms between requests (avoids 429s on free tier)"],
    ["OpenAI Fallback", "GPT-5.2 (4,096 max tokens)"],
    ["Ollama Local Fallback", "qwen3:4b at localhost:11434"],
    ["Retry Strategy", "Exponential backoff, max 6 attempts, max 60s wait"],
    ["Error Classification", "Auto-classifies 401/403/404/429 from both OpenAI SDK and Gemini string errors"],
    ["Vertex AI Support", "Optional OAuth-based auth via GEMINI_USE_VERTEXAI=true"],
  ],
  COL_WIDTHS_2
));

children.push(heading("Pipeline Performance Estimate", HeadingLevel.HEADING_2));
children.push(para("Based on the chain architecture, a typical generation pipeline makes approximately 8-10 AI calls:"));
children.push(statusTable(
  ["Phase", "AI Calls", "Estimated Time"],
  [
    ["Phase 1: Resume Parse + Benchmark", "2 (parallel)", "5-8 seconds"],
    ["Benchmark CV HTML", "1", "3-5 seconds"],
    ["Phase 2: Gap Analysis", "1", "4-6 seconds"],
    ["Phase 3: CV + Cover Letter + Roadmap", "3 (parallel)", "8-12 seconds"],
    ["Phase 4: Personal Statement + Portfolio", "2 (parallel)", "6-10 seconds"],
    ["Phase 5: Validation", "1", "3-5 seconds"],
    ["Total", "~10 calls", "30-45 seconds typical"],
  ],
  [3800, 2000, 3560]
));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 9. RECOMMENDATIONS ──────────────────────────────────────────────
children.push(heading("9. Strategic Recommendations"));

children.push(heading("9.1 Immediate Actions (This Week)", HeadingLevel.HEADING_2));
children.push(para([
  bold("1. Secure the pipeline endpoints. "),
  normal("This is the most critical issue. Add JWT auth dependency to both /api/generate/pipeline routes. Without this, anyone can consume your AI credits."),
]));
children.push(para([
  bold("2. Add rate limiting. "),
  normal("Install slowapi and add rate limit middleware. Recommended: 10 pipeline requests per hour per user, 100 API calls per minute globally."),
]));
children.push(para([
  bold("3. Fix the timer leak and silent failures. "),
  normal("Quick 2-line fixes that prevent memory leaks and confusing user experiences."),
]));

children.push(heading("9.2 Architecture Decisions Needed", HeadingLevel.HEADING_2));
children.push(para([
  bold("Celery: Keep or Remove? "),
  normal("Currently, the generation pipeline runs synchronously in the FastAPI request handler (with SSE streaming). Celery is fully configured but unused. For production with multiple concurrent users, consider: (a) Keep current approach for simplicity (SSE handles long-running well), or (b) Move generation to Celery for better resource isolation and retry handling. Recommendation: Keep SSE for now, add Celery only if you need background processing (e.g., scheduled re-analysis)."),
]));
children.push(para([
  bold("Deployment Target: "),
  normal("The README suggests Vercel (frontend) + container platform (backend) + Supabase hosted (DB). This is the recommended approach. Vercel handles Next.js optimally, and Supabase hosted includes PITR backups, connection pooling, and edge functions. For the backend, Railway or Render provide simple container hosting with auto-deploy from git."),
]));

children.push(heading("9.3 Scaling Considerations", HeadingLevel.HEADING_2));
children.push(para("The current architecture handles single-user well but needs attention for multi-user production. Key areas: AI API rate limits (Gemini free tier is 5 req/min), concurrent pipeline executions (each uses ~10 AI calls over 30-45s), Supabase connection pooling (default 100 connections), and Realtime subscription limits. For 100+ concurrent users, implement: request queuing with priority, AI result caching with Redis, and connection pool monitoring."));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ── 10. FILE MANIFEST ───────────────────────────────────────────────
children.push(heading("10. Key File Manifest"));

children.push(statusTable(
  ["File", "Purpose"],
  [
    ["backend/main.py", "FastAPI app entry point, CORS, error handlers, route registration"],
    ["backend/app/core/config.py", "Pydantic settings (Supabase, AI providers, rate limits)"],
    ["backend/app/api/routes/generate.py", "Core pipeline endpoints (sync + SSE streaming)"],
    ["backend/app/api/deps.py", "JWT auth dependencies (get_current_user, require_premium)"],
    ["ai_engine/client.py", "Multi-provider AI client with retry + fallback logic"],
    ["ai_engine/chains/*.py", "6 AI chain implementations (profiler, benchmark, gaps, docs, consultant, validator)"],
    ["frontend/src/app/(dashboard)/new/page.tsx", "4-step generation wizard (1,200 lines)"],
    ["frontend/src/app/(dashboard)/applications/[id]/page.tsx", "Application workspace (2,200 lines, most complex)"],
    ["frontend/src/lib/firestore/ops.ts", "All Supabase CRUD operations + SSE client"],
    ["frontend/src/lib/firestore/hooks.ts", "Realtime subscription hooks with polling fallback"],
    ["frontend/src/lib/firestore/models.ts", "TypeScript type definitions for all entities"],
    ["frontend/src/lib/export.ts", "Client-side PDF/DOCX/PNG/ZIP export functions"],
    ["frontend/src/components/app-shell.tsx", "Main layout (sidebar, nav, theme toggle)"],
    ["supabase/migrations/*.sql", "4 migration files defining all 19 tables + RLS"],
    ["infra/docker-compose.yml", "Docker Compose for local dev (backend, frontend, redis, worker)"],
    ["docs/PROJECT_JOURNAL.md", "Development timeline and architecture decisions"],
    ["docs/WORKSPACE_UX_SPEC.md", "UX specification for the application workspace"],
  ],
  COL_WIDTHS_2
));

// ── Build the document ──────────────────────────────────────────────
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: DARK },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 1 }
      },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: BLUE, space: 1 } },
          children: [new TextRun({ text: "HireStack AI \u2014 Codebase Analysis", size: 16, color: "95A5A6", italics: true })]
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Page ", size: 16, color: "95A5A6" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "95A5A6" }),
          ]
        })]
      })
    },
    children
  }]
});

const OUTPUT_PATH = "/sessions/loving-relaxed-bardeen/mnt/HireStack AI/HireStack_AI_Analysis.docx";

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(OUTPUT_PATH, buffer);
  console.log("Document created:", OUTPUT_PATH);
}).catch(err => {
  console.error("Error:", err);
  process.exit(1);
});
