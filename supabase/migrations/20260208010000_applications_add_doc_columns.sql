-- HireStack AI — Add missing application document columns
-- This migration aligns the `applications` table with the frontend modules:
-- Personal Statement, Portfolio, validation metadata, and version histories.

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS personal_statement_html TEXT,
  ADD COLUMN IF NOT EXISTS portfolio_html TEXT,
  ADD COLUMN IF NOT EXISTS validation JSONB,
  ADD COLUMN IF NOT EXISTS ps_versions JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS portfolio_versions JSONB DEFAULT '[]'::jsonb;

