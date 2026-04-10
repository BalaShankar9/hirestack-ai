-- CHECK constraints for Tier 2 feature enums
ALTER TABLE ats_scans
  ADD CONSTRAINT ck_ats_scans_status
  CHECK (status IN ('pending', 'scanning', 'completed', 'failed'));

ALTER TABLE interview_sessions
  ADD CONSTRAINT ck_interview_status
  CHECK (status IN ('active', 'completed', 'abandoned', 'expired'));
