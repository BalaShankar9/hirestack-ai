-- ═══════════════════════════════════════════════════════════════════════════════
-- HireStack AI — Production Migration: Waves 2 & 3
-- Run this in the Supabase Dashboard SQL Editor (one-time)
-- All statements are idempotent (IF NOT EXISTS / IF EXISTS)
-- ═══════════════════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════════════════
-- PART A: Generation Job Events + Intelligence Columns (prerequisites)
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.generation_jobs
  ADD COLUMN IF NOT EXISTS current_agent TEXT,
  ADD COLUMN IF NOT EXISTS completed_steps INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_steps INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS active_sources_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS public.generation_job_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES public.generation_jobs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  application_id UUID NOT NULL,
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
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.generation_job_events ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users can read own generation job events" ON public.generation_job_events
    FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on generation_job_events" ON public.generation_job_events
    FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_generation_job_events_job_sequence ON public.generation_job_events(job_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_generation_job_events_application_id ON public.generation_job_events(application_id);
CREATE INDEX IF NOT EXISTS idx_generation_job_events_user_id ON public.generation_job_events(user_id);

ALTER TABLE public.generation_job_events REPLICA IDENTITY FULL;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'generation_job_events'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.generation_job_events;
  END IF;
END $$;

-- Application intelligence columns
ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS discovered_documents JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS generated_documents JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS benchmark_documents JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS document_strategy TEXT,
  ADD COLUMN IF NOT EXISTS company_intel JSONB DEFAULT '{}'::jsonb;


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART B: v3 Durable Evidence Columns on generation_jobs
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.generation_jobs
  ADD COLUMN IF NOT EXISTS workflow_id TEXT,
  ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS stage_timeouts JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS evidence_summary JSONB;

-- Evidence ledger storage per job
CREATE TABLE IF NOT EXISTS public.evidence_ledger_items (
  pk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id TEXT NOT NULL,
  job_id UUID NOT NULL REFERENCES public.generation_jobs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  tier TEXT NOT NULL CHECK (tier IN ('verbatim', 'derived', 'inferred', 'user_stated')),
  source TEXT NOT NULL CHECK (source IN ('profile', 'jd', 'company', 'tool', 'memory')),
  source_field TEXT NOT NULL DEFAULT '',
  evidence_text TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(job_id, id)
);

ALTER TABLE public.evidence_ledger_items ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users can read own evidence items" ON public.evidence_ledger_items
    FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on evidence_ledger_items" ON public.evidence_ledger_items
    FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_ledger_job_id ON public.evidence_ledger_items(job_id);
CREATE INDEX IF NOT EXISTS idx_evidence_ledger_user_id ON public.evidence_ledger_items(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_ledger_tier ON public.evidence_ledger_items(tier);

-- Claim citations
CREATE TABLE IF NOT EXISTS public.claim_citations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES public.generation_jobs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  claim_text TEXT NOT NULL,
  evidence_ids TEXT[] NOT NULL DEFAULT '{}',
  classification TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 0,
  tier TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.claim_citations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users can read own citations" ON public.claim_citations
    FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on claim_citations" ON public.claim_citations
    FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_claim_citations_job_id ON public.claim_citations(job_id);


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART C: v3 Phase 2 — Relax event constraints + resume columns
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.generation_job_events
  DROP CONSTRAINT IF EXISTS generation_job_events_job_id_sequence_no_key;

CREATE INDEX IF NOT EXISTS idx_generation_job_events_job_seq
  ON public.generation_job_events(job_id, sequence_no);

ALTER TABLE public.generation_jobs
  ADD COLUMN IF NOT EXISTS resume_from_stage TEXT,
  ADD COLUMN IF NOT EXISTS resume_from_stages JSONB,
  ADD COLUMN IF NOT EXISTS recovery_attempts INTEGER NOT NULL DEFAULT 0;


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART D: Outcome Tracking
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS callback_received_at   timestamptz,
    ADD COLUMN IF NOT EXISTS offer_received_at       timestamptz,
    ADD COLUMN IF NOT EXISTS user_rating             smallint CHECK (user_rating IS NULL OR (user_rating >= 1 AND user_rating <= 5)),
    ADD COLUMN IF NOT EXISTS user_feedback_text      text;

CREATE INDEX IF NOT EXISTS idx_applications_callback ON public.applications(user_id) WHERE callback_received_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_applications_offer ON public.applications(user_id) WHERE offer_received_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_applications_rated ON public.applications(user_id) WHERE user_rating IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.ab_test_results (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id      uuid NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    variant_id          text NOT NULL,
    document_type       text NOT NULL,
    ats_score           real,
    readability_score   real,
    keyword_density     real,
    outcome_type        text CHECK (outcome_type IN ('callback', 'offer', 'rejection', 'no_response', NULL)),
    outcome_recorded_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.ab_test_results ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "ab_test_results_owner" ON public.ab_test_results FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_ab_test_results_user ON public.ab_test_results(user_id);
CREATE INDEX IF NOT EXISTS idx_ab_test_results_application ON public.ab_test_results(application_id);
CREATE INDEX IF NOT EXISTS idx_ab_test_results_variant ON public.ab_test_results(variant_id, outcome_type);

-- Outcome signals (funnel tracking)
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
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on outcome_signals" ON public.outcome_signals FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_outcome_signals_user ON public.outcome_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_app ON public.outcome_signals(application_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_type ON public.outcome_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_job ON public.outcome_signals(generation_job_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_created ON public.outcome_signals(created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART E: Pipeline Telemetry + Agent Traces
-- ═══════════════════════════════════════════════════════════════════════════════

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
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on pipeline_telemetry" ON public.pipeline_telemetry FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_user ON public.pipeline_telemetry(user_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_job ON public.pipeline_telemetry(job_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_pipeline ON public.pipeline_telemetry(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_created ON public.pipeline_telemetry(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_telemetry_user_pipe ON public.pipeline_telemetry(user_id, pipeline_name);

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
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on agent_traces" ON public.agent_traces FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_agent_traces_user ON public.agent_traces(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_job ON public.agent_traces(job_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_created ON public.agent_traces(created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART F: Evidence Graph (canonical user-level evidence)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.user_evidence_nodes (
    id              text PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_text  text NOT NULL,
    tier            text NOT NULL CHECK (tier IN ('verbatim', 'derived', 'inferred', 'user_stated')),
    source          text NOT NULL,
    source_field    text NOT NULL DEFAULT '',
    confidence      real NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    first_seen_job_id text,
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.user_evidence_nodes ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Users own evidence_nodes" ON public.user_evidence_nodes FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on evidence_nodes" ON public.user_evidence_nodes FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_nodes_user ON public.user_evidence_nodes(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_nodes_tier ON public.user_evidence_nodes(tier);
CREATE INDEX IF NOT EXISTS idx_evidence_nodes_conf ON public.user_evidence_nodes(confidence DESC);

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
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on evidence_aliases" ON public.user_evidence_aliases FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_aliases_user ON public.user_evidence_aliases(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_aliases_node ON public.user_evidence_aliases(canonical_node_id);

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
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on evidence_contradictions" ON public.evidence_contradictions FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_contradictions_user ON public.evidence_contradictions(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_contradictions_unresolved ON public.evidence_contradictions(user_id) WHERE resolved_at IS NULL;

-- Pipeline plans (adaptive planner audit trail)
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
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on pipeline_plans" ON public.pipeline_plans FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_pipeline_plans_user ON public.pipeline_plans(user_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_plans_job ON public.pipeline_plans(job_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_plans_created ON public.pipeline_plans(created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART G: Wave 3 — Autonomous Intelligence Tables
-- ═══════════════════════════════════════════════════════════════════════════════

-- Career alerts
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
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on career_alerts" ON public.career_alerts FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_career_alerts_user ON public.career_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_career_alerts_active ON public.career_alerts(user_id, created_at DESC) WHERE dismissed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_career_alerts_type ON public.career_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_career_alerts_expires ON public.career_alerts(expires_at) WHERE expires_at IS NOT NULL;

-- Document evolution (semantic diff tracking)
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
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "Service role full access on document_evolution" ON public.document_evolution FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_doc_evolution_user ON public.document_evolution(user_id);
CREATE INDEX IF NOT EXISTS idx_doc_evolution_doc ON public.document_evolution(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_evolution_app ON public.document_evolution(application_id) WHERE application_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_doc_evolution_created ON public.document_evolution(created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART H: Document Catalog + Document Library
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.document_type_catalog (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key             text UNIQUE NOT NULL,
    label           text NOT NULL,
    description     text NOT NULL DEFAULT '',
    category        text NOT NULL DEFAULT 'professional'
                    CHECK (category IN ('core', 'professional', 'academic', 'creative', 'executive', 'compliance', 'technical')),
    generatable     boolean NOT NULL DEFAULT false,
    seen_count      integer NOT NULL DEFAULT 1,
    source_context  text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_type_catalog_key ON public.document_type_catalog(key);
CREATE INDEX IF NOT EXISTS idx_document_type_catalog_category ON public.document_type_catalog(category);

ALTER TABLE public.document_type_catalog ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "document_type_catalog_read" ON public.document_type_catalog FOR SELECT USING (true);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "document_type_catalog_service_write" ON public.document_type_catalog FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS public.document_observations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    catalog_entry_id    uuid NOT NULL REFERENCES public.document_type_catalog(id) ON DELETE CASCADE,
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id      uuid REFERENCES public.applications(id) ON DELETE SET NULL,
    job_title           text NOT NULL DEFAULT '',
    industry            text NOT NULL DEFAULT '',
    job_level           text NOT NULL DEFAULT '',
    reason              text NOT NULL DEFAULT '',
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_observations_catalog ON public.document_observations(catalog_entry_id);
CREATE INDEX IF NOT EXISTS idx_document_observations_user ON public.document_observations(user_id);

ALTER TABLE public.document_observations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "document_observations_read" ON public.document_observations FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "document_observations_service_write" ON public.document_observations FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.applications ADD COLUMN IF NOT EXISTS doc_pack_plan JSONB;

-- Seed catalog
INSERT INTO public.document_type_catalog (key, label, description, category, generatable, seen_count, source_context) VALUES
    ('cv', 'Tailored CV', 'Your resume tailored and optimized for the specific job description', 'core', true, 100, 'Universal requirement'),
    ('cover_letter', 'Cover Letter', 'Compelling narrative connecting your experience to the role', 'core', true, 100, 'Universal requirement'),
    ('personal_statement', 'Personal Statement', 'Authentic career narrative', 'core', true, 80, 'Standard for most applications'),
    ('portfolio', 'Portfolio & Evidence', 'Showcase of projects with impact', 'core', true, 70, 'Standard for technical/creative roles'),
    ('executive_summary', 'Executive Summary', 'One-page overview of qualifications', 'executive', true, 0, 'Senior and executive-level'),
    ('elevator_pitch', 'Elevator Pitch', 'Brief compelling pitch', 'professional', true, 0, 'Networking events'),
    ('references_list', 'References List', 'Formatted professional references', 'professional', true, 0, 'After initial screening'),
    ('motivation_letter', 'Motivation Letter', 'Career motivation exploration', 'professional', true, 0, 'European/international applications'),
    ('recommendation_letter_template', 'Recommendation Letter Template', 'Draft template for recommenders', 'professional', true, 0, 'Requesting recommendations'),
    ('ninety_day_plan', '90-Day Plan', 'Strategic onboarding plan', 'executive', true, 0, 'Senior roles'),
    ('values_statement', 'Values Statement', 'Professional values articulation', 'professional', true, 0, 'Mission-driven organizations'),
    ('leadership_philosophy', 'Leadership Philosophy', 'Leadership style framework', 'executive', true, 0, 'Management/director roles'),
    ('research_statement', 'Research Statement', 'Research interests overview', 'academic', true, 0, 'Academic/research positions'),
    ('teaching_philosophy', 'Teaching Philosophy', 'Teaching approach statement', 'academic', true, 0, 'Academic teaching positions'),
    ('publications_list', 'Publications List', 'Formatted publications', 'academic', true, 0, 'Academic/research positions'),
    ('thesis_abstract', 'Thesis Abstract', 'Thesis research summary', 'academic', true, 0, 'Recent graduates'),
    ('grant_proposal', 'Grant Proposal', 'Research funding proposal', 'academic', true, 0, 'Research-funded positions'),
    ('selection_criteria', 'Selection Criteria Response', 'STAR-format response', 'compliance', true, 0, 'Government applications'),
    ('diversity_statement', 'Diversity Statement', 'DEI commitment statement', 'compliance', true, 0, 'Academic/government roles'),
    ('safety_statement', 'Safety Statement', 'Workplace safety approach', 'compliance', true, 0, 'Safety-related roles'),
    ('equity_statement', 'Equity Statement', 'Equity advancement framework', 'compliance', true, 0, 'Academic/public sector'),
    ('conflict_of_interest_declaration', 'Conflict of Interest Declaration', 'Conflict disclosure', 'compliance', true, 0, 'Senior public sector/board'),
    ('community_engagement_statement', 'Community Engagement Statement', 'Community involvement', 'compliance', true, 0, 'Public sector/nonprofit'),
    ('technical_assessment', 'Technical Assessment', 'Technical knowledge demo', 'technical', true, 0, 'Technical/engineering roles'),
    ('code_samples', 'Code Samples', 'Code quality examples', 'technical', true, 0, 'Software engineering roles'),
    ('writing_sample', 'Writing Sample', 'Professional writing example', 'technical', true, 0, 'Content/communications roles'),
    ('case_study', 'Case Study', 'Detailed project analysis', 'technical', true, 0, 'Consulting/strategy roles'),
    ('design_portfolio', 'Design Portfolio', 'Visual design showcase', 'creative', true, 0, 'Design/creative roles'),
    ('clinical_portfolio', 'Clinical Portfolio', 'Clinical experience docs', 'creative', true, 0, 'Healthcare/clinical positions'),
    ('speaker_bio', 'Speaker Bio', 'Professional speaking bio', 'creative', true, 0, 'Thought leaders'),
    ('media_kit', 'Media Kit', 'Press-ready materials', 'creative', true, 0, 'Public-facing roles'),
    ('consulting_deck', 'Consulting Deck', 'Expertise presentation', 'executive', true, 0, 'Consulting/advisory roles'),
    ('board_presentation', 'Board Presentation', 'Board qualifications', 'executive', true, 0, 'Board member positions'),
    ('professional_development_plan', 'Professional Development Plan', 'Skill development plan', 'professional', true, 0, 'Continuous improvement')
ON CONFLICT (key) DO NOTHING;

-- Increment functions
CREATE OR REPLACE FUNCTION increment_catalog_seen_count(p_key text)
RETURNS void LANGUAGE sql SECURITY DEFINER AS $$
    UPDATE public.document_type_catalog
    SET seen_count = seen_count + 1, updated_at = now()
    WHERE key = p_key;
$$;

CREATE OR REPLACE FUNCTION increment_catalog_seen_count_batch(p_keys text[])
RETURNS void LANGUAGE sql SECURITY DEFINER AS $$
    UPDATE public.document_type_catalog
    SET seen_count = seen_count + 1, updated_at = now()
    WHERE key = ANY(p_keys);
$$;

-- Document Library
CREATE TABLE IF NOT EXISTS public.document_library (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id  uuid REFERENCES public.applications(id) ON DELETE SET NULL,
    doc_type        text NOT NULL,
    doc_category    text NOT NULL DEFAULT 'tailored'
                    CHECK (doc_category IN ('benchmark', 'fixed', 'tailored')),
    label           text NOT NULL DEFAULT '',
    html_content    text NOT NULL DEFAULT '',
    metadata        jsonb NOT NULL DEFAULT '{}',
    version         integer NOT NULL DEFAULT 1,
    status          text NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned', 'generating', 'ready', 'error')),
    error_message   text,
    source          text NOT NULL DEFAULT 'planner'
                    CHECK (source IN ('planner', 'user_request', 'auto_evolve', 'migration')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_library_user ON public.document_library(user_id);
CREATE INDEX IF NOT EXISTS idx_document_library_user_category ON public.document_library(user_id, doc_category);
CREATE INDEX IF NOT EXISTS idx_document_library_application ON public.document_library(application_id) WHERE application_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_document_library_user_type_category ON public.document_library(user_id, doc_type, doc_category);

ALTER TABLE public.document_library ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "document_library_user_select" ON public.document_library FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "document_library_service_all" ON public.document_library FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE OR REPLACE FUNCTION update_document_library_timestamp()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
  CREATE TRIGGER trg_document_library_updated_at
    BEFORE UPDATE ON public.document_library FOR EACH ROW
    EXECUTE FUNCTION update_document_library_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS generation_plan jsonb DEFAULT NULL;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND tablename = 'document_library'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.document_library;
  END IF;
END $$;


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART I: Quality Observations (model router persistence)
-- ═══════════════════════════════════════════════════════════════════════════════

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

ALTER TABLE public.quality_observations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  CREATE POLICY "Service role full access on quality_observations" ON public.quality_observations
    FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_quality_obs_task_model ON public.quality_observations(task_type, model);
CREATE INDEX IF NOT EXISTS idx_quality_obs_created ON public.quality_observations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_quality_obs_recent ON public.quality_observations(task_type, model, created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════════════
-- PART J: Repair Missing Tables (elite upgrades that may have been partially applied)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Salary analyses
CREATE TABLE IF NOT EXISTS public.salary_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_title TEXT NOT NULL,
    location TEXT,
    experience_years INTEGER,
    industry TEXT,
    company_size TEXT,
    salary_range JSONB DEFAULT '{}'::jsonb,
    market_data JSONB DEFAULT '{}'::jsonb,
    recommendations JSONB DEFAULT '[]'::jsonb,
    negotiation_tips JSONB DEFAULT '[]'::jsonb,
    confidence_score NUMERIC(5,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.salary_analyses ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "Users manage own salary_analyses" ON public.salary_analyses FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_salary_analyses_user_id ON public.salary_analyses(user_id);

-- Review sessions
CREATE TABLE IF NOT EXISTS public.review_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
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
ALTER TABLE public.review_sessions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "Users manage own review_sessions" ON public.review_sessions FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on review_sessions" ON public.review_sessions FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_review_sessions_share_token ON public.review_sessions(share_token);

-- Learning streaks
CREATE TABLE IF NOT EXISTS public.learning_streaks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
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
DO $$ BEGIN CREATE POLICY "Users manage own learning_streaks" ON public.learning_streaks FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on learning_streaks" ON public.learning_streaks FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- API keys
CREATE TABLE IF NOT EXISTS public.api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    key_prefix VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL DEFAULT 'Default Key',
    scopes JSONB DEFAULT '["read", "write"]'::jsonb,
    rate_limit INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "Users manage own api_keys" ON public.api_keys FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on api_keys" ON public.api_keys FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- API usage
CREATE TABLE IF NOT EXISTS public.api_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID NOT NULL REFERENCES public.api_keys(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER,
    response_time_ms INTEGER,
    request_body_size INTEGER,
    response_body_size INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.api_usage ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "Users view own api_usage" ON public.api_usage FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on api_usage" ON public.api_usage FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_api_usage_key_id ON public.api_usage(api_key_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_created_at ON public.api_usage(created_at);


-- ═══════════════════════════════════════════════════════════════════════════════
-- DONE — All Wave 2 & 3 tables created, all idempotent
-- ═══════════════════════════════════════════════════════════════════════════════
