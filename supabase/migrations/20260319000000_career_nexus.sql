-- Career Nexus: Add profile versioning, social links, and career intelligence columns
-- These columns support the Career Nexus feature (profile hub, universal docs, completeness scoring)

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS social_links JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS universal_documents JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS universal_docs_version INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS profile_version INTEGER DEFAULT 1,
  ADD COLUMN IF NOT EXISTS completeness_score INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS resume_worth_score INTEGER DEFAULT 0;
