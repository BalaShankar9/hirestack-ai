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
    created_at TIMESTAMPTZ DEFAULT NOW()
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
        "scorecard": {"state": "idle"}
    }'::jsonb,

    -- Module outputs
    benchmark JSONB,
    gaps JSONB,
    learning_plan JSONB,
    cv_html TEXT,
    cover_letter_html TEXT,
    scorecard JSONB,

    -- Version histories
    cv_versions JSONB DEFAULT '[]'::jsonb,
    cl_versions JSONB DEFAULT '[]'::jsonb,

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
$$ LANGUAGE plpgsql SECURITY DEFINER;

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
        'roadmaps', 'projects', 'documents', 'applications',
        'evidence', 'tasks', 'learning_plans'
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
