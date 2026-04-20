-- ============================================================
-- Orchestration foundation tables for the v4 agent system.
--
-- Adds the persistence layer that the new orchestration package
-- needs to durably store typed artifacts and to reason over the
-- application/module state machine.
--
-- Safe to apply on top of the existing schema: every change is
-- additive and idempotent (IF NOT EXISTS / DO blocks).
-- ============================================================

-- ── 1. agent_artifacts ─────────────────────────────────────────
-- Every typed artifact produced by any agent in any run lands
-- here. This is the single source of truth that lets us:
--   * Resume a run from any artifact boundary
--   * Build a full lineage / provenance graph
--   * Replay individual agents on identical input
--   * Cache expensive artifacts across runs

CREATE TABLE IF NOT EXISTS public.agent_artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID REFERENCES public.applications(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL,

    -- Logical name of the agent that produced the artifact, e.g.
    -- "atlas", "cipher", "quill.cv_writer".
    agent_name      TEXT NOT NULL,

    -- Schema name, matches ARTIFACT_TYPES in artifact_contracts.py
    -- e.g. "BenchmarkProfile", "SkillGapMap", "TailoredDocumentBundle".
    artifact_type   TEXT NOT NULL,

    -- Schema version of the artifact_type, e.g. "1.0.0".
    version         TEXT NOT NULL DEFAULT '1.0.0',

    -- Lineage: id of the immediate parent artifact (nullable for roots).
    parent_artifact_id UUID REFERENCES public.agent_artifacts(id) ON DELETE SET NULL,

    -- The artifact body (Pydantic model dumped as JSON).
    content         JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Self-reported confidence (0..1) and strongest evidence tier.
    confidence      DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    evidence_tier   TEXT NOT NULL DEFAULT 'unknown',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS agent_artifacts_application_idx
    ON public.agent_artifacts (application_id, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_artifacts_user_idx
    ON public.agent_artifacts (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_artifacts_type_idx
    ON public.agent_artifacts (artifact_type, application_id);

CREATE INDEX IF NOT EXISTS agent_artifacts_lineage_idx
    ON public.agent_artifacts (parent_artifact_id);

-- Trigger to maintain updated_at automatically.
CREATE OR REPLACE FUNCTION public.touch_agent_artifacts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS agent_artifacts_touch ON public.agent_artifacts;
CREATE TRIGGER agent_artifacts_touch
    BEFORE UPDATE ON public.agent_artifacts
    FOR EACH ROW
    EXECUTE FUNCTION public.touch_agent_artifacts_updated_at();

-- RLS: the table contains only data the user already owns through the
-- linked application; tightly scope reads to the owning user.
ALTER TABLE public.agent_artifacts ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'agent_artifacts'
          AND policyname = 'agent_artifacts_owner_select'
    ) THEN
        CREATE POLICY agent_artifacts_owner_select
            ON public.agent_artifacts
            FOR SELECT
            USING (auth.uid() = user_id);
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'agent_artifacts'
          AND policyname = 'agent_artifacts_owner_modify'
    ) THEN
        CREATE POLICY agent_artifacts_owner_modify
            ON public.agent_artifacts
            FOR ALL
            USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);
    END IF;
END$$;

-- ── 2. generation_job_events index ──────────────────────────────
-- The event log already exists; adding a covering index for the
-- query pattern the future Mission Control UI hits most often:
-- "give me all events for application X, ordered newest first".

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'generation_job_events'
    ) THEN
        CREATE INDEX IF NOT EXISTS generation_job_events_app_event_idx
            ON public.generation_job_events (application_id, event_name, created_at DESC);
    END IF;
END$$;

-- ── 3. application module-state validity check ──────────────────
-- The applications.modules JSONB column carries per-module status.
-- We add a soft check via trigger to reject states outside the
-- v4 ModuleState enum. This is advisory only — reads are unaffected,
-- writes that violate the constraint are still rejected with a clear
-- error message rather than producing silent data corruption.

CREATE OR REPLACE FUNCTION public.validate_application_module_states()
RETURNS TRIGGER AS $$
DECLARE
    valid_states  TEXT[] := ARRAY[
        'not_started', 'queued', 'running', 'blocked',
        'waiting_for_dependency', 'validating', 'completed',
        'failed', 'retrying', 'skipped_with_reason',
        -- Legacy values still in flight; accept them so existing rows
        -- don't break under the new check.
        'idle', 'pending', 'in_progress', 'success', 'error', 'ready'
    ];
    module_key    TEXT;
    module_value  JSONB;
    module_state  TEXT;
BEGIN
    IF NEW.modules IS NULL OR jsonb_typeof(NEW.modules) <> 'object' THEN
        RETURN NEW;
    END IF;

    FOR module_key, module_value IN SELECT * FROM jsonb_each(NEW.modules) LOOP
        IF jsonb_typeof(module_value) = 'object' THEN
            module_state := module_value->>'state';
            IF module_state IS NOT NULL
               AND NOT (module_state = ANY (valid_states)) THEN
                RAISE EXCEPTION
                    'Invalid module state "%" for module "%"',
                    module_state, module_key
                    USING HINT = 'Use one of the v4 ModuleState values';
            END IF;
        END IF;
    END LOOP;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'applications'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'modules'
    ) THEN
        DROP TRIGGER IF EXISTS validate_application_module_states_trg ON public.applications;
        CREATE TRIGGER validate_application_module_states_trg
            BEFORE INSERT OR UPDATE OF modules ON public.applications
            FOR EACH ROW
            EXECUTE FUNCTION public.validate_application_module_states();
    END IF;
END$$;

COMMENT ON TABLE public.agent_artifacts IS
    'Typed, versioned, lineage-tagged artifacts produced by v4 orchestration agents.';
