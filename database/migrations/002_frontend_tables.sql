-- HireStack AI - Frontend-driven tables + schema fixes
-- Run this in Supabase SQL Editor AFTER 001_initial_schema.sql

-- ─── Fix missing columns on existing tables ─────────────────────────────────

-- benchmarks: services store user_id for ownership queries
ALTER TABLE benchmarks ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

-- gap_reports: services set a status column
ALTER TABLE gap_reports ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'completed';
ALTER TABLE gap_reports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- documents: service stores doc_metadata (001 used "metadata")
ALTER TABLE documents RENAME COLUMN metadata TO doc_metadata;

-- gap_reports updated_at trigger
CREATE TRIGGER update_gap_reports_updated_at BEFORE UPDATE ON gap_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ─── Applications table (frontend workspace model) ──────────────────────────

CREATE TABLE IF NOT EXISTS applications (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title             VARCHAR(255) NOT NULL DEFAULT '',
    status            VARCHAR(20) DEFAULT 'draft',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    -- Confirmed facts (JSONB: { jobTitle, company, jdText, jdQuality, resume })
    confirmed_facts   JSONB,

    -- Whether user has locked/confirmed facts
    facts_locked      BOOLEAN DEFAULT FALSE,

    -- Module statuses (JSONB: { benchmark: { status, error, updatedAt }, ... })
    modules           JSONB NOT NULL DEFAULT '{}',

    -- Scores snapshot (JSONB: { benchmark, gaps, cv, coverLetter, overall })
    scores            JSONB,

    -- AI-generated module outputs
    benchmark         JSONB,
    gaps              JSONB,
    learning_plan     JSONB,

    -- Document HTML
    cv_html           TEXT,
    cover_letter_html TEXT,

    -- Scorecard
    scorecard         JSONB,

    -- Version history (JSONB arrays)
    cv_versions       JSONB DEFAULT '[]',
    cl_versions       JSONB DEFAULT '[]'
);

ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own applications" ON applications
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_applications_user_id ON applications(user_id);
CREATE INDEX idx_applications_updated_at ON applications(updated_at DESC);

CREATE TRIGGER update_applications_updated_at BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ─── Evidence table (proof items: links, files) ─────────────────────────────

CREATE TABLE IF NOT EXISTS evidence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id  UUID REFERENCES applications(id) ON DELETE SET NULL,
    kind            VARCHAR(10) NOT NULL DEFAULT 'link',
    type            VARCHAR(20) DEFAULT 'other',
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    url             TEXT,
    storage_url     TEXT,
    file_url        TEXT,
    file_name       VARCHAR(255),
    mime_type       VARCHAR(100),
    tags            TEXT[] DEFAULT '{}',
    skills          TEXT[] DEFAULT '{}',
    tools           TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE evidence ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own evidence" ON evidence
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_evidence_user_id ON evidence(user_id);

CREATE TRIGGER update_evidence_updated_at BEFORE UPDATE ON evidence
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ─── Tasks table (action queue items) ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,  -- custom composite IDs like "appId__gap-proof-keyword"
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id  UUID REFERENCES applications(id) ON DELETE CASCADE,
    source          VARCHAR(20),
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    priority        VARCHAR(10) DEFAULT 'medium',
    status          VARCHAR(20) DEFAULT 'todo',
    due_date        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    tags            TEXT[] DEFAULT '{}'
);

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own tasks" ON tasks
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_tasks_user_id ON tasks(user_id);
CREATE INDEX idx_tasks_application_id ON tasks(application_id);

-- ─── Events table (analytics events from frontend) ──────────────────────────

CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    event           VARCHAR(100) NOT NULL,
    application_id  UUID REFERENCES applications(id) ON DELETE SET NULL,
    payload         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own events" ON events
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_events_user_id ON events(user_id);

-- ─── Enable Supabase Realtime for frontend tables ───────────────────────────

ALTER PUBLICATION supabase_realtime ADD TABLE applications;
ALTER PUBLICATION supabase_realtime ADD TABLE evidence;
ALTER PUBLICATION supabase_realtime ADD TABLE tasks;

-- ─── Storage buckets (create via Supabase Dashboard or SQL) ─────────────────
-- Bucket: resumes  (for resume file uploads)
-- Bucket: evidence (for evidence file uploads)
--
-- In Supabase Dashboard: Build → Storage → New Bucket
-- Or uncomment:
-- INSERT INTO storage.buckets (id, name, public) VALUES ('resumes', 'resumes', false);
-- INSERT INTO storage.buckets (id, name, public) VALUES ('evidence', 'evidence', false);
--
-- Storage RLS policies (allow authenticated users to manage their own files):
-- CREATE POLICY "Users can upload resumes" ON storage.objects FOR INSERT
--     WITH CHECK (bucket_id = 'resumes' AND auth.role() = 'authenticated');
-- CREATE POLICY "Users can read own resumes" ON storage.objects FOR SELECT
--     USING (bucket_id = 'resumes' AND auth.role() = 'authenticated');
-- CREATE POLICY "Users can upload evidence" ON storage.objects FOR INSERT
--     WITH CHECK (bucket_id = 'evidence' AND auth.role() = 'authenticated');
-- CREATE POLICY "Users can read own evidence" ON storage.objects FOR SELECT
--     USING (bucket_id = 'evidence' AND auth.role() = 'authenticated');
