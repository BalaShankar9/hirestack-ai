-- HireStack AI — Application Generation Intelligence Columns
-- Aligns the applications table with generated document strategy and company intel outputs.

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS discovered_documents JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS generated_documents JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS benchmark_documents JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS document_strategy TEXT,
  ADD COLUMN IF NOT EXISTS company_intel JSONB DEFAULT '{}'::jsonb;
