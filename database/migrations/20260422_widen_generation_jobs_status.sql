-- HireStack AI — Widen generation_jobs.status to accommodate 'succeeded_with_warnings'
-- The status value 'succeeded_with_warnings' is 23 characters but the column was
-- defined as VARCHAR(20), which would cause Postgres to raise:
--   ERROR: value too long for type character varying(20)
-- This migration widens the column to VARCHAR(30) to fit all known status strings
-- with headroom for future additions.

ALTER TABLE public.generation_jobs
    ALTER COLUMN status TYPE VARCHAR(30);
