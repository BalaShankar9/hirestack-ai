-- ═══════════════════════════════════════════════════════════════════════
-- HireStack AI — Enterprise Foundation Migration
-- Step 1: Create ALL tables first
-- Step 2: Enable RLS on all tables
-- Step 3: Add policies (after all tables exist)
-- Step 4: Add org_id to existing tables
-- ═══════════════════════════════════════════════════════════════════════

-- ════════ STEP 1: CREATE ALL TABLES ═════════════════════════════════

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

-- Also add Career Nexus columns if missing
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS social_links JSONB DEFAULT '{}';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS universal_documents JSONB DEFAULT '{}';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS universal_docs_version INTEGER DEFAULT 0;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS profile_version INTEGER DEFAULT 1;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS completeness_score INTEGER DEFAULT 0;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS resume_worth_score INTEGER DEFAULT 0;

-- ════════ STEP 2: ENABLE RLS ════════════════════════════════════════

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.org_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.org_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhooks ENABLE ROW LEVEL SECURITY;

-- ════════ STEP 3: ADD POLICIES (all tables exist now) ═══════════════

DO $$ BEGIN
  -- Organizations
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'organizations' AND policyname = 'Service role full access on organizations') THEN
    CREATE POLICY "Service role full access on organizations" ON public.organizations FOR ALL USING (auth.role() = 'service_role');
  END IF;
  -- Org Members
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'org_members' AND policyname = 'Service role full access on org_members') THEN
    CREATE POLICY "Service role full access on org_members" ON public.org_members FOR ALL USING (auth.role() = 'service_role');
  END IF;
  -- Candidates
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'candidates' AND policyname = 'Service role full access on candidates') THEN
    CREATE POLICY "Service role full access on candidates" ON public.candidates FOR ALL USING (auth.role() = 'service_role');
  END IF;
  -- Subscriptions
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'subscriptions' AND policyname = 'Service role full access on subscriptions') THEN
    CREATE POLICY "Service role full access on subscriptions" ON public.subscriptions FOR ALL USING (auth.role() = 'service_role');
  END IF;
  -- Usage Records
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'usage_records' AND policyname = 'Service role full access on usage_records') THEN
    CREATE POLICY "Service role full access on usage_records" ON public.usage_records FOR ALL USING (auth.role() = 'service_role');
  END IF;
  -- Audit Logs
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'audit_logs' AND policyname = 'Service role full access on audit_logs') THEN
    CREATE POLICY "Service role full access on audit_logs" ON public.audit_logs FOR ALL USING (auth.role() = 'service_role');
  END IF;
  -- Invitations
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'org_invitations' AND policyname = 'Service role full access on org_invitations') THEN
    CREATE POLICY "Service role full access on org_invitations" ON public.org_invitations FOR ALL USING (auth.role() = 'service_role');
  END IF;
  -- Webhooks
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'webhooks' AND policyname = 'Service role full access on webhooks') THEN
    CREATE POLICY "Service role full access on webhooks" ON public.webhooks FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;

-- ════════ STEP 4: INDEXES ═══════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_org_members_user ON public.org_members(user_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org ON public.org_members(org_id);
CREATE INDEX IF NOT EXISTS idx_candidates_org ON public.candidates(org_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON public.candidates(org_id, status);
CREATE INDEX IF NOT EXISTS idx_usage_org_period ON public.usage_records(org_id, period_start);
CREATE INDEX IF NOT EXISTS idx_audit_org ON public.audit_logs(org_id, created_at DESC);

-- ════════ STEP 5: ADD org_id TO EXISTING TABLES ═════════════════════

ALTER TABLE public.applications ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);
ALTER TABLE public.evidence ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);
ALTER TABLE public.job_descriptions ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id);

CREATE INDEX IF NOT EXISTS idx_applications_org ON public.applications(org_id);
CREATE INDEX IF NOT EXISTS idx_profiles_org ON public.profiles(org_id);
CREATE INDEX IF NOT EXISTS idx_evidence_org ON public.evidence(org_id);

-- ════════ DONE ══════════════════════════════════════════════════════
