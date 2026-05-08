-- ════════════════════════════════════════════════════════════════
-- 20260509000000_missions_and_drafts.sql
-- M1 — mission-mode foundation: missions + mission_drafts tables,
-- plus the additive applications.status taxonomy extension for
-- `evaluated` so surfaced-but-not-sent workspaces can be modeled
-- without overloading `draft` or `skip`.
--
-- Idempotent where practical (CREATE TABLE IF NOT EXISTS, DO blocks
-- swallow duplicate_object on constraints/policies). Safe to re-apply.
-- ════════════════════════════════════════════════════════════════

BEGIN;

ALTER TABLE public.applications
  DROP CONSTRAINT IF EXISTS chk_applications_status;

ALTER TABLE public.applications
  ADD CONSTRAINT chk_applications_status
  CHECK (status IN (
    'draft',
    'active',
    'submitted',
    'interview',
    'offer',
    'rejected',
    'withdrawn',
    'archived',
    'responded',
    'discarded',
    'skip',
    'evaluated'
  ));

CREATE TABLE IF NOT EXISTS public.missions (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name                    text NOT NULL,
    status                  text NOT NULL DEFAULT 'active',
    role_titles             text[] NOT NULL DEFAULT '{}',
    locations               text[] NOT NULL DEFAULT '{}',
    comp_band_min           integer NULL,
    comp_band_max           integer NULL,
    must_haves              text[] NOT NULL DEFAULT '{}',
    deal_breakers           text[] NOT NULL DEFAULT '{}',
    min_fit_score           numeric(3,1) NOT NULL DEFAULT 4.0,
    target_volume_per_week  integer NOT NULL DEFAULT 5,
    voice_preset            text NOT NULL DEFAULT 'confident_selective',
    created_at              timestamptz NOT NULL DEFAULT now(),
    paused_at               timestamptz NULL
);

DO $$ BEGIN
    ALTER TABLE public.missions
        ADD CONSTRAINT missions_status_chk
        CHECK (status IN ('active', 'paused', 'archived'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.missions
        ADD CONSTRAINT missions_name_chk
        CHECK (btrim(name) <> '');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.missions
        ADD CONSTRAINT missions_min_fit_score_chk
        CHECK (min_fit_score BETWEEN 0 AND 5);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.missions
        ADD CONSTRAINT missions_target_volume_chk
        CHECK (target_volume_per_week >= 1 AND target_volume_per_week <= 100);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.missions
        ADD CONSTRAINT missions_comp_band_chk
        CHECK (
            (comp_band_min IS NULL OR comp_band_min >= 0)
            AND (comp_band_max IS NULL OR comp_band_max >= 0)
            AND (
                comp_band_min IS NULL
                OR comp_band_max IS NULL
                OR comp_band_max >= comp_band_min
            )
        );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.missions
        ADD CONSTRAINT missions_voice_preset_chk
        CHECK (voice_preset IN (
            'confident_selective',
            'warm_eager',
            'formal_traditional'
        ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_missions_user_status_created
    ON public.missions(user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_missions_user_created
    ON public.missions(user_id, created_at DESC);

COMMENT ON TABLE public.missions IS
    'M1 — user-defined job-search missions that scope role titles, locations, compensation targets, fit threshold, and voice preset for future orchestration.';

ALTER TABLE public.missions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "own_missions" ON public.missions
        FOR ALL USING (auth.uid() = user_id)
        WITH CHECK (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "service_role_missions" ON public.missions
        FOR ALL USING (auth.role() = 'service_role')
        WITH CHECK (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS public.mission_drafts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id      uuid NOT NULL REFERENCES public.missions(id) ON DELETE CASCADE,
    application_id  uuid NULL REFERENCES public.applications(id) ON DELETE SET NULL,
    surfaced_at     timestamptz NOT NULL DEFAULT now(),
    prepared_at     timestamptz NULL,
    sent_at         timestamptz NULL,
    status          text NOT NULL DEFAULT 'surfaced',
    fit_score       numeric(3,1) NULL
);

DO $$ BEGIN
    ALTER TABLE public.mission_drafts
        ADD CONSTRAINT mission_drafts_status_chk
        CHECK (status IN (
            'surfaced',
            'prepared',
            'ready_for_user',
            'sent',
            'skipped',
            'expired'
        ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.mission_drafts
        ADD CONSTRAINT mission_drafts_fit_score_chk
        CHECK (fit_score IS NULL OR fit_score BETWEEN 0 AND 5);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.mission_drafts
        ADD CONSTRAINT mission_drafts_mission_application_uniq
        UNIQUE (mission_id, application_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_mission_drafts_mission_status_surfaced
    ON public.mission_drafts(mission_id, status, surfaced_at DESC);

CREATE INDEX IF NOT EXISTS idx_mission_drafts_mission_surfaced
    ON public.mission_drafts(mission_id, surfaced_at DESC);

COMMENT ON TABLE public.mission_drafts IS
    'M1 — surfaced and prepared candidate workspaces attached to a mission. Later orchestration can advance rows from surfaced to ready_for_user to sent.';

ALTER TABLE public.mission_drafts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "own_mission_drafts" ON public.mission_drafts
        FOR ALL USING (
            EXISTS (
                SELECT 1
                FROM public.missions m
                WHERE m.id = mission_id AND m.user_id = auth.uid()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM public.missions m
                WHERE m.id = mission_id AND m.user_id = auth.uid()
            )
        );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "service_role_mission_drafts" ON public.mission_drafts
        FOR ALL USING (auth.role() = 'service_role')
        WITH CHECK (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMIT;