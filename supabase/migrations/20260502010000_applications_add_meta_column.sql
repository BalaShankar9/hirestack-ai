-- ATLAS frontend follow-up: persist `meta` JSONB on `applications`.
--
-- The SSE pipeline complete payload (backend Slice 4.2) emits a
-- `meta` object that currently carries `atlas_candidate_validation`
-- (the ValidationSwarm's claim-by-claim report — see
-- ai_engine/agents/sub_agents/atlas/validation_swarm.py and
-- backend/app/api/routes/stream.py).
--
-- The frontend IntelligencePanel renders this report via
-- CandidateValidationPanel, but until now the column did not exist
-- on the table — so the panel only worked for the in-memory app
-- object during the SSE session, and disappeared on page reload.
--
-- This migration adds the column. ops.runAIPipeline now persists
-- `result.meta` into it, and mapApplicationRow already reads
-- `row.meta` into `ApplicationDoc.meta` (forward-compat code shipped
-- in commit aa80450).
--
-- The shape is intentionally an open JSONB bag — future ATLAS / agent
-- artifacts (e.g. archetypes attribution, model usage breakdown) can
-- co-exist under named keys without further migrations.

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS meta JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.applications.meta IS
  'Open JSONB bag for pipeline-emitted metadata. Currently carries '
  '`atlas_candidate_validation` (ValidationSwarm report). New keys '
  'may be added by future agents without schema changes. Distinct '
  'from `company_intel` (company research) and `metadata` columns '
  'on other tables.';
