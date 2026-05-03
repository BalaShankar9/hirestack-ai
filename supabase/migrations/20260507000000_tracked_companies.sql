-- ════════════════════════════════════════════════════════════════
-- 20260507000000_tracked_companies.sql
-- B2 — `tracked_companies` table powers the portal_scanner worker
-- (B1.next, commit 4b57519). Each row tells the scanner WHICH ATS
-- portal to fan-out a fetch against on behalf of the user.
--
-- Field names align with the existing pure-fn `TrackedCompany`
-- dataclass in backend/app/services/portal_scanner.py (provider +
-- company_slug + workday_tenant) — NOT the plan-doc draft (ats_*
-- names) — so the service layer can map row → dataclass cleanly
-- without alias plumbing.
--
-- Provider CHECK constraint matches the 6 providers the scanner
-- actually parses today (Provider Literal in portal_scanner.py).
-- Adding a 7th later requires a CHECK extension migration AND a
-- new parser — both must ship together so we never have rows
-- pointing at providers the scanner can't reach.
--
-- Idempotent (CREATE TABLE IF NOT EXISTS, DO blocks swallow
-- duplicate_object on constraints/policies). Safe to re-apply.
-- ════════════════════════════════════════════════════════════════

BEGIN;

CREATE TABLE IF NOT EXISTS public.tracked_companies (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    org_id          uuid NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    provider        text NOT NULL,
    company_slug    text NOT NULL,
    workday_tenant  text NULL,
    display_name    text NOT NULL,
    careers_url     text NULL,
    enabled         boolean NOT NULL DEFAULT true,
    last_scanned_at timestamptz NULL,
    scan_error      text NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    ALTER TABLE public.tracked_companies
        ADD CONSTRAINT tracked_companies_provider_chk
        CHECK (provider IN (
            'greenhouse','lever','ashby','workday','workable','smartrecruiters'
        ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Workday rows MUST carry a tenant (e.g. 'acme.wd5'); other
-- providers MUST NOT (avoids garbage data drift if the UI reuses
-- the same form for all providers).
DO $$ BEGIN
    ALTER TABLE public.tracked_companies
        ADD CONSTRAINT tracked_companies_workday_tenant_chk
        CHECK (
            (provider = 'workday' AND workday_tenant IS NOT NULL AND workday_tenant <> '')
            OR
            (provider <> 'workday' AND workday_tenant IS NULL)
        );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- One row per (user, provider, slug) — re-adding the same company
-- on the same portal is a no-op idempotent upsert from the API.
DO $$ BEGIN
    ALTER TABLE public.tracked_companies
        ADD CONSTRAINT tracked_companies_user_provider_slug_uniq
        UNIQUE (user_id, provider, company_slug);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Hot index for the worker's "what should I scan next?" loop:
-- enabled rows ordered by oldest last_scanned_at first.
CREATE INDEX IF NOT EXISTS idx_tracked_companies_user_enabled
    ON public.tracked_companies(user_id, last_scanned_at NULLS FIRST)
    WHERE enabled = true;

CREATE INDEX IF NOT EXISTS idx_tracked_companies_user
    ON public.tracked_companies(user_id);

COMMENT ON TABLE public.tracked_companies IS
    'B2 — companies a user is watching on one ATS portal. Powers B1 portal_scanner_worker fan-out. provider + company_slug + workday_tenant fields mirror the TrackedCompany dataclass in services/portal_scanner.py exactly.';

ALTER TABLE public.tracked_companies ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "own_tracked_companies" ON public.tracked_companies
        FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "service_role_tracked_companies" ON public.tracked_companies
        FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMIT;
