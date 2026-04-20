-- HireStack AI — User FK On-Delete Cascade Hygiene
--
-- Closes a P0 schema drift item discovered by the cascade-integrity
-- test. Several tables had foreign keys to `users` declared without an
-- explicit ON DELETE clause. Postgres' default is NO ACTION, so
-- DELETE FROM users would currently FAIL with a FK-violation rather
-- than cascade properly — making GDPR Right-to-Erasure impossible.
--
-- This migration explicitly classifies each FK:
--   - CASCADE   → drop dependent rows (data is meaningless without owner)
--   - SET NULL  → preserve audit / billing / org rows, sever the link
--
-- Idempotent: each block drops the existing constraint (if present)
-- before re-adding it with the desired ON DELETE strategy.

BEGIN;

-- organizations.created_by → SET NULL (org survives owner deletion;
-- audit purposes — we want orgs to outlive individual founder accounts)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'organizations') THEN
    ALTER TABLE public.organizations DROP CONSTRAINT IF EXISTS organizations_created_by_fkey;
    ALTER TABLE public.organizations
      ADD CONSTRAINT organizations_created_by_fkey
      FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
END $$;

-- org_members.invited_by → SET NULL (membership stays, inviter cleared)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'org_members') THEN
    ALTER TABLE public.org_members DROP CONSTRAINT IF EXISTS org_members_invited_by_fkey;
    ALTER TABLE public.org_members
      ADD CONSTRAINT org_members_invited_by_fkey
      FOREIGN KEY (invited_by) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
END $$;

-- candidates.user_id → CASCADE (candidate profile is owned by the user)
-- candidates.assigned_recruiter → SET NULL (un-assign on recruiter delete)
-- candidates.created_by → SET NULL (preserve candidate, clear creator)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'candidates') THEN
    ALTER TABLE public.candidates DROP CONSTRAINT IF EXISTS candidates_user_id_fkey;
    ALTER TABLE public.candidates
      ADD CONSTRAINT candidates_user_id_fkey
      FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

    ALTER TABLE public.candidates DROP CONSTRAINT IF EXISTS candidates_assigned_recruiter_fkey;
    ALTER TABLE public.candidates
      ADD CONSTRAINT candidates_assigned_recruiter_fkey
      FOREIGN KEY (assigned_recruiter) REFERENCES public.users(id) ON DELETE SET NULL;

    ALTER TABLE public.candidates DROP CONSTRAINT IF EXISTS candidates_created_by_fkey;
    ALTER TABLE public.candidates
      ADD CONSTRAINT candidates_created_by_fkey
      FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
END $$;

-- usage_records.user_id → SET NULL (preserve billing-history rows
-- for accounting; we still know what was used, just not by whom)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'usage_records') THEN
    ALTER TABLE public.usage_records DROP CONSTRAINT IF EXISTS usage_records_user_id_fkey;
    ALTER TABLE public.usage_records
      ADD CONSTRAINT usage_records_user_id_fkey
      FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
END $$;

-- audit_logs.user_id → SET NULL (audit trail must survive user deletion)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_logs') THEN
    ALTER TABLE public.audit_logs DROP CONSTRAINT IF EXISTS audit_logs_user_id_fkey;
    ALTER TABLE public.audit_logs
      ADD CONSTRAINT audit_logs_user_id_fkey
      FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
END $$;

-- org_invitations.invited_by → SET NULL (invitation history preserved)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'org_invitations') THEN
    ALTER TABLE public.org_invitations DROP CONSTRAINT IF EXISTS org_invitations_invited_by_fkey;
    ALTER TABLE public.org_invitations
      ADD CONSTRAINT org_invitations_invited_by_fkey
      FOREIGN KEY (invited_by) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
END $$;

COMMIT;
