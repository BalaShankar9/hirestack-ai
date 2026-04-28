-- HireStack AI — Widen generation_jobs.status column
-- Mirrors: database/migrations/20260422_widen_generation_jobs_status.sql
--
-- WHY THIS IS NEEDED:
--   The status value 'succeeded_with_warnings' is 23 characters.
--   The column was originally defined as VARCHAR(20) in 20260209000000_generation_jobs.sql.
--   PostgreSQL raises "value too long for type character varying(20)" when the backend
--   tries to persist this status, causing all critic-gate-downgraded jobs to fail with a
--   DB error instead of recording honest completion.
--
-- This migration widens the column to VARCHAR(30) to fit all current status values
-- with headroom for future additions:
--   queued (6), running (7), succeeded (9), failed (6), cancelled (9),
--   succeeded_with_warnings (23) — all fit in VARCHAR(30).

ALTER TABLE public.generation_jobs
    ALTER COLUMN status TYPE VARCHAR(30);
