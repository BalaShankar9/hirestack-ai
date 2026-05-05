-- HireStack AI — Assignment Intelligence Module (AIM) — Phase 1 schema
-- Tables: aim_assignments, aim_assignment_documents, aim_assignment_analysis,
--         aim_sections, aim_section_outputs, aim_evaluations, aim_tasks, aim_jobs
-- All tables RLS-protected by user_id (auth.uid() = user_id) or via parent join.

-- ─── aim_assignments ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aim_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    course VARCHAR(255),
    academic_level VARCHAR(50),       -- ug | pg | mba | phd | other
    referencing_style VARCHAR(50),    -- harvard | apa | mla | chicago | ieee | other
    deadline TIMESTAMP WITH TIME ZONE,
    word_count INTEGER,
    status VARCHAR(30) DEFAULT 'draft', -- draft|analyzing|ready|in_progress|complete|failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE aim_assignments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_assignments_owner_all" ON aim_assignments
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_assignments_user ON aim_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_aim_assignments_status ON aim_assignments(user_id, status);

-- ─── aim_assignment_documents ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS aim_assignment_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES aim_assignments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(30) NOT NULL,        -- brief | rubric | notes | reference
    file_name VARCHAR(500),
    file_url TEXT,
    raw_text TEXT,
    parsed_data JSONB,
    parse_confidence NUMERIC(4,3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE aim_assignment_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_documents_owner_all" ON aim_assignment_documents
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_documents_assignment ON aim_assignment_documents(assignment_id);

-- ─── aim_assignment_analysis ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aim_assignment_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL UNIQUE REFERENCES aim_assignments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    directive VARCHAR(100),                   -- analyse | evaluate | discuss | critique | etc.
    parser_confidence NUMERIC(4,3),
    needs_clarification BOOLEAN DEFAULT FALSE,
    clarification_questions JSONB,            -- [{question, why}]
    structure JSONB,                          -- [{title, purpose, key_argument, word_limit, order_index}]
    rubric_breakdown JSONB,                   -- [{criterion, weight, descriptors{}}]
    expectations JSONB,                       -- {hidden_expectations[], distinction_strategy, mark_loss_patterns[]}
    recon_report JSONB,                       -- full ReconReport payload
    recon_version INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE aim_assignment_analysis ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_analysis_owner_all" ON aim_assignment_analysis
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_analysis_assignment ON aim_assignment_analysis(assignment_id);

-- ─── aim_sections ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aim_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES aim_assignments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    order_index INTEGER NOT NULL,
    word_limit INTEGER,
    purpose TEXT,
    key_argument TEXT,
    rubric_links JSONB,                       -- [criterion ids this section serves]
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE aim_sections ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_sections_owner_all" ON aim_sections
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_sections_assignment ON aim_sections(assignment_id, order_index);

-- ─── aim_section_outputs ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aim_section_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id UUID NOT NULL REFERENCES aim_sections(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    quality_score NUMERIC(5,2),               -- 0..100 weighted AIM Quality Score
    sub_scores JSONB,                         -- {directive_alignment, analytical_depth, academic_tone, originality, structure}
    reviewer_issues JSONB,                    -- ranked issue list from reviewer
    blocked_phrases JSONB,                    -- deterministic filter hits
    version INTEGER NOT NULL DEFAULT 1,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    passed_gate BOOLEAN NOT NULL DEFAULT FALSE,  -- score >= 85
    model_used VARCHAR(100),
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE aim_section_outputs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_section_outputs_owner_all" ON aim_section_outputs
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_section_outputs_section ON aim_section_outputs(section_id, version DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_aim_section_outputs_current
    ON aim_section_outputs(section_id) WHERE is_current = TRUE;

-- ─── aim_evaluations ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aim_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES aim_assignments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    predicted_grade_low INTEGER,
    predicted_grade_high INTEGER,
    band VARCHAR(50),                         -- e.g. "2:1", "B", "Distinction"
    overall_quality NUMERIC(5,2),
    per_criterion JSONB,                      -- [{criterion, score, reasoning}]
    feedback JSONB,                           -- {strengths[], weaknesses[], improvement_priorities[]}
    reasoning TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE aim_evaluations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_evaluations_owner_all" ON aim_evaluations
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_evaluations_assignment ON aim_evaluations(assignment_id, created_at DESC);

-- ─── aim_tasks (Deadline Mode) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS aim_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES aim_assignments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_name VARCHAR(500) NOT NULL,
    description TEXT,
    section_id UUID REFERENCES aim_sections(id) ON DELETE SET NULL,
    due_date DATE,
    effort_minutes INTEGER,
    status VARCHAR(20) DEFAULT 'pending',     -- pending | in_progress | done | skipped
    order_index INTEGER DEFAULT 0,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE aim_tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_tasks_owner_all" ON aim_tasks
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_tasks_assignment ON aim_tasks(assignment_id, due_date);

-- ─── aim_jobs ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aim_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES aim_assignments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind VARCHAR(40) NOT NULL,                -- analyze | generate_section | evaluate | fix | plan_tasks
    section_id UUID REFERENCES aim_sections(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending', -- pending|running|succeeded|failed|cancelled
    attempts INTEGER DEFAULT 0,
    events JSONB DEFAULT '[]'::jsonb,
    result JSONB,
    error TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE aim_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_jobs_owner_all" ON aim_jobs
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_jobs_assignment ON aim_jobs(assignment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aim_jobs_status ON aim_jobs(status, created_at);

-- ─── aim_usage (free/paid quota tracking) ───────────────────────────
CREATE TABLE IF NOT EXISTS aim_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_month DATE NOT NULL,               -- first day of month, e.g. 2026-05-01
    assignments_created INTEGER NOT NULL DEFAULT 0,
    sections_generated INTEGER NOT NULL DEFAULT 0,
    evaluations_run INTEGER NOT NULL DEFAULT 0,
    plan VARCHAR(20) NOT NULL DEFAULT 'free', -- free | paid
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, period_month)
);
ALTER TABLE aim_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_usage_owner_select" ON aim_usage
    FOR SELECT USING (auth.uid() = user_id);
