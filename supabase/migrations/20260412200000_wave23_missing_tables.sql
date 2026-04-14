-- ═══════════════════════════════════════════════════════════════════════
-- HireStack AI — Wave 2/3 Missing Tables
-- Tables created in apply_all_pending.sql but never tracked as
-- Supabase migrations.  All statements are idempotent.
-- ═══════════════════════════════════════════════════════════════════════

-- ─── 1. outcome_signals ─────────────────────────────────────────────
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

CREATE INDEX IF NOT EXISTS idx_outcome_signals_user    ON public.outcome_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_app     ON public.outcome_signals(application_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_type    ON public.outcome_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_job     ON public.outcome_signals(generation_job_id);
CREATE INDEX IF NOT EXISTS idx_outcome_signals_created ON public.outcome_signals(created_at DESC);


-- ─── 2. pipeline_telemetry ──────────────────────────────────────────
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


-- ─── 3. career_alerts ───────────────────────────────────────────────
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

CREATE INDEX IF NOT EXISTS idx_career_alerts_user    ON public.career_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_career_alerts_active  ON public.career_alerts(user_id, created_at DESC) WHERE dismissed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_career_alerts_type    ON public.career_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_career_alerts_expires ON public.career_alerts(expires_at) WHERE expires_at IS NOT NULL;


-- ─── 4. document_evolution ──────────────────────────────────────────
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

CREATE INDEX IF NOT EXISTS idx_doc_evolution_user    ON public.document_evolution(user_id);
CREATE INDEX IF NOT EXISTS idx_doc_evolution_doc     ON public.document_evolution(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_evolution_app     ON public.document_evolution(application_id) WHERE application_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_doc_evolution_created ON public.document_evolution(created_at DESC);


-- ─── 5. quality_observations ────────────────────────────────────────
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
  CREATE POLICY "Service role full access on quality_observations" ON public.quality_observations FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_quality_obs_task_model ON public.quality_observations(task_type, model);
CREATE INDEX IF NOT EXISTS idx_quality_obs_created    ON public.quality_observations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_quality_obs_recent     ON public.quality_observations(task_type, model, created_at DESC);


-- ─── 6. Add job_id column to agent_traces if missing ────────────────
ALTER TABLE public.agent_traces ADD COLUMN IF NOT EXISTS job_id text;
CREATE INDEX IF NOT EXISTS idx_agent_traces_job     ON public.agent_traces(job_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_created ON public.agent_traces(created_at DESC);
