-- ═══════════════════════════════════════════════════════════════════════════════
-- HireStack AI — Career-Ops Integration (consolidated migration)
-- Ref: docs/superpowers/plans/2026-05-02-career-ops-integration.md
--
-- Adds schema for:
--   Sprint 1 — Trust Layer
--     • applications.status_canonical, legitimacy_tier/signals, archetype_preset,
--       scorecard_ag
--     • job_scan_history (ghost-detection repost signal)
--     • public_ghost_scans (anonymized aggregate for weekly index)
--   Sprint 2 — Retention Loop
--     • application_followups (scheduled follow-up cadence + drafts)
--   Sprint 3 — Signal Layer
--     • archetype_presets (seed: 6 career-ops archetypes)
--   Sprint 4 — Voice & Quality
--     • story_bank (STAR+R reusable interview stories)
--     • writing_samples (voice calibration inputs)
--     • proof_points (split from evidence — quantified claims)
--
-- Safety:
--   • All ADD/CREATE guarded with IF NOT EXISTS
--   • Policies wrapped in DO $$ EXCEPTION WHEN duplicate_object THEN NULL blocks
--   • Backfill is idempotent (UPDATE ... WHERE status_canonical IS NULL)
--   • Safe to re-apply
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────
-- 1. applications — add legitimacy, archetype, canonical status, A-G scorecard
-- ───────────────────────────────────────────────────────────────────────────
ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS status_canonical    TEXT,
    ADD COLUMN IF NOT EXISTS legitimacy_tier     TEXT,
    ADD COLUMN IF NOT EXISTS legitimacy_signals  JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS archetype_preset    TEXT,
    ADD COLUMN IF NOT EXISTS scorecard_ag        JSONB DEFAULT '{}'::jsonb;

-- Check constraints (DO blocks so re-application is safe)
DO $$ BEGIN
    ALTER TABLE public.applications
        ADD CONSTRAINT applications_legitimacy_tier_chk
        CHECK (legitimacy_tier IS NULL OR legitimacy_tier IN ('high_confidence','caution','suspicious'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.applications
        ADD CONSTRAINT applications_status_canonical_chk
        CHECK (status_canonical IS NULL OR status_canonical IN (
            'evaluated','applied','answered','contact','interview',
            'offer','rejected','discarded','do_not_apply'
        ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Column comments (self-documenting schema)
COMMENT ON COLUMN public.applications.status_canonical IS
    'career-ops canonical state: evaluated → applied → answered/contact → interview → offer/rejected/discarded/do_not_apply. Coexists with legacy status column.';
COMMENT ON COLUMN public.applications.legitimacy_tier IS
    'Ghost-job assessment: high_confidence | caution | suspicious.';
COMMENT ON COLUMN public.applications.legitimacy_signals IS
    'Full LegitimacyReport payload: { score, summary, signals: [...] }.';
COMMENT ON COLUMN public.applications.archetype_preset IS
    'FK-ish ref to archetype_presets.id (llmops, agentic, ai_pm, ai_sa, ai_fde, ai_transformation).';
COMMENT ON COLUMN public.applications.scorecard_ag IS
    'career-ops A-G evaluation blocks: { role_summary, match, level_strategy, comp, personalization, interview_plan, legitimacy, global_score }.';

CREATE INDEX IF NOT EXISTS idx_applications_legitimacy_tier
    ON public.applications(legitimacy_tier) WHERE legitimacy_tier IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_applications_status_canonical
    ON public.applications(status_canonical) WHERE status_canonical IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_applications_archetype
    ON public.applications(archetype_preset) WHERE archetype_preset IS NOT NULL;

-- ───────────────────────────────────────────────────────────────────────────
-- 2. Backfill status_canonical from legacy status
-- ───────────────────────────────────────────────────────────────────────────
-- Idempotent: only updates rows where canonical is still NULL.
UPDATE public.applications
SET status_canonical = CASE
    WHEN LOWER(COALESCE(status, '')) IN ('draft','generating','complete','generated','ready','idle','') THEN 'evaluated'
    WHEN LOWER(COALESCE(status, '')) = 'applied' THEN 'applied'
    WHEN LOWER(COALESCE(status, '')) IN ('offered','offer') THEN 'offer'
    WHEN LOWER(COALESCE(status, '')) = 'rejected' THEN 'rejected'
    WHEN LOWER(COALESCE(status, '')) IN ('interview','interviewing') THEN 'interview'
    WHEN LOWER(COALESCE(status, '')) IN ('discarded','archived') THEN 'discarded'
    ELSE 'evaluated'
END
WHERE status_canonical IS NULL;

-- Promote via outcome tracking: if a callback was received, at minimum 'answered'
UPDATE public.applications
SET status_canonical = 'answered'
WHERE callback_received_at IS NOT NULL
  AND status_canonical IN ('evaluated','applied');

-- Promote to offer when offer_received_at is set
UPDATE public.applications
SET status_canonical = 'offer'
WHERE offer_received_at IS NOT NULL
  AND status_canonical NOT IN ('offer','rejected');

-- ───────────────────────────────────────────────────────────────────────────
-- 3. job_scan_history — repost signal for ghost detection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.job_scan_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url_canonical   TEXT NOT NULL UNIQUE,
    company_slug    TEXT NOT NULL,
    role_title      TEXT NOT NULL DEFAULT '',
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    times_seen      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_job_scan_history_company_role
    ON public.job_scan_history(company_slug, role_title);
CREATE INDEX IF NOT EXISTS idx_job_scan_history_last_seen
    ON public.job_scan_history(last_seen DESC);

COMMENT ON TABLE public.job_scan_history IS
    'Global (not per-user) record of every job URL scanned. Powers repost detection for the ghost-job signal.';

-- No RLS — this is a shared global table. Only backend writes via service role.
-- Reading is not user-scoped; handled via service_role inside ScanHistoryService.

-- ───────────────────────────────────────────────────────────────────────────
-- 4. public_ghost_scans — anonymized aggregation for the weekly Ghost Index
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.public_ghost_scans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url_hash        TEXT NOT NULL,             -- sha256(canonical_url)
    company_slug    TEXT,
    tier            TEXT,
    signals         JSONB DEFAULT '[]'::jsonb,
    scanned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_public_ghost_scans_company_date
    ON public.public_ghost_scans(company_slug, scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_public_ghost_scans_tier_date
    ON public.public_ghost_scans(tier, scanned_at DESC);

COMMENT ON TABLE public.public_ghost_scans IS
    'Anonymized record of every /api/public/ghost-check call. url_hash only — no raw URLs stored. Powers weekly Ghost Index blog post + public benchmarks.';

-- ───────────────────────────────────────────────────────────────────────────
-- 5. application_followups — Sprint 2 retention loop
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.application_followups (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id      UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    scheduled_for       TIMESTAMPTZ NOT NULL,
    sent_at             TIMESTAMPTZ,
    channel             TEXT NOT NULL DEFAULT 'email',
    template_key        TEXT NOT NULL DEFAULT 'first',
    draft               JSONB DEFAULT '{}'::jsonb,
    contact_name        TEXT,
    contact_email       TEXT,
    contact_linkedin    TEXT,
    followup_count      INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pending',
    dismissed_at        TIMESTAMPTZ,
    response_received_at TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
    ALTER TABLE public.application_followups
        ADD CONSTRAINT application_followups_channel_chk
        CHECK (channel IN ('email','linkedin','form'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.application_followups
        ADD CONSTRAINT application_followups_status_chk
        CHECK (status IN ('pending','draft_ready','sent','dismissed','responded'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.application_followups
        ADD CONSTRAINT application_followups_template_chk
        CHECK (template_key IN ('first','linkedin','second','cold_reopen'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_followups_user_scheduled
    ON public.application_followups(user_id, scheduled_for)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_followups_application
    ON public.application_followups(application_id);
CREATE INDEX IF NOT EXISTS idx_followups_due_beat
    ON public.application_followups(scheduled_for, status)
    WHERE status = 'pending';

COMMENT ON TABLE public.application_followups IS
    'Scheduled follow-up cadence per application. The followup_beat worker polls this table every 15min and generates drafts when scheduled_for <= now().';

ALTER TABLE public.application_followups ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "own_followups" ON public.application_followups
        FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY "service_role_followups" ON public.application_followups
        FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- updated_at trigger reusing the existing pattern
DO $$ BEGIN
    CREATE TRIGGER trg_application_followups_updated_at
        BEFORE UPDATE ON public.application_followups
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION WHEN undefined_function THEN
    -- set_updated_at() doesn't exist yet in this environment; skip.
    NULL;
WHEN duplicate_object THEN NULL; END $$;

-- ───────────────────────────────────────────────────────────────────────────
-- 6. archetype_presets — Sprint 3, seeded with 6 career-ops archetypes
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.archetype_presets (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT,
    jd_signals          TEXT[] NOT NULL DEFAULT '{}',
    proof_priorities    TEXT[] NOT NULL DEFAULT '{}',
    star_focus          TEXT[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.archetype_presets IS
    'Career-ops 6 fixed archetypes. Users pick one in Career Nexus onboarding; it influences Critic, DocGenerator, and Interview chains.';

-- Seed data (INSERT ON CONFLICT DO NOTHING — safe to re-run)
INSERT INTO public.archetype_presets (id, name, description, jd_signals, proof_priorities, star_focus) VALUES
  ('llmops',
   'AI Platform / LLMOps',
   'Observability, evals, pipelines, monitoring, reliability for AI systems in production.',
   ARRAY['observability','evals','pipelines','monitoring','reliability','llm','inference','mlops'],
   ARRAY['evals','monitoring','pipelines','reliability_metrics'],
   ARRAY['production_hardening','incident_response','eval_harness']),
  ('agentic',
   'Agentic / Automation',
   'Multi-agent orchestration, human-in-the-loop workflows, tool use.',
   ARRAY['agent','HITL','orchestration','workflow','multi-agent','tool use','autonomous'],
   ARRAY['multi_agent','HITL','orchestration','tool_integrations'],
   ARRAY['error_handling','state_management','human_escalation']),
  ('ai_pm',
   'Technical AI PM',
   'PRDs, discovery, roadmap, stakeholders for AI products.',
   ARRAY['PRD','roadmap','discovery','stakeholder','product manager','product owner','PRFAQ'],
   ARRAY['discovery','metrics','tradeoffs','customer_research'],
   ARRAY['tradeoffs','prioritization','stakeholder_alignment']),
  ('ai_sa',
   'AI Solutions Architect',
   'Enterprise architecture, integrations, systems design for AI deployments.',
   ARRAY['architecture','enterprise','integration','design','systems','solutions','reference architecture'],
   ARRAY['system_design','integration','enterprise_scale'],
   ARRAY['architecture_decisions','integration_patterns','scale_engineering']),
  ('ai_fde',
   'AI Forward Deployed',
   'Client-facing, fast delivery, prototyping, field deployment of AI.',
   ARRAY['client-facing','deploy','prototype','fast delivery','field','forward deployed','customer'],
   ARRAY['delivery_speed','client_facing','prototyping'],
   ARRAY['speed_of_delivery','customer_impact','prototype_to_production']),
  ('ai_transformation',
   'AI Transformation',
   'Change management, adoption, enablement for AI-driven transformation.',
   ARRAY['change management','adoption','enablement','transformation','program','AI strategy'],
   ARRAY['adoption','change_mgmt','program_management'],
   ARRAY['organizational_change','executive_alignment','enablement_programs'])
ON CONFLICT (id) DO NOTHING;

-- Soft FK from applications.archetype_preset → archetype_presets.id
DO $$ BEGIN
    ALTER TABLE public.applications
        ADD CONSTRAINT applications_archetype_preset_fk
        FOREIGN KEY (archetype_preset) REFERENCES public.archetype_presets(id)
        ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
WHEN others THEN
    -- If the FK can't be added (e.g. orphan values exist), log and skip; don't block migration
    RAISE NOTICE 'archetype FK skipped: %', SQLERRM;
END $$;

-- ───────────────────────────────────────────────────────────────────────────
-- 7. story_bank — Sprint 4, reusable STAR+R interview stories
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.story_bank (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    situation           TEXT NOT NULL DEFAULT '',
    task                TEXT NOT NULL DEFAULT '',
    action              TEXT NOT NULL DEFAULT '',
    result              TEXT NOT NULL DEFAULT '',
    reflection          TEXT NOT NULL DEFAULT '',
    tags                TEXT[] NOT NULL DEFAULT '{}',
    archetype_affinity  TEXT[] NOT NULL DEFAULT '{}',
    times_used          INTEGER NOT NULL DEFAULT 0,
    last_used_at        TIMESTAMPTZ,
    source_application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_story_bank_user
    ON public.story_bank(user_id);
CREATE INDEX IF NOT EXISTS idx_story_bank_tags
    ON public.story_bank USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_story_bank_archetype
    ON public.story_bank USING GIN(archetype_affinity);

COMMENT ON TABLE public.story_bank IS
    'Reusable interview stories in STAR+R format (+R = Reflection column for seniority signal). Each story can be tagged + affinity-mapped to archetypes.';

ALTER TABLE public.story_bank ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "own_stories" ON public.story_bank
        FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY "service_role_stories" ON public.story_bank
        FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ───────────────────────────────────────────────────────────────────────────
-- 8. writing_samples — Sprint 4, voice calibration
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.writing_samples (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL DEFAULT 'other',
    content         TEXT NOT NULL,
    derived_style   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
    ALTER TABLE public.writing_samples
        ADD CONSTRAINT writing_samples_kind_chk
        CHECK (kind IN ('cover_letter','linkedin_about','email','blog','slack','other'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_writing_samples_user
    ON public.writing_samples(user_id);

COMMENT ON TABLE public.writing_samples IS
    'User-provided past writing used by style_signal_deriver to calibrate generated output voice.';

ALTER TABLE public.writing_samples ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "own_writing_samples" ON public.writing_samples
        FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ───────────────────────────────────────────────────────────────────────────
-- 9. proof_points — Sprint 4, split from evidence (quantified claims)
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.proof_points (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    claim               TEXT NOT NULL,
    metric              TEXT,
    context             TEXT,
    evidence_refs       UUID[] NOT NULL DEFAULT '{}',
    archetype_affinity  TEXT[] NOT NULL DEFAULT '{}',
    confidence          NUMERIC(3,2) NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    times_used          INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proof_points_user
    ON public.proof_points(user_id);
CREATE INDEX IF NOT EXISTS idx_proof_points_archetype
    ON public.proof_points USING GIN(archetype_affinity);

COMMENT ON TABLE public.proof_points IS
    'Quantified candidate claims ("Built X that did Y"). Distinct from evidence (files/certs). evidence_refs holds optional UUIDs into the evidence table.';

ALTER TABLE public.proof_points ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "own_proof_points" ON public.proof_points
        FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ───────────────────────────────────────────────────────────────────────────
-- 10. Convenience view: weekly ghost-index aggregates
-- ───────────────────────────────────────────────────────────────────────────
-- Used by /benchmarks and the weekly blog post generator.
CREATE OR REPLACE VIEW public.v_weekly_ghost_index AS
SELECT
    DATE_TRUNC('week', scanned_at)                      AS week_start,
    company_slug,
    tier,
    COUNT(*)                                            AS scan_count
FROM public.public_ghost_scans
WHERE scanned_at > NOW() - INTERVAL '13 weeks'
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC;

COMMENT ON VIEW public.v_weekly_ghost_index IS
    'Rolling 13-week ghost-scan aggregates by company + tier. Read by backend for public Ghost Index blog + weekly digest.';

-- ═══════════════════════════════════════════════════════════════════════════════
-- End of career-ops integration migration.
-- ═══════════════════════════════════════════════════════════════════════════════
