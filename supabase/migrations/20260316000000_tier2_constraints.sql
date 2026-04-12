-- CHECK constraints for Tier 2 feature enums (idempotent)
DO $$ BEGIN
  ALTER TABLE ats_scans ADD CONSTRAINT ck_ats_scans_status CHECK (status IN ('pending', 'scanning', 'completed', 'failed'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE interview_sessions ADD CONSTRAINT ck_interview_status CHECK (status IN ('active', 'completed', 'abandoned', 'expired'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
