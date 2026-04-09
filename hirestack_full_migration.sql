-- HireStack AI — Full Database Schema
-- Local Supabase migration

-- ────────────────────────────────────────────────────────────────
-- Extensions
-- ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ────────────────────────────────────────────────────────────────
-- Users (extends Supabase Auth)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    is_premium BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile" ON public.users
    FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON public.users
    FOR UPDATE USING (auth.uid() = id);
-- Service role can do anything (bypasses RLS)
CREATE POLICY "Service role full access on users" ON public.users
    FOR ALL USING (auth.role() = 'service_role');

-- ────────────────────────────────────────────────────────────────
-- Profiles (parsed resume data)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name VARCHAR(255),
    title VARCHAR(255),
    summary TEXT,
    raw_resume_text TEXT,
    file_url TEXT,
    file_type VARCHAR(50),
    parsed_data JSONB,
    contact_info JSONB,
    skills JSONB,
    experience JSONB,
    education JSONB,
    certifications JSONB,
    languages JSONB,
    projects JSONB,
    achievements JSONB,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own profiles" ON public.profiles
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on profiles" ON public.profiles
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON public.profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_is_primary ON public.profiles(user_id, is_primary);

-- ────────────────────────────────────────────────────────────────
-- Job Descriptions
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.job_descriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    location VARCHAR(255),
    job_type VARCHAR(50),
    experience_level VARCHAR(50),
    salary_range VARCHAR(100),
    description TEXT NOT NULL,
    raw_text TEXT,
    parsed_data JSONB,
    required_skills JSONB,
    preferred_skills JSONB,
    requirements JSONB,
    responsibilities JSONB,
    benefits JSONB,
    company_info JSONB,
    source_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.job_descriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own jobs" ON public.job_descriptions
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on jobs" ON public.job_descriptions
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_job_descriptions_user_id ON public.job_descriptions(user_id);

-- ────────────────────────────────────────────────────────────────
-- Benchmarks (ideal candidate profile)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.benchmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_description_id UUID NOT NULL REFERENCES public.job_descriptions(id) ON DELETE CASCADE,
    ideal_profile JSONB,
    ideal_skills JSONB,
    ideal_experience JSONB,
    ideal_education JSONB,
    ideal_certifications JSONB,
    ideal_cv TEXT,
    ideal_cover_letter TEXT,
    ideal_portfolio JSONB,
    ideal_case_studies JSONB,
    ideal_action_plan JSONB,
    ideal_proposals JSONB,
    compatibility_criteria JSONB,
    scoring_weights JSONB,
    version INTEGER DEFAULT 1,
    status VARCHAR(50) DEFAULT 'generated',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.benchmarks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view benchmarks for own jobs" ON public.benchmarks
    FOR ALL USING (
        job_description_id IN (SELECT id FROM public.job_descriptions WHERE user_id = auth.uid())
    );
CREATE POLICY "Service role full access on benchmarks" ON public.benchmarks
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_benchmarks_job_id ON public.benchmarks(job_description_id);

-- ────────────────────────────────────────────────────────────────
-- Gap Reports
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.gap_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    benchmark_id UUID NOT NULL REFERENCES public.benchmarks(id) ON DELETE CASCADE,
    compatibility_score INTEGER DEFAULT 0,
    skill_score INTEGER DEFAULT 0,
    experience_score INTEGER DEFAULT 0,
    education_score INTEGER DEFAULT 0,
    certification_score INTEGER DEFAULT 0,
    project_score INTEGER DEFAULT 0,
    skill_gaps JSONB,
    experience_gaps JSONB,
    education_gaps JSONB,
    certification_gaps JSONB,
    project_gaps JSONB,
    strengths JSONB,
    recommendations JSONB,
    priority_actions JSONB,
    summary JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.gap_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own gap reports" ON public.gap_reports
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on gap_reports" ON public.gap_reports
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_gap_reports_user_id ON public.gap_reports(user_id);

-- ────────────────────────────────────────────────────────────────
-- Roadmaps
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.roadmaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    gap_report_id UUID NOT NULL REFERENCES public.gap_reports(id) ON DELETE CASCADE,
    title VARCHAR(255) DEFAULT 'Career Roadmap',
    description TEXT,
    learning_path JSONB,
    milestones JSONB,
    timeline JSONB,
    resources JSONB,
    skill_development JSONB,
    certification_path JSONB,
    experience_recommendations JSONB,
    action_items JSONB,
    progress JSONB,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.roadmaps ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own roadmaps" ON public.roadmaps
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on roadmaps" ON public.roadmaps
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_roadmaps_user_id ON public.roadmaps(user_id);

-- ────────────────────────────────────────────────────────────────
-- Projects
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    roadmap_id UUID REFERENCES public.roadmaps(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    summary TEXT,
    tech_stack JSONB,
    difficulty VARCHAR(50),
    estimated_duration VARCHAR(100),
    implementation_guide JSONB,
    milestones JSONB,
    features JSONB,
    skills_developed JSONB,
    learning_outcomes JSONB,
    resources JSONB,
    "references" JSONB,
    status VARCHAR(50) DEFAULT 'suggested',
    progress INTEGER DEFAULT 0,
    repo_url TEXT,
    demo_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own projects" ON public.projects
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on projects" ON public.projects
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON public.projects(user_id);

-- ────────────────────────────────────────────────────────────────
-- Documents (CVs, cover letters, etc.)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    structured_content JSONB,
    metadata JSONB,
    target_job_id UUID,
    target_company VARCHAR(255),
    version INTEGER DEFAULT 1,
    parent_id UUID,
    template_id VARCHAR(100),
    status VARCHAR(50) DEFAULT 'draft',
    is_benchmark BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own documents" ON public.documents
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on documents" ON public.documents
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_documents_user_id ON public.documents(user_id);

-- ────────────────────────────────────────────────────────────────
-- Exports
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    document_ids UUID[] NOT NULL DEFAULT '{}',
    format VARCHAR(20) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_url TEXT,
    file_size INTEGER,
    options JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

ALTER TABLE public.exports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own exports" ON public.exports
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on exports" ON public.exports
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_exports_user_id ON public.exports(user_id);

-- ────────────────────────────────────────────────────────────────
-- Analytics
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB,
    session_id VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    entity_type VARCHAR(50),
    entity_id UUID,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.analytics ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own analytics" ON public.analytics
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own analytics" ON public.analytics
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Service role full access on analytics" ON public.analytics
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_analytics_user_id ON public.analytics(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON public.analytics(event_type);

-- ────────────────────────────────────────────────────────────────
-- Applications (workspace documents — the main entity the frontend uses)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'Untitled Application',
    status VARCHAR(50) DEFAULT 'draft',

    -- Step-1 confirmed facts
    confirmed_facts JSONB,
    facts_locked BOOLEAN DEFAULT FALSE,

    -- Module statuses  { benchmark: { state, progress, error, updatedAt }, ... }
    modules JSONB NOT NULL DEFAULT '{
        "benchmark": {"state": "idle"},
        "gaps": {"state": "idle"},
        "learningPlan": {"state": "idle"},
        "cv": {"state": "idle"},
        "coverLetter": {"state": "idle"},
        "personalStatement": {"state": "idle"},
        "portfolio": {"state": "idle"},
        "scorecard": {"state": "idle"}
    }'::jsonb,

    -- Module outputs
    benchmark JSONB,
    gaps JSONB,
    learning_plan JSONB,
    cv_html TEXT,
    cover_letter_html TEXT,
    personal_statement_html TEXT,
    portfolio_html TEXT,
    scorecard JSONB,
    validation JSONB,

    -- Version histories
    cv_versions JSONB DEFAULT '[]'::jsonb,
    cl_versions JSONB DEFAULT '[]'::jsonb,
    ps_versions JSONB DEFAULT '[]'::jsonb,
    portfolio_versions JSONB DEFAULT '[]'::jsonb,

    -- Scores snapshot
    scores JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own applications" ON public.applications
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on applications" ON public.applications
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_applications_user_id ON public.applications(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON public.applications(status);

-- ────────────────────────────────────────────────────────────────
-- Evidence (proof items: certs, projects, links, files)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    kind VARCHAR(10) NOT NULL DEFAULT 'link',       -- 'link' | 'file'
    type VARCHAR(50) NOT NULL DEFAULT 'other',      -- cert | project | course | award | publication | other
    title VARCHAR(255) NOT NULL,
    description TEXT,
    url TEXT,
    storage_url TEXT,
    file_url TEXT,
    file_name VARCHAR(255),
    skills JSONB DEFAULT '[]'::jsonb,
    tools JSONB DEFAULT '[]'::jsonb,
    tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.evidence ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own evidence" ON public.evidence
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on evidence" ON public.evidence
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_evidence_user_id ON public.evidence(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_application_id ON public.evidence(application_id);

-- ────────────────────────────────────────────────────────────────
-- Tasks (actionable items generated from modules or manual)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'manual',   -- benchmark | gaps | learningPlan | coach | manual
    title VARCHAR(255) NOT NULL,
    description TEXT,
    detail TEXT,
    why TEXT,
    status VARCHAR(20) DEFAULT 'todo',              -- todo | in-progress | done | skipped
    priority VARCHAR(10) DEFAULT 'medium',          -- low | medium | high
    due_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own tasks" ON public.tasks
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on tasks" ON public.tasks
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON public.tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_application_id ON public.tasks(application_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON public.tasks(status);

-- ────────────────────────────────────────────────────────────────
-- Events (analytics / activity log)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    event VARCHAR(100) NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own events" ON public.events
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on events" ON public.events
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_events_user_id ON public.events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_application_id ON public.events(application_id);

-- ────────────────────────────────────────────────────────────────
-- Learning Plans (standalone table for career lab)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.learning_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    focus JSONB DEFAULT '[]'::jsonb,
    plan JSONB DEFAULT '[]'::jsonb,
    resources JSONB DEFAULT '[]'::jsonb,
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.learning_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own learning_plans" ON public.learning_plans
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on learning_plans" ON public.learning_plans
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_learning_plans_user_id ON public.learning_plans(user_id);

-- ────────────────────────────────────────────────────────────────
-- Doc Versions (version history for documents)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.doc_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE CASCADE,
    doc_type VARCHAR(50) NOT NULL,    -- 'cv' | 'coverLetter'
    html TEXT NOT NULL DEFAULT '',
    label VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.doc_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own doc_versions" ON public.doc_versions
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on doc_versions" ON public.doc_versions
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_doc_versions_application_id ON public.doc_versions(application_id);

-- ────────────────────────────────────────────────────────────────
-- Auto-create user row on auth.users signup
-- ────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email, full_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.email,
        NEW.raw_user_meta_data->>'full_name',
        NEW.raw_user_meta_data->>'avatar_url'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ────────────────────────────────────────────────────────────────
-- Auto-update updated_at on row modification
-- ────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers to all mutable tables
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'users', 'profiles', 'job_descriptions', 'benchmarks',
        'gap_reports', 'roadmaps', 'projects', 'documents', 'exports',
        'applications', 'evidence', 'tasks', 'learning_plans'
    ]) LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS update_%s_updated_at ON public.%I; '
            'CREATE TRIGGER update_%s_updated_at BEFORE UPDATE ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();',
            t, t, t, t
        );
    END LOOP;
END;
$$;

-- ────────────────────────────────────────────────────────────────
-- Storage bucket for file uploads (resumes, evidence files)
-- ────────────────────────────────────────────────────────────────
INSERT INTO storage.buckets (id, name, public)
VALUES ('uploads', 'uploads', false)
ON CONFLICT (id) DO NOTHING;

-- Allow authenticated users to upload/read their own files
CREATE POLICY "Users can upload files" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'uploads' AND (storage.foldername(name))[1] = auth.uid()::text);

CREATE POLICY "Users can read own files" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'uploads' AND (storage.foldername(name))[1] = auth.uid()::text);

CREATE POLICY "Service role storage access" ON storage.objects
    FOR ALL USING (auth.role() = 'service_role');
-- Realtime setup for HireStack AI
-- Ensures Postgres tables are configured for Supabase Realtime (postgres_changes).

-- 1) Ensure the publication exists (Supabase creates this by default, but keep it safe)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    CREATE PUBLICATION supabase_realtime;
  END IF;
END
$$;

-- HireStack AI — Application Generation Intelligence Columns
-- Aligns the applications table with generated document strategy and company intel outputs.

ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS discovered_documents JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS generated_documents JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS benchmark_documents JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS document_strategy TEXT,
    ADD COLUMN IF NOT EXISTS company_intel JSONB DEFAULT '{}'::jsonb;

-- 2) Enable REPLICA IDENTITY FULL so that DELETE events include all columns
--    (required for filtered subscriptions on DELETE)
ALTER TABLE public.applications REPLICA IDENTITY FULL;
ALTER TABLE public.evidence REPLICA IDENTITY FULL;
ALTER TABLE public.tasks REPLICA IDENTITY FULL;
ALTER TABLE public.events REPLICA IDENTITY FULL;

-- 3) Add tables to the supabase_realtime publication (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'applications'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.applications;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'evidence'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.evidence;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'tasks'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.tasks;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'events'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.events;
  END IF;
END
$$;
-- HireStack AI — Add missing application document columns
-- This migration aligns the `applications` table with the frontend modules:
-- Personal Statement, Portfolio, validation metadata, and version histories.

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS personal_statement_html TEXT,
  ADD COLUMN IF NOT EXISTS portfolio_html TEXT,
  ADD COLUMN IF NOT EXISTS validation JSONB,
  ADD COLUMN IF NOT EXISTS ps_versions JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS portfolio_versions JSONB DEFAULT '[]'::jsonb;

-- HireStack AI — Generation Jobs
-- Adds a DB-backed job record for long-running AI pipeline runs so the UI can
-- resume progress after refresh and support cancellation/retry without getting stuck.

CREATE TABLE IF NOT EXISTS public.generation_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,

  -- Which modules were requested for this run (e.g. {benchmark,gaps,cv})
  requested_modules TEXT[] NOT NULL DEFAULT '{}'::text[],

  -- queued | running | succeeded | failed | cancelled
  status VARCHAR(20) NOT NULL DEFAULT 'queued',

  -- UI-friendly progress fields (0-100)
  progress INTEGER NOT NULL DEFAULT 0,
  phase TEXT,
  message TEXT,

  -- Cancellation flag checked between phases (best-effort)
  cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,

  -- Final response payload (same shape as /api/generate/pipeline response)
  result JSONB,
  error_message TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.generation_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own generation jobs" ON public.generation_jobs
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Service role full access on generation_jobs" ON public.generation_jobs
  FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_generation_jobs_user_id ON public.generation_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_application_id ON public.generation_jobs(application_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_status ON public.generation_jobs(status);

-- Keep updated_at in sync with the repo's shared trigger function.
DROP TRIGGER IF EXISTS update_generation_jobs_updated_at ON public.generation_jobs;
CREATE TRIGGER update_generation_jobs_updated_at
  BEFORE UPDATE ON public.generation_jobs
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Realtime support (optional, but keeps local + prod behavior aligned)
ALTER TABLE public.generation_jobs REPLICA IDENTITY FULL;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'generation_jobs'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.generation_jobs;
  END IF;
END
$$;

-- HireStack AI — Generation Job Events + Snapshot Fields
-- Persists a detailed append-only event log for long-running generation jobs.

ALTER TABLE public.generation_jobs
    ADD COLUMN IF NOT EXISTS current_agent TEXT,
    ADD COLUMN IF NOT EXISTS completed_steps INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_steps INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS active_sources_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS public.generation_job_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES public.generation_jobs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    event_name TEXT NOT NULL,
    agent_name TEXT,
    stage TEXT,
    status TEXT,
    message TEXT NOT NULL DEFAULT '',
    source TEXT,
    url TEXT,
    latency_ms INTEGER,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(job_id, sequence_no)
);

ALTER TABLE public.generation_job_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own generation job events" ON public.generation_job_events
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Service role full access on generation_job_events" ON public.generation_job_events
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_generation_job_events_job_sequence
    ON public.generation_job_events(job_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_generation_job_events_application_id
    ON public.generation_job_events(application_id);
CREATE INDEX IF NOT EXISTS idx_generation_job_events_user_id
    ON public.generation_job_events(user_id);

ALTER TABLE public.generation_job_events REPLICA IDENTITY FULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
            AND schemaname = 'public'
            AND tablename = 'generation_job_events'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.generation_job_events;
    END IF;
END
$$;

-- HireStack AI — Fix gap_reports: add missing status and updated_at columns
-- Also adds the update_updated_at trigger for gap_reports and exports.

ALTER TABLE public.gap_reports
  ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Apply updated_at trigger to gap_reports
DROP TRIGGER IF EXISTS update_gap_reports_updated_at ON public.gap_reports;
CREATE TRIGGER update_gap_reports_updated_at
  BEFORE UPDATE ON public.gap_reports
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Apply updated_at trigger to exports (was also missing)
DROP TRIGGER IF EXISTS update_exports_updated_at ON public.exports;
CREATE TRIGGER update_exports_updated_at
  BEFORE UPDATE ON public.exports
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
-- HireStack AI — Elite Upgrades Migration
-- Adds tables for: ATS Scanner, Evidence Mapper, A/B Doc Lab, Interview Simulator,
-- Career Analytics, Salary Coach, Collaborative Review, Job Sync, Micro-Learning, API Keys

-- ────────────────────────────────────────────────────────────────
-- 1. ATS Scans (Recruiter Lens)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ats_scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    document_id UUID REFERENCES public.documents(id) ON DELETE SET NULL,
    job_description_id UUID REFERENCES public.job_descriptions(id) ON DELETE SET NULL,
    document_content TEXT,
    ats_score INTEGER DEFAULT 0,
    keyword_match_rate NUMERIC(5,2) DEFAULT 0,
    readability_score NUMERIC(5,2) DEFAULT 0,
    format_score NUMERIC(5,2) DEFAULT 0,
    section_scores JSONB DEFAULT '{}'::jsonb,
    matched_keywords JSONB DEFAULT '[]'::jsonb,
    missing_keywords JSONB DEFAULT '[]'::jsonb,
    formatting_issues JSONB DEFAULT '[]'::jsonb,
    recommendations JSONB DEFAULT '[]'::jsonb,
    pass_prediction VARCHAR(20) DEFAULT 'unknown',  -- pass | borderline | fail | unknown
    recruiter_view_html TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.ats_scans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own ats_scans" ON public.ats_scans
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on ats_scans" ON public.ats_scans
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_ats_scans_user_id ON public.ats_scans(user_id);
CREATE INDEX IF NOT EXISTS idx_ats_scans_application_id ON public.ats_scans(application_id);

-- ────────────────────────────────────────────────────────────────
-- 2. Evidence Mappings (Smart Auto-Mapper)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.evidence_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    evidence_id UUID NOT NULL REFERENCES public.evidence(id) ON DELETE CASCADE,
    gap_report_id UUID REFERENCES public.gap_reports(id) ON DELETE SET NULL,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    skill_name VARCHAR(255) NOT NULL,
    gap_severity VARCHAR(50),
    relevance_score NUMERIC(5,2) DEFAULT 0,
    ai_explanation TEXT,
    is_confirmed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.evidence_mappings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own evidence_mappings" ON public.evidence_mappings
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on evidence_mappings" ON public.evidence_mappings
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_evidence_mappings_user_id ON public.evidence_mappings(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_mappings_evidence_id ON public.evidence_mappings(evidence_id);

-- ────────────────────────────────────────────────────────────────
-- 3. Document Variants (A/B Doc Lab)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.doc_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    document_type VARCHAR(50) NOT NULL,  -- cv | cover_letter | personal_statement
    variant_name VARCHAR(100) NOT NULL,  -- conservative | balanced | creative
    tone VARCHAR(50) NOT NULL DEFAULT 'balanced',
    content TEXT NOT NULL DEFAULT '',
    ats_score INTEGER,
    readability_score NUMERIC(5,2),
    keyword_density NUMERIC(5,2),
    word_count INTEGER,
    ai_analysis JSONB DEFAULT '{}'::jsonb,
    is_selected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.doc_variants ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own doc_variants" ON public.doc_variants
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on doc_variants" ON public.doc_variants
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_doc_variants_user_id ON public.doc_variants(user_id);
CREATE INDEX IF NOT EXISTS idx_doc_variants_application_id ON public.doc_variants(application_id);

-- ────────────────────────────────────────────────────────────────
-- 4. Interview Sessions & Answers (Interview Simulator)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.interview_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    job_title VARCHAR(255),
    company VARCHAR(255),
    interview_type VARCHAR(50) NOT NULL DEFAULT 'behavioral',  -- behavioral | technical | situational | mixed
    difficulty VARCHAR(20) DEFAULT 'medium',  -- easy | medium | hard
    questions JSONB DEFAULT '[]'::jsonb,
    overall_score NUMERIC(5,2),
    overall_feedback TEXT,
    strengths JSONB DEFAULT '[]'::jsonb,
    improvements JSONB DEFAULT '[]'::jsonb,
    duration_seconds INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'in_progress',  -- in_progress | completed | abandoned
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.interview_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    question_index INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    question_type VARCHAR(50),
    answer_text TEXT NOT NULL DEFAULT '',
    score NUMERIC(5,2),
    star_scores JSONB DEFAULT '{}'::jsonb,  -- { situation, task, action, result }
    feedback TEXT,
    strengths JSONB DEFAULT '[]'::jsonb,
    improvements JSONB DEFAULT '[]'::jsonb,
    model_answer TEXT,
    duration_seconds INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.interview_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own interview_sessions" ON public.interview_sessions
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on interview_sessions" ON public.interview_sessions
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_interview_sessions_user_id ON public.interview_sessions(user_id);

ALTER TABLE public.interview_answers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own interview_answers" ON public.interview_answers
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on interview_answers" ON public.interview_answers
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_interview_answers_session_id ON public.interview_answers(session_id);

-- ────────────────────────────────────────────────────────────────
-- 5. Career Snapshots (Career Analytics 2.0)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.career_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    overall_score NUMERIC(5,2),
    technical_score NUMERIC(5,2),
    experience_score NUMERIC(5,2),
    education_score NUMERIC(5,2),
    applications_count INTEGER DEFAULT 0,
    interviews_completed INTEGER DEFAULT 0,
    avg_ats_score NUMERIC(5,2),
    skills_gained JSONB DEFAULT '[]'::jsonb,
    industry_percentile NUMERIC(5,2),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.career_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own career_snapshots" ON public.career_snapshots
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on career_snapshots" ON public.career_snapshots
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_career_snapshots_user_id ON public.career_snapshots(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_career_snapshots_unique ON public.career_snapshots(user_id, snapshot_date);

-- ────────────────────────────────────────────────────────────────
-- 6. Salary Analyses (Salary Negotiation Coach)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.salary_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    job_title VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    location VARCHAR(255),
    experience_years NUMERIC(4,1),
    current_salary NUMERIC(12,2),
    market_data JSONB DEFAULT '{}'::jsonb,  -- { min, median, max, percentile_25, percentile_75 }
    salary_range JSONB DEFAULT '{}'::jsonb, -- { recommended_min, recommended_max, target }
    negotiation_scripts JSONB DEFAULT '[]'::jsonb,
    counter_offers JSONB DEFAULT '[]'::jsonb,
    talking_points JSONB DEFAULT '[]'::jsonb,
    benefits_analysis JSONB DEFAULT '{}'::jsonb,
    confidence_level VARCHAR(20) DEFAULT 'medium',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.salary_analyses ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own salary_analyses" ON public.salary_analyses
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on salary_analyses" ON public.salary_analyses
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_salary_analyses_user_id ON public.salary_analyses(user_id);

-- ────────────────────────────────────────────────────────────────
-- 7. Review Sessions & Comments (Collaborative Review)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.review_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    document_type VARCHAR(50),
    share_token VARCHAR(100) UNIQUE NOT NULL,
    share_url TEXT,
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    reviewer_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.review_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.review_sessions(id) ON DELETE CASCADE,
    reviewer_name VARCHAR(255) NOT NULL DEFAULT 'Anonymous',
    comment_text TEXT NOT NULL,
    selection_start INTEGER,
    selection_end INTEGER,
    section VARCHAR(100),
    sentiment VARCHAR(20) DEFAULT 'neutral',  -- positive | neutral | negative | suggestion
    is_resolved BOOLEAN DEFAULT FALSE,
    ai_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.review_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own review_sessions" ON public.review_sessions
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on review_sessions" ON public.review_sessions
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_review_sessions_share_token ON public.review_sessions(share_token);

ALTER TABLE public.review_comments ENABLE ROW LEVEL SECURITY;
-- Comments are accessible to anyone with the session share token (via service role)
CREATE POLICY "Service role full access on review_comments" ON public.review_comments
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_review_comments_session_id ON public.review_comments(session_id);

-- ────────────────────────────────────────────────────────────────
-- 8. Job Alerts (Job Board Sync)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.job_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    keywords JSONB DEFAULT '[]'::jsonb,
    location VARCHAR(255),
    job_type VARCHAR(50),
    salary_min NUMERIC(12,2),
    experience_level VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.job_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    alert_id UUID REFERENCES public.job_alerts(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    location VARCHAR(255),
    salary_range VARCHAR(100),
    description TEXT,
    source_url TEXT,
    source VARCHAR(50) DEFAULT 'manual',  -- manual | linkedin | indeed | glassdoor
    match_score NUMERIC(5,2) DEFAULT 0,
    match_reasons JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(50) DEFAULT 'new',  -- new | interested | applied | rejected | saved
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.job_alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own job_alerts" ON public.job_alerts
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on job_alerts" ON public.job_alerts
    FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE public.job_matches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own job_matches" ON public.job_matches
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on job_matches" ON public.job_matches
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_job_matches_user_id ON public.job_matches(user_id);

-- ────────────────────────────────────────────────────────────────
-- 9. Learning Challenges (Micro-Learning Engine)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.learning_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    skill VARCHAR(255) NOT NULL,
    difficulty VARCHAR(20) DEFAULT 'medium',
    challenge_type VARCHAR(50) NOT NULL DEFAULT 'quiz',  -- quiz | coding | scenario | flashcard
    question TEXT NOT NULL,
    options JSONB DEFAULT '[]'::jsonb,
    correct_answer TEXT,
    explanation TEXT,
    user_answer TEXT,
    is_correct BOOLEAN,
    points_earned INTEGER DEFAULT 0,
    streak_day INTEGER DEFAULT 0,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.learning_streaks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    total_points INTEGER DEFAULT 0,
    total_challenges INTEGER DEFAULT 0,
    correct_challenges INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_challenge_date DATE,
    skills_mastered JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.learning_challenges ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own learning_challenges" ON public.learning_challenges
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on learning_challenges" ON public.learning_challenges
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_learning_challenges_user_id ON public.learning_challenges(user_id);

ALTER TABLE public.learning_streaks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own learning_streaks" ON public.learning_streaks
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on learning_streaks" ON public.learning_streaks
    FOR ALL USING (auth.role() = 'service_role');

-- ────────────────────────────────────────────────────────────────
-- 10. API Keys (White-Label API)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    key_prefix VARCHAR(20) NOT NULL,  -- first 8 chars for display
    name VARCHAR(255) NOT NULL DEFAULT 'Default Key',
    scopes JSONB DEFAULT '["read", "write"]'::jsonb,
    rate_limit INTEGER DEFAULT 100,  -- requests per minute
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.api_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID NOT NULL REFERENCES public.api_keys(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER,
    response_time_ms INTEGER,
    request_body_size INTEGER,
    response_body_size INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own api_keys" ON public.api_keys
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on api_keys" ON public.api_keys
    FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE public.api_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own api_usage" ON public.api_usage
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on api_usage" ON public.api_usage
    FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_api_usage_key_id ON public.api_usage(api_key_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_created_at ON public.api_usage(created_at);

-- ────────────────────────────────────────────────────────────────
-- Apply updated_at triggers to new mutable tables
-- ────────────────────────────────────────────────────────────────
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'ats_scans', 'evidence_mappings', 'doc_variants',
        'interview_sessions', 'salary_analyses', 'review_sessions',
        'job_alerts', 'job_matches', 'learning_streaks', 'api_keys'
    ]) LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS update_%s_updated_at ON public.%I; '
            'CREATE TRIGGER update_%s_updated_at BEFORE UPDATE ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();',
            t, t, t, t
        );
    END LOOP;
END;
$$;

-- Enable Realtime on key new tables
ALTER PUBLICATION supabase_realtime ADD TABLE public.ats_scans;
ALTER PUBLICATION supabase_realtime ADD TABLE public.interview_sessions;
ALTER PUBLICATION supabase_realtime ADD TABLE public.learning_streaks;
