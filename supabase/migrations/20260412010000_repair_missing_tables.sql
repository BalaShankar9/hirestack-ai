-- Repair migration: create 7 tables that were missed from the elite_upgrades migration
-- These tables exist in 20260302100000_elite_upgrades.sql but were not created on the
-- remote DB (likely due to a partial migration run). All statements are idempotent.

-- 1. evidence_mappings
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
DO $$ BEGIN CREATE POLICY "Users can manage own evidence_mappings" ON public.evidence_mappings FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on evidence_mappings" ON public.evidence_mappings FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_evidence_mappings_user_id ON public.evidence_mappings(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_mappings_evidence_id ON public.evidence_mappings(evidence_id);

-- 2. interview_answers
CREATE TABLE IF NOT EXISTS public.interview_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    question_index INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    question_type VARCHAR(50),
    answer_text TEXT NOT NULL DEFAULT '',
    score NUMERIC(5,2),
    star_scores JSONB DEFAULT '{}'::jsonb,
    feedback TEXT,
    strengths JSONB DEFAULT '[]'::jsonb,
    improvements JSONB DEFAULT '[]'::jsonb,
    model_answer TEXT,
    duration_seconds INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.interview_answers ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "Users can manage own interview_answers" ON public.interview_answers FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on interview_answers" ON public.interview_answers FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_interview_answers_session_id ON public.interview_answers(session_id);

-- 3. career_snapshots
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
DO $$ BEGIN CREATE POLICY "Users can manage own career_snapshots" ON public.career_snapshots FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on career_snapshots" ON public.career_snapshots FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_career_snapshots_user_id ON public.career_snapshots(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_career_snapshots_unique ON public.career_snapshots(user_id, snapshot_date);

-- 4. review_sessions
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
ALTER TABLE public.review_sessions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "Users can manage own review_sessions" ON public.review_sessions FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on review_sessions" ON public.review_sessions FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_review_sessions_share_token ON public.review_sessions(share_token);

-- 5. learning_streaks
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
DO $$ BEGIN CREATE POLICY "Users can manage own learning_streaks" ON public.learning_streaks FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on learning_streaks" ON public.learning_streaks FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 6. api_keys
CREATE TABLE IF NOT EXISTS public.api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
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
DO $$ BEGIN CREATE POLICY "Users can manage own api_keys" ON public.api_keys FOR ALL USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on api_keys" ON public.api_keys FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 7. api_usage
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
ALTER TABLE public.api_usage ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "Users can view own api_usage" ON public.api_usage FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "Service role full access on api_usage" ON public.api_usage FOR ALL USING (auth.role() = 'service_role'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_api_usage_key_id ON public.api_usage(api_key_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_created_at ON public.api_usage(created_at);

-- Apply updated_at triggers
DO $$
DECLARE t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'evidence_mappings', 'career_snapshots', 'review_sessions',
        'learning_streaks', 'api_keys'
    ]) LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'set_updated_at' AND tgrelid = ('public.' || t)::regclass
        ) THEN
            EXECUTE format('CREATE TRIGGER set_updated_at BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column()', t);
        END IF;
    END LOOP;
END $$;

-- Realtime publication for learning_streaks
DO $$ BEGIN ALTER PUBLICATION supabase_realtime ADD TABLE public.learning_streaks; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
