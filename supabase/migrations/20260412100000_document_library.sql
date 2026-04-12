-- Document Library: Unified storage for Benchmark, Fixed, and Tailored documents
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── 1. document_library table ────────────────────────────────────────
-- Stores all generated documents across three categories:
--   • benchmark  → Ideal-candidate standard documents (per-application)
--   • fixed      → User's persistent evolving library (cross-application)
--   • tailored   → Job-specific adapted documents (per-application)

CREATE TABLE IF NOT EXISTS document_library (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id  uuid REFERENCES applications(id) ON DELETE SET NULL,
    doc_type        text NOT NULL,                                -- e.g. 'cv', 'cover_letter', 'executive_summary'
    doc_category    text NOT NULL DEFAULT 'tailored'
                    CHECK (doc_category IN ('benchmark', 'fixed', 'tailored')),
    label           text NOT NULL DEFAULT '',                     -- human-readable name
    html_content    text NOT NULL DEFAULT '',                     -- the actual document HTML
    metadata        jsonb NOT NULL DEFAULT '{}',                  -- scores, planner context, tone, etc.
    version         integer NOT NULL DEFAULT 1,
    status          text NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned', 'generating', 'ready', 'error')),
    error_message   text,
    source          text NOT NULL DEFAULT 'planner'               -- 'planner', 'user_request', 'auto_evolve'
                    CHECK (source IN ('planner', 'user_request', 'auto_evolve', 'migration')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Indexes for common access patterns
CREATE INDEX IF NOT EXISTS idx_document_library_user
    ON document_library(user_id);
CREATE INDEX IF NOT EXISTS idx_document_library_user_category
    ON document_library(user_id, doc_category);
CREATE INDEX IF NOT EXISTS idx_document_library_application
    ON document_library(application_id) WHERE application_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_document_library_user_type_category
    ON document_library(user_id, doc_type, doc_category);

-- RLS: users can only access their own documents
ALTER TABLE document_library ENABLE ROW LEVEL SECURITY;

CREATE POLICY document_library_user_select ON document_library
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY document_library_service_all ON document_library
    FOR ALL USING (auth.role() = 'service_role');


-- ── 2. Update trigger for updated_at ─────────────────────────────────
CREATE OR REPLACE FUNCTION update_document_library_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_document_library_updated_at
    BEFORE UPDATE ON document_library
    FOR EACH ROW
    EXECUTE FUNCTION update_document_library_timestamp();


-- ── 3. Add generation_plan column to generation_jobs ─────────────────
-- Stores the planner's decision about what to generate
ALTER TABLE generation_jobs
    ADD COLUMN IF NOT EXISTS generation_plan jsonb DEFAULT NULL;


-- ── 4. Realtime subscription for document_library ────────────────────
-- Enables frontend to subscribe to document status changes
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND tablename = 'document_library'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE document_library;
    END IF;
END $$;
