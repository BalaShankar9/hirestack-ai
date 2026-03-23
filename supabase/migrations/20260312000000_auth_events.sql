-- Migration: Auth events audit log
-- Tracks sign‑in / sign‑out / failed auth / token refresh / password changes.
-- Required for enterprise compliance (SOC 2, ISO 27001 audit trails).

CREATE TABLE IF NOT EXISTS public.auth_events (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    event_type  TEXT        NOT NULL,          -- login | logout | failed_login | token_refresh | password_change | mfa_setup | account_locked
    ip_address  INET,
    user_agent  TEXT,
    metadata    JSONB       DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_auth_events_user_id    ON public.auth_events(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_events_created_at ON public.auth_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_auth_events_event_type ON public.auth_events(event_type);

-- RLS
ALTER TABLE public.auth_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'auth_events' AND policyname = 'Users can view own auth events') THEN
    CREATE POLICY "Users can view own auth events" ON public.auth_events FOR SELECT USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'auth_events' AND policyname = 'Service role full access on auth_events') THEN
    CREATE POLICY "Service role full access on auth_events" ON public.auth_events FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;
