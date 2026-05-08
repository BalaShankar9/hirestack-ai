-- HireStack AI — persist richer job match intelligence
--
-- ``job_sync.score_match`` already computes ``missing_skills`` and a
-- coarse ``recommendation``. Additive migration only: keep existing
-- rows working and backfill safe defaults for old databases.

ALTER TABLE public.job_matches
    ADD COLUMN IF NOT EXISTS missing_skills JSONB;

ALTER TABLE public.job_matches
    ADD COLUMN IF NOT EXISTS recommendation VARCHAR(20);

UPDATE public.job_matches
SET missing_skills = '[]'::jsonb
WHERE missing_skills IS NULL;

UPDATE public.job_matches
SET recommendation = 'consider'
WHERE recommendation IS NULL;

ALTER TABLE public.job_matches
    ALTER COLUMN missing_skills SET DEFAULT '[]'::jsonb;

ALTER TABLE public.job_matches
    ALTER COLUMN missing_skills SET NOT NULL;

ALTER TABLE public.job_matches
    ALTER COLUMN recommendation SET DEFAULT 'consider';

ALTER TABLE public.job_matches
    ALTER COLUMN recommendation SET NOT NULL;