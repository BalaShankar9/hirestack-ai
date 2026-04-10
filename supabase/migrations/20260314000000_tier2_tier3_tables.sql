-- Tier 2+3 feature tables

-- ATS Scans
CREATE TABLE IF NOT EXISTS ats_scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
    document_content TEXT NOT NULL,
    jd_text TEXT,
    overall_score INTEGER,
    scan_result JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE ats_scans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own ats scans" ON ats_scans FOR ALL USING (auth.uid() = user_id);
CREATE INDEX idx_ats_scans_user ON ats_scans(user_id);

-- Interview Sessions
CREATE TABLE IF NOT EXISTS interview_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
    job_title VARCHAR(255),
    questions JSONB,
    answers JSONB,
    evaluation JSONB,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

ALTER TABLE interview_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own interview sessions" ON interview_sessions FOR ALL USING (auth.uid() = user_id);
CREATE INDEX idx_interview_sessions_user ON interview_sessions(user_id);

-- Document Variants (A/B Lab)
CREATE TABLE IF NOT EXISTS doc_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
    document_type VARCHAR(50) NOT NULL,
    tone VARCHAR(20) NOT NULL DEFAULT 'balanced',
    content_html TEXT,
    scores JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE doc_variants ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own doc variants" ON doc_variants FOR ALL USING (auth.uid() = user_id);
CREATE INDEX idx_doc_variants_user ON doc_variants(user_id);

-- Learning Challenges (Daily Learn)
CREATE TABLE IF NOT EXISTS learning_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic VARCHAR(255) NOT NULL,
    difficulty VARCHAR(20) DEFAULT 'intermediate',
    challenge JSONB NOT NULL,
    user_answer TEXT,
    evaluation JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE learning_challenges ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own learning challenges" ON learning_challenges FOR ALL USING (auth.uid() = user_id);
CREATE INDEX idx_learning_challenges_user ON learning_challenges(user_id);

-- Review Comments (Salary Coach / document reviews)
CREATE TABLE IF NOT EXISTS review_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE review_comments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own review comments" ON review_comments FOR ALL USING (auth.uid() = user_id);
CREATE INDEX idx_review_comments_document ON review_comments(document_id);
