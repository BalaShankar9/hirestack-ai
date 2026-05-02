-- ════════════════════════════════════════════════════════════════
-- 20260505000000_application_followups.sql
-- A1 — cadence engine: per-application follow-up schedule.
--
-- Stores the schedule of follow-up beats the cadence engine should
-- prepare for each application. The engine computes WHEN to send
-- (and which template to use); the worker generates the draft a few
-- minutes before scheduled_for; the user reviews and clicks Send
-- themselves.  HARD RULE: nothing is ever sent automatically.
--
-- Idempotent (CREATE TABLE IF NOT EXISTS, DO blocks swallow
-- duplicate_object on constraints/policies). Safe to re-apply.
-- Mirrors the schema sketched in the unstaged
-- 20260502000000_career_ops_integration.sql so any future
-- consolidation is a no-op.
-- ════════════════════════════════════════════════════════════════

BEGIN;

CREATE TABLE IF NOT EXISTS public.application_followups (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id       uuid NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    user_id              uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    scheduled_for        timestamptz NOT NULL,
    sent_at              timestamptz NULL,
    channel              text NOT NULL DEFAULT 'email',
    template_key         text NOT NULL DEFAULT 'first',
    draft                jsonb NOT NULL DEFAULT '{}'::jsonb,
    contact_name         text NULL,
    contact_email        text NULL,
    contact_linkedin     text NULL,
    followup_count       integer NOT NULL DEFAULT 0,
    status               text NOT NULL DEFAULT 'pending',
    dismissed_at         timestamptz NULL,
    response_received_at timestamptz NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    ALTER TABLE public.application_followups
        ADD CONSTRAINT application_followups_channel_chk
        CHECK (channel IN ('email','linkedin','form'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE public.application_followups
        ADD CONSTRAINT application_followups_status_chk
        CHECK (status IN ('pending','draft_ready','sent','dismissed','responded','expired'));
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
    'A1 cadence engine — scheduled follow-up beats per application. The followup_beat worker polls this table every 15min and generates drafts when scheduled_for <= now(). HARD RULE: nothing is ever sent automatically; status moves pending → draft_ready, then user clicks Send to move to sent.';

ALTER TABLE public.application_followups ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "own_followups" ON public.application_followups
        FOR ALL USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "service_role_followups" ON public.application_followups
        FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Reuse the existing set_updated_at() trigger if it exists in this
-- environment; otherwise this DO block silently no-ops so the
-- migration stays applicable to fresh schemas too.
DO $$ BEGIN
    CREATE TRIGGER trg_application_followups_updated_at
        BEFORE UPDATE ON public.application_followups
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION
    WHEN undefined_function THEN NULL;
    WHEN duplicate_object THEN NULL;
END $$;

COMMIT;
