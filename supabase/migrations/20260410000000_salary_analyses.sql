-- Create salary_analyses table for Salary Negotiation Coach
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

CREATE POLICY "Users can manage own salary_analyses" ON public.salary_analyses
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on salary_analyses" ON public.salary_analyses
    FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_salary_analyses_user_id ON public.salary_analyses(user_id);
