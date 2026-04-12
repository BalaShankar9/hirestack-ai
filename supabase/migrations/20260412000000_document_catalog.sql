-- Document Type Catalog: platform-wide growing knowledge base of application document types
-- ═══════════════════════════════════════════════════════════════════════════════════════════

-- ── 1. Global document type catalog (append-only, platform-wide) ─────
CREATE TABLE IF NOT EXISTS document_type_catalog (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key             text UNIQUE NOT NULL,
    label           text NOT NULL,
    description     text NOT NULL DEFAULT '',
    category        text NOT NULL DEFAULT 'professional'
                    CHECK (category IN ('core', 'professional', 'academic', 'creative', 'executive', 'compliance', 'technical')),
    generatable     boolean NOT NULL DEFAULT false,
    seen_count      integer NOT NULL DEFAULT 1,
    source_context  text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_type_catalog_key
    ON document_type_catalog(key);
CREATE INDEX IF NOT EXISTS idx_document_type_catalog_category
    ON document_type_catalog(category);

-- Platform-wide read access, service-role writes
ALTER TABLE document_type_catalog ENABLE ROW LEVEL SECURITY;

CREATE POLICY document_type_catalog_read ON document_type_catalog
    FOR SELECT USING (true);

CREATE POLICY document_type_catalog_service_write ON document_type_catalog
    FOR ALL USING (auth.role() = 'service_role');


-- ── 2. Document observations (per-JD sighting evidence) ─────────────
CREATE TABLE IF NOT EXISTS document_observations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    catalog_entry_id    uuid NOT NULL REFERENCES document_type_catalog(id) ON DELETE CASCADE,
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id      uuid REFERENCES applications(id) ON DELETE SET NULL,
    job_title           text NOT NULL DEFAULT '',
    industry            text NOT NULL DEFAULT '',
    job_level           text NOT NULL DEFAULT '',
    reason              text NOT NULL DEFAULT '',
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_observations_catalog
    ON document_observations(catalog_entry_id);
CREATE INDEX IF NOT EXISTS idx_document_observations_user
    ON document_observations(user_id);

ALTER TABLE document_observations ENABLE ROW LEVEL SECURITY;

CREATE POLICY document_observations_read ON document_observations
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY document_observations_service_write ON document_observations
    FOR ALL USING (auth.role() = 'service_role');


-- ── 3. Add doc_pack_plan column to applications ─────────────────────
ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS doc_pack_plan JSONB;


-- ── 4. Seed the initial catalog ─────────────────────────────────────
INSERT INTO document_type_catalog (key, label, description, category, generatable, seen_count, source_context) VALUES
    -- Core documents (always generated)
    ('cv', 'Tailored CV', 'Your resume tailored and optimized for the specific job description', 'core', true, 100, 'Universal requirement for all job applications'),
    ('cover_letter', 'Cover Letter', 'Compelling narrative connecting your experience to the role', 'core', true, 100, 'Universal requirement for all job applications'),
    ('personal_statement', 'Personal Statement', 'Authentic career narrative revealing the person behind the resume', 'core', true, 80, 'Standard for most professional applications'),
    ('portfolio', 'Portfolio & Evidence', 'Showcase of projects presented as mini case studies with impact', 'core', true, 70, 'Standard for technical and creative roles'),

    -- Professional documents
    ('executive_summary', 'Executive Summary', 'Concise one-page overview of qualifications and value proposition', 'executive', true, 0, 'Common for senior and executive-level applications'),
    ('elevator_pitch', 'Elevator Pitch', 'Brief compelling pitch for networking and quick introductions', 'professional', true, 0, 'Useful for networking events and recruiter outreach'),
    ('references_list', 'References List', 'Formatted professional references with contact details', 'professional', true, 0, 'Often requested after initial screening'),
    ('motivation_letter', 'Motivation Letter', 'Deeper exploration of career motivation and role alignment', 'professional', true, 0, 'Common in European and international applications'),
    ('recommendation_letter_template', 'Recommendation Letter Template', 'Draft template for recommenders to customize', 'professional', true, 0, 'Helpful when requesting recommendations'),
    ('ninety_day_plan', '90-Day Plan', 'Strategic onboarding plan showing immediate value delivery', 'executive', true, 0, 'Impressive for senior roles; shows strategic thinking'),
    ('values_statement', 'Values Statement', 'Articulation of professional values and ethical framework', 'professional', true, 0, 'Requested by mission-driven organizations'),
    ('leadership_philosophy', 'Leadership Philosophy', 'Framework describing leadership style and management approach', 'executive', true, 0, 'Common for management and director-level roles'),

    -- Academic documents
    ('research_statement', 'Research Statement', 'Overview of research interests, methodology, and future directions', 'academic', true, 0, 'Required for academic and research positions'),
    ('teaching_philosophy', 'Teaching Philosophy', 'Statement of teaching approach, methods, and educational values', 'academic', true, 0, 'Required for academic teaching positions'),
    ('publications_list', 'Publications List', 'Formatted list of academic publications and citations', 'academic', true, 0, 'Required for academic and research positions'),
    ('thesis_abstract', 'Thesis Abstract', 'Concise summary of thesis research for non-specialist audiences', 'academic', true, 0, 'Useful for recent graduates with thesis work'),
    ('grant_proposal', 'Grant Proposal', 'Structured proposal for research funding applications', 'academic', true, 0, 'Required for research-funded positions'),

    -- Compliance / Government documents
    ('selection_criteria', 'Selection Criteria Response', 'Structured STAR-format response to government selection criteria', 'compliance', true, 0, 'Required for government and public sector applications'),
    ('diversity_statement', 'Diversity Statement', 'Commitment to diversity, equity, and inclusion in professional practice', 'compliance', true, 0, 'Common for academic and government roles'),
    ('safety_statement', 'Safety Statement', 'Professional approach to workplace safety and compliance', 'compliance', true, 0, 'Required for roles with safety responsibilities'),
    ('equity_statement', 'Equity Statement', 'Framework for advancing equity in professional context', 'compliance', true, 0, 'Common for academic and public sector roles'),
    ('conflict_of_interest_declaration', 'Conflict of Interest Declaration', 'Transparent disclosure of potential conflicts', 'compliance', true, 0, 'Required for senior public sector and board roles'),
    ('community_engagement_statement', 'Community Engagement Statement', 'Description of community involvement and outreach activities', 'compliance', true, 0, 'Common for public sector and nonprofit roles'),

    -- Technical documents
    ('technical_assessment', 'Technical Assessment', 'Demonstration of technical knowledge relevant to the role', 'technical', true, 0, 'Common for technical and engineering roles'),
    ('code_samples', 'Code Samples', 'Curated examples of code quality and problem-solving approach', 'technical', true, 0, 'Common for software engineering roles'),
    ('writing_sample', 'Writing Sample', 'Example of professional writing demonstrating communication skills', 'technical', true, 0, 'Required for content, communications, and policy roles'),
    ('case_study', 'Case Study', 'Detailed analysis of a professional project or business problem solved', 'technical', true, 0, 'Common for consulting and strategy roles'),

    -- Creative / Portfolio documents
    ('design_portfolio', 'Design Portfolio', 'Visual showcase of design work with process documentation', 'creative', true, 0, 'Required for design and creative roles'),
    ('clinical_portfolio', 'Clinical Portfolio', 'Documentation of clinical experience and patient care competencies', 'creative', true, 0, 'Required for healthcare and clinical positions'),
    ('speaker_bio', 'Speaker Bio', 'Professional biography for speaking engagements and conferences', 'creative', true, 0, 'Useful for thought leaders and conference speakers'),
    ('media_kit', 'Media Kit', 'Press-ready materials including bio, photos, and key achievements', 'creative', true, 0, 'Useful for public-facing and media roles'),
    ('consulting_deck', 'Consulting Deck', 'Presentation-style overview of expertise and methodology', 'executive', true, 0, 'Common for consulting and advisory roles'),
    ('board_presentation', 'Board Presentation', 'Executive-level presentation of qualifications for board roles', 'executive', true, 0, 'Required for board member and advisory positions'),
    ('professional_development_plan', 'Professional Development Plan', 'Structured plan for ongoing skill development and career growth', 'professional', true, 0, 'Shows commitment to continuous improvement')

ON CONFLICT (key) DO NOTHING;


-- ── 5. Atomic increment function for seen_count ─────────────────────
CREATE OR REPLACE FUNCTION increment_catalog_seen_count(p_key text)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
AS $$
    UPDATE document_type_catalog
    SET seen_count = seen_count + 1,
        updated_at = now()
    WHERE key = p_key;
$$;

-- Batch version: increment seen_count for multiple keys in one call
CREATE OR REPLACE FUNCTION increment_catalog_seen_count_batch(p_keys text[])
RETURNS void
LANGUAGE sql
SECURITY DEFINER
AS $$
    UPDATE document_type_catalog
    SET seen_count = seen_count + 1,
        updated_at = now()
    WHERE key = ANY(p_keys);
$$;
