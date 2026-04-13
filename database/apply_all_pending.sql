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

-- HireStack AI — Application Generation Intelligence Columns
-- Aligns the applications table with generated document strategy and company intel outputs.

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS discovered_documents JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS generated_documents JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS benchmark_documents JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS document_strategy TEXT,
  ADD COLUMN IF NOT EXISTS company_intel JSONB DEFAULT '{}'::jsonb;
-- ═══════════════════════════════════════════════════════════════════════
-- HireStack AI — Consolidated Migration
-- Run this ONCE in Supabase Dashboard SQL Editor
-- Combines: Career Nexus, Elite Upgrades, Enterprise Foundation
-- Safe to run multiple times (uses IF NOT EXISTS / IF EXISTS)
-- ═══════════════════════════════════════════════════════════════════════

-- ═══════ 1. CAREER NEXUS COLUMNS (profiles table) ═══════════════════

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS social_links JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS universal_documents JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS universal_docs_version INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS profile_version INTEGER DEFAULT 1,
  ADD COLUMN IF NOT EXISTS completeness_score INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS resume_worth_score INTEGER DEFAULT 0;

-- ═══════ 2. ELITE UPGRADE TABLES ════════════════════════════════════

-- Career Snapshots
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
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'career_snapshots' AND policyname = 'Users can manage own career_snapshots') THEN
    CREATE POLICY "Users can manage own career_snapshots" ON public.career_snapshots FOR ALL USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'career_snapshots' AND policyname = 'Service role full access on career_snapshots') THEN
    CREATE POLICY "Service role full access on career_snapshots" ON public.career_snapshots FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Salary Analyses
CREATE TABLE IF NOT EXISTS public.salary_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    job_title VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    location VARCHAR(255),
    experience_years NUMERIC(4,1),
    current_salary NUMERIC(12,2),
    market_data JSONB DEFAULT '{}'::jsonb,
    salary_range JSONB DEFAULT '{}'::jsonb,
    negotiation_scripts JSONB DEFAULT '[]'::jsonb,
    counter_offers JSONB DEFAULT '[]'::jsonb,
    talking_points JSONB DEFAULT '[]'::jsonb,
    benefits_analysis JSONB DEFAULT '{}'::jsonb,
    confidence_level VARCHAR(20) DEFAULT 'medium',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.salary_analyses ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'salary_analyses' AND policyname = 'Users can manage own salary_analyses') THEN
    CREATE POLICY "Users can manage own salary_analyses" ON public.salary_analyses FOR ALL USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'salary_analyses' AND policyname = 'Service role full access on salary_analyses') THEN
    CREATE POLICY "Service role full access on salary_analyses" ON public.salary_analyses FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Job Alerts
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
ALTER TABLE public.job_alerts ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'job_alerts' AND policyname = 'Users can manage own job_alerts') THEN
    CREATE POLICY "Users can manage own job_alerts" ON public.job_alerts FOR ALL USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'job_alerts' AND policyname = 'Service role full access on job_alerts') THEN
    CREATE POLICY "Service role full access on job_alerts" ON public.job_alerts FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Job Matches
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
    source VARCHAR(50) DEFAULT 'manual',
    match_score NUMERIC(5,2) DEFAULT 0,
    match_reasons JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(50) DEFAULT 'new',
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.job_matches ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'job_matches' AND policyname = 'Users can manage own job_matches') THEN
    CREATE POLICY "Users can manage own job_matches" ON public.job_matches FOR ALL USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'job_matches' AND policyname = 'Service role full access on job_matches') THEN
    CREATE POLICY "Service role full access on job_matches" ON public.job_matches FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Learning Streaks
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
ALTER TABLE public.learning_streaks ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'learning_streaks' AND policyname = 'Users can manage own learning_streaks') THEN
    CREATE POLICY "Users can manage own learning_streaks" ON public.learning_streaks FOR ALL USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'learning_streaks' AND policyname = 'Service role full access on learning_streaks') THEN
    CREATE POLICY "Service role full access on learning_streaks" ON public.learning_streaks FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- ATS Scans extended columns
ALTER TABLE public.ats_scans
  ADD COLUMN IF NOT EXISTS ats_score INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS keyword_match_rate NUMERIC(5,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS readability_score NUMERIC(5,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS format_score NUMERIC(5,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS section_scores JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS matched_keywords JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS missing_keywords JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS formatting_issues JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS recommendations JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS pass_prediction VARCHAR(20) DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS recruiter_view_html TEXT;

-- ═══════ 3. ENTERPRISE TABLES ═══════════════════════════════════════

-- Organizations
CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    logo_url TEXT,
    tier VARCHAR(20) DEFAULT 'free',
    billing_email VARCHAR(255),
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    settings JSONB DEFAULT '{}',
    max_members INTEGER DEFAULT 5,
    max_candidates INTEGER DEFAULT 50,
    features JSONB DEFAULT '{}',
    created_by UUID REFERENCES public.users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'organizations' AND policyname = 'Service role full access on organizations') THEN
    CREATE POLICY "Service role full access on organizations" ON public.organizations FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Org Members
CREATE TABLE IF NOT EXISTS public.org_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    invited_by UUID REFERENCES public.users(id),
    invited_email VARCHAR(255),
    status VARCHAR(20) DEFAULT 'active',
    permissions JSONB DEFAULT '{}',
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, user_id)
);
ALTER TABLE public.org_members ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'org_members' AND policyname = 'Service role full access on org_members') THEN
    CREATE POLICY "Service role full access on org_members" ON public.org_members FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_org_members_user ON public.org_members(user_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org ON public.org_members(org_id);

-- Candidates
CREATE TABLE IF NOT EXISTS public.candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.users(id),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    location VARCHAR(255),
    profile_id UUID REFERENCES public.profiles(id),
    status VARCHAR(20) DEFAULT 'active',
    pipeline_stage VARCHAR(30) DEFAULT 'sourced',
    tags JSONB DEFAULT '[]',
    notes TEXT,
    client_company VARCHAR(255),
    assigned_recruiter UUID REFERENCES public.users(id),
    resume_url TEXT,
    resume_text TEXT,
    parsed_data JSONB DEFAULT '{}',
    skills JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_by UUID REFERENCES public.users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.candidates ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'candidates' AND policyname = 'Service role full access on candidates') THEN
    CREATE POLICY "Service role full access on candidates" ON public.candidates FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_candidates_org ON public.candidates(org_id);

-- Subscriptions
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    plan VARCHAR(20) NOT NULL DEFAULT 'free',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    stripe_subscription_id VARCHAR(255),
    stripe_price_id VARCHAR(255),
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at TIMESTAMPTZ,
    usage_limits JSONB DEFAULT '{"applications": 5, "ats_scans": 10, "ai_calls": 50, "members": 2, "candidates": 10}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'subscriptions' AND policyname = 'Service role full access on subscriptions') THEN
    CREATE POLICY "Service role full access on subscriptions" ON public.subscriptions FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Usage Records
CREATE TABLE IF NOT EXISTS public.usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.users(id),
    feature VARCHAR(50) NOT NULL,
    quantity INTEGER DEFAULT 1,
    metadata JSONB DEFAULT '{}',
    period_start DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.usage_records ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'usage_records' AND policyname = 'Service role full access on usage_records') THEN
    CREATE POLICY "Service role full access on usage_records" ON public.usage_records FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Audit Logs
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    user_id UUID REFERENCES public.users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    changes JSONB DEFAULT '{}',
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'audit_logs' AND policyname = 'Service role full access on audit_logs') THEN
    CREATE POLICY "Service role full access on audit_logs" ON public.audit_logs FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Invitations
CREATE TABLE IF NOT EXISTS public.org_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'member',
    invited_by UUID REFERENCES public.users(id),
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.org_invitations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'org_invitations' AND policyname = 'Service role full access on org_invitations') THEN
    CREATE POLICY "Service role full access on org_invitations" ON public.org_invitations FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- Webhooks
CREATE TABLE IF NOT EXISTS public.webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    secret VARCHAR(255) NOT NULL,
    events JSONB DEFAULT '["*"]',
    is_active BOOLEAN DEFAULT TRUE,
    last_triggered_at TIMESTAMPTZ,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.webhooks ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'webhooks' AND policyname = 'Service role full access on webhooks') THEN
    CREATE POLICY "Service role full access on webhooks" ON public.webhooks FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- ═══════ 4. ADD org_id TO EXISTING TABLES ═══════════════════════════

ALTER TABLE public.applications ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);
ALTER TABLE public.evidence ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);
ALTER TABLE public.job_descriptions ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);

CREATE INDEX IF NOT EXISTS idx_applications_org ON public.applications(org_id);
CREATE INDEX IF NOT EXISTS idx_profiles_org ON public.profiles(org_id);
CREATE INDEX IF NOT EXISTS idx_evidence_org ON public.evidence(org_id);

-- ═══════ DONE ════════════════════════════════════════════════════════
-- All tables, columns, RLS policies, and indexes have been applied.
-- HireStack AI is now enterprise-ready at the database level.


-- ═══════════════════════════════════════════════════════════════════════
-- Outcome Signals + Pipeline Telemetry tables
-- Closes the feedback loop: export → apply → interview → offer
-- and tracks per-run AI cost, token, and quality data.
-- ═══════════════════════════════════════════════════════════════════════

-- 1. outcome_signals — progressive funnel signals per application
CREATE TABLE IF NOT EXISTS public.outcome_signals (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id      uuid NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    generation_job_id   uuid REFERENCES public.generation_jobs(id) ON DELETE SET NULL,
    signal_type         text NOT NULL CHECK (signal_type IN (
                            'exported', 'applied', 'screened', 'interview',
                            'interview_done', 'offer', 'accepted', 'rejected'
                        )),
    signal_data         jsonb NOT NULL DEFAULT '{}'::jsonb,
    pipeline_config     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.outcome_signals ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own outcome_signals" ON public.outcome_signals FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on outcome_signals" ON public.outcome_signals FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_outcome_signals_user       ON public.outcome_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_app        ON public.outcome_signals(application_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_type       ON public.outcome_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_job        ON public.outcome_signals(generation_job_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_created    ON public.outcome_signals(created_at DESC);


-- 2. pipeline_telemetry — per-run cost, token, and quality metrics
CREATE TABLE IF NOT EXISTS public.pipeline_telemetry (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_id              text NOT NULL,
    pipeline_name       text NOT NULL,
    model_used          text NOT NULL DEFAULT '',
    research_depth      text NOT NULL DEFAULT '',
    iterations_used     integer NOT NULL DEFAULT 0,
    total_latency_ms    integer NOT NULL DEFAULT 0,
    stage_latencies     jsonb NOT NULL DEFAULT '{}'::jsonb,
    token_usage         jsonb NOT NULL DEFAULT '{}'::jsonb,
    quality_scores      jsonb NOT NULL DEFAULT '{}'::jsonb,
    evidence_stats      jsonb NOT NULL DEFAULT '{}'::jsonb,
    cost_usd_cents      integer NOT NULL DEFAULT 0,
    cascade_failovers   integer NOT NULL DEFAULT 0,
    pipeline_config     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.pipeline_telemetry ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own pipeline_telemetry" ON public.pipeline_telemetry FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on pipeline_telemetry" ON public.pipeline_telemetry FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_user      ON public.pipeline_telemetry(user_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_job       ON public.pipeline_telemetry(job_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_pipeline  ON public.pipeline_telemetry(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_created   ON public.pipeline_telemetry(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_user_pipe ON public.pipeline_telemetry(user_id, pipeline_name);


-- 3. agent_traces — searchable agent execution traces
CREATE TABLE IF NOT EXISTS public.agent_traces (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_id              text NOT NULL,
    pipeline_name       text NOT NULL,
    stages              jsonb NOT NULL DEFAULT '[]'::jsonb,
    total_latency_ms    integer NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.agent_traces ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own agent_traces" ON public.agent_traces FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on agent_traces" ON public.agent_traces FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_agent_traces_user    ON public.agent_traces(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_job     ON public.agent_traces(job_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_created ON public.agent_traces(created_at DESC);


-- 4. pipeline_plans — adaptive planner plan artifacts
CREATE TABLE IF NOT EXISTS public.pipeline_plans (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_id              text NOT NULL,
    plan                jsonb NOT NULL DEFAULT '{}'::jsonb,
    risk_mode           text NOT NULL DEFAULT 'standard',
    jd_quality_score    real NOT NULL DEFAULT 0,
    profile_quality_score real NOT NULL DEFAULT 0,
    evidence_score      real NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.pipeline_plans ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own pipeline_plans" ON public.pipeline_plans FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on pipeline_plans" ON public.pipeline_plans FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_pipeline_plans_user    ON public.pipeline_plans(user_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_plans_job     ON public.pipeline_plans(job_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_plans_created ON public.pipeline_plans(created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════
-- Wave 3 — Autonomous Intelligence Tables
-- ═══════════════════════════════════════════════════════════════════════

-- 5. user_evidence_nodes — canonical cross-job evidence nodes
CREATE TABLE IF NOT EXISTS public.user_evidence_nodes (
    id                  text PRIMARY KEY,
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_text      text NOT NULL,
    tier                text NOT NULL CHECK (tier IN ('verbatim', 'derived', 'inferred', 'user_stated')),
    source              text NOT NULL,
    source_field        text NOT NULL DEFAULT '',
    confidence          real NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    first_seen_job_id   text,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.user_evidence_nodes ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own evidence_nodes" ON public.user_evidence_nodes FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on evidence_nodes" ON public.user_evidence_nodes FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_nodes_user     ON public.user_evidence_nodes(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_nodes_tier     ON public.user_evidence_nodes(tier);
CREATE INDEX IF NOT EXISTS idx_evidence_nodes_conf     ON public.user_evidence_nodes(confidence DESC);


-- 6. user_evidence_aliases — alias text for canonical nodes
CREATE TABLE IF NOT EXISTS public.user_evidence_aliases (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_node_id   text NOT NULL REFERENCES public.user_evidence_nodes(id) ON DELETE CASCADE,
    alias_text          text NOT NULL,
    similarity_score    real NOT NULL DEFAULT 0.85,
    source_job_id       text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.user_evidence_aliases ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own evidence_aliases" ON public.user_evidence_aliases FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on evidence_aliases" ON public.user_evidence_aliases FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_aliases_user ON public.user_evidence_aliases(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_aliases_node ON public.user_evidence_aliases(canonical_node_id);


-- 7. evidence_contradictions — detected conflicts between evidence nodes
CREATE TABLE IF NOT EXISTS public.evidence_contradictions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    node_a_id           text NOT NULL REFERENCES public.user_evidence_nodes(id) ON DELETE CASCADE,
    node_b_id           text NOT NULL REFERENCES public.user_evidence_nodes(id) ON DELETE CASCADE,
    contradiction_type  text NOT NULL CHECK (contradiction_type IN (
        'company_name', 'title_conflict', 'date_overlap',
        'certification_conflict', 'metric_conflict'
    )),
    severity            text NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical', 'resolved')),
    description         text NOT NULL DEFAULT '',
    resolved_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.evidence_contradictions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own evidence_contradictions" ON public.evidence_contradictions FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on evidence_contradictions" ON public.evidence_contradictions FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_contradictions_user     ON public.evidence_contradictions(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_contradictions_unresolved ON public.evidence_contradictions(user_id) WHERE resolved_at IS NULL;


-- 8. career_alerts — proactive autonomous career monitoring alerts
CREATE TABLE IF NOT EXISTS public.career_alerts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    alert_type          text NOT NULL CHECK (alert_type IN (
        'profile_stale', 'evidence_decay', 'skill_trending',
        'market_shift', 'document_outdated', 'quality_regression',
        'opportunity_match', 'interview_prep_reminder'
    )),
    severity            text NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
    title               text NOT NULL,
    description         text NOT NULL DEFAULT '',
    action_url          text,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    read_at             timestamptz,
    dismissed_at        timestamptz,
    expires_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.career_alerts ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own career_alerts" ON public.career_alerts FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on career_alerts" ON public.career_alerts FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_career_alerts_user        ON public.career_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_career_alerts_active      ON public.career_alerts(user_id, created_at DESC) WHERE dismissed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_career_alerts_type        ON public.career_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_career_alerts_expires     ON public.career_alerts(expires_at) WHERE expires_at IS NOT NULL;


-- 9. document_evolution — semantic diff tracking between document versions
CREATE TABLE IF NOT EXISTS public.document_evolution (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    document_id         uuid NOT NULL,
    application_id      uuid,
    version_from        integer NOT NULL,
    version_to          integer NOT NULL,
    diff_type           text NOT NULL CHECK (diff_type IN ('content', 'structure', 'tone', 'keyword', 'evidence')),
    change_summary      text NOT NULL DEFAULT '',
    improvement_score   real CHECK (improvement_score >= -100 AND improvement_score <= 100),
    sections_changed    jsonb NOT NULL DEFAULT '[]'::jsonb,
    keywords_added      jsonb NOT NULL DEFAULT '[]'::jsonb,
    keywords_removed    jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_delta      jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.document_evolution ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own document_evolution" ON public.document_evolution FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on document_evolution" ON public.document_evolution FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_doc_evolution_user     ON public.document_evolution(user_id);
CREATE INDEX IF NOT EXISTS idx_doc_evolution_doc      ON public.document_evolution(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_evolution_app      ON public.document_evolution(application_id) WHERE application_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_doc_evolution_created  ON public.document_evolution(created_at DESC);


-- 10. quality_observations — persist model quality data across restarts
CREATE TABLE IF NOT EXISTS public.quality_observations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type           text NOT NULL,
    model               text NOT NULL,
    quality_score       real NOT NULL CHECK (quality_score >= 0 AND quality_score <= 100),
    pipeline_name       text,
    user_id             uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    job_id              text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- No RLS on quality_observations — service-level table only
ALTER TABLE public.quality_observations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Service role full access on quality_observations" ON public.quality_observations FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_quality_obs_task_model ON public.quality_observations(task_type, model);
CREATE INDEX IF NOT EXISTS idx_quality_obs_created    ON public.quality_observations(created_at DESC);
-- Keep only recent observations (cleanup via cron or app logic)
CREATE INDEX IF NOT EXISTS idx_quality_obs_recent     ON public.quality_observations(task_type, model, created_at DESC);
