-- HireStack AI — AIM source library foundation
-- Adds durable source/citation tables for source-backed academic work.

CREATE TABLE IF NOT EXISTS aim_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES aim_assignments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type VARCHAR(50) NOT NULL DEFAULT 'other',
    title VARCHAR(500),
    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    year INTEGER,
    publisher VARCHAR(500),
    journal VARCHAR(500),
    doi VARCHAR(255),
    url TEXT,
    access_date VARCHAR(30),
    reliability_tier VARCHAR(20) NOT NULL DEFAULT 'tier_4',
    verification_status VARCHAR(30) NOT NULL DEFAULT 'needs_metadata',
    raw_text TEXT,
    extracted_summary TEXT,
    relevant_quotes JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE aim_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_sources_owner_all" ON aim_sources
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_sources_assignment ON aim_sources(assignment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aim_sources_user_tier ON aim_sources(user_id, reliability_tier);

CREATE TABLE IF NOT EXISTS aim_source_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES aim_assignments(id) ON DELETE CASCADE,
    section_id UUID REFERENCES aim_sections(id) ON DELETE CASCADE,
    output_id UUID REFERENCES aim_section_outputs(id) ON DELETE CASCADE,
    source_id UUID REFERENCES aim_sources(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'unverified',
    citation_required BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE aim_source_claims ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_source_claims_owner_all" ON aim_source_claims
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_source_claims_assignment ON aim_source_claims(assignment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aim_source_claims_source ON aim_source_claims(source_id);

CREATE TABLE IF NOT EXISTS aim_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES aim_assignments(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES aim_sources(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    style VARCHAR(50) NOT NULL,
    in_text_citation TEXT,
    bibliography_entry TEXT,
    validation_status VARCHAR(30) NOT NULL DEFAULT 'unverified',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(source_id, style)
);

ALTER TABLE aim_citations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aim_citations_owner_all" ON aim_citations
    FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_aim_citations_assignment ON aim_citations(assignment_id, style);