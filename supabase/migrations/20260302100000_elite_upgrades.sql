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
            'DROP TRIGGER IF EXISTS %I ON public.%I; '
            'CREATE TRIGGER %I BEFORE UPDATE ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();',
            'update_' || t || '_updated_at', t, 'update_' || t || '_updated_at', t
        );
    END LOOP;
END;
$$;

-- Enable Realtime on key new tables
ALTER PUBLICATION supabase_realtime ADD TABLE public.ats_scans;
ALTER PUBLICATION supabase_realtime ADD TABLE public.interview_sessions;
ALTER PUBLICATION supabase_realtime ADD TABLE public.learning_streaks;
