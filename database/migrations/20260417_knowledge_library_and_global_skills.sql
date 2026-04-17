-- ============================================================================
-- Knowledge Library + Global Skills & Gaps + Global Learning Center
-- 2026-04-17
-- ============================================================================

-- ── 1. Knowledge Library Resources ──────────────────────────────────────────
-- Platform-wide curated learning resources, guides, templates, books, etc.
CREATE TABLE IF NOT EXISTS knowledge_resources (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title           text NOT NULL,
    description     text,
    resource_type   text NOT NULL CHECK (resource_type IN (
        'guide', 'book', 'template', 'video', 'course', 'article',
        'cheatsheet', 'reference', 'tutorial', 'tool', 'podcast'
    )),
    category        text NOT NULL CHECK (category IN (
        'resume_writing', 'interview_prep', 'skill_development',
        'career_strategy', 'networking', 'salary_negotiation',
        'industry_knowledge', 'soft_skills', 'technical_skills',
        'job_search', 'personal_branding', 'general'
    )),
    url             text,
    content_html    text,
    provider        text,           -- e.g. "HireStack", "freeCodeCamp", "MIT OCW"
    is_free         boolean NOT NULL DEFAULT true,
    difficulty      text CHECK (difficulty IN ('beginner', 'intermediate', 'advanced')),
    estimated_time  text,           -- e.g. "30 min", "2 hours", "6 weeks"
    skills          text[] DEFAULT '{}',  -- skills this resource helps develop
    tags            text[] DEFAULT '{}',
    cover_image_url text,
    sort_order      int DEFAULT 0,
    is_featured     boolean DEFAULT false,
    is_published    boolean DEFAULT true,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_resources_type ON knowledge_resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_resources_category ON knowledge_resources(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_resources_skills ON knowledge_resources USING gin(skills);
CREATE INDEX IF NOT EXISTS idx_knowledge_resources_featured ON knowledge_resources(is_featured) WHERE is_featured = true;

-- ── 2. User bookmarks / progress on knowledge resources ─────────────────────
CREATE TABLE IF NOT EXISTS user_knowledge_progress (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    resource_id     uuid NOT NULL REFERENCES knowledge_resources(id) ON DELETE CASCADE,
    status          text NOT NULL DEFAULT 'saved' CHECK (status IN ('saved', 'in_progress', 'completed')),
    progress_pct    int DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    notes           text,
    rating          int CHECK (rating BETWEEN 1 AND 5),
    completed_at    timestamptz,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    UNIQUE(user_id, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_user_knowledge_progress_user ON user_knowledge_progress(user_id);

-- ── 3. Global user skills (profile-wide, not per-application) ───────────────
CREATE TABLE IF NOT EXISTS user_skills (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    skill_name      text NOT NULL,
    category        text CHECK (category IN (
        'technical', 'soft_skill', 'tool', 'language', 'framework',
        'methodology', 'certification', 'domain', 'other'
    )),
    proficiency     text CHECK (proficiency IN ('beginner', 'intermediate', 'advanced', 'expert')),
    years_experience numeric(4,1),
    is_verified     boolean DEFAULT false,  -- verified via evidence, certs, etc.
    evidence_ids    uuid[] DEFAULT '{}',    -- links to evidence items
    source          text DEFAULT 'manual' CHECK (source IN ('manual', 'resume_parse', 'gap_analysis', 'learning', 'evidence')),
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    UNIQUE(user_id, skill_name)
);

CREATE INDEX IF NOT EXISTS idx_user_skills_user ON user_skills(user_id);
CREATE INDEX IF NOT EXISTS idx_user_skills_category ON user_skills(category);

-- ── 4. Global skill gaps (aggregated across all applications) ───────────────
CREATE TABLE IF NOT EXISTS user_skill_gaps (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    skill_name          text NOT NULL,
    gap_severity        text NOT NULL CHECK (gap_severity IN ('low', 'medium', 'high', 'critical')),
    current_level       text,
    target_level        text,
    frequency           int DEFAULT 1,          -- how many applications need this skill
    application_ids     uuid[] DEFAULT '{}',    -- which applications flagged this gap
    recommended_resources uuid[] DEFAULT '{}',  -- knowledge_resources IDs
    status              text DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'closed', 'dismissed')),
    priority_score      numeric(5,2) DEFAULT 0, -- computed: severity * frequency * recency
    notes               text,
    created_at          timestamptz DEFAULT now(),
    updated_at          timestamptz DEFAULT now(),
    UNIQUE(user_id, skill_name)
);

CREATE INDEX IF NOT EXISTS idx_user_skill_gaps_user ON user_skill_gaps(user_id);
CREATE INDEX IF NOT EXISTS idx_user_skill_gaps_severity ON user_skill_gaps(gap_severity);
CREATE INDEX IF NOT EXISTS idx_user_skill_gaps_status ON user_skill_gaps(status);

-- ── 5. Global learning goals (long-term career development) ─────────────────
CREATE TABLE IF NOT EXISTS user_learning_goals (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title               text NOT NULL,
    description         text,
    target_skills       text[] DEFAULT '{}',
    goal_type           text CHECK (goal_type IN (
        'skill_acquisition', 'certification', 'career_transition',
        'promotion_readiness', 'industry_knowledge', 'general'
    )),
    status              text DEFAULT 'active' CHECK (status IN ('active', 'completed', 'paused', 'archived')),
    target_date         timestamptz,
    progress_pct        int DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    linked_resource_ids uuid[] DEFAULT '{}',    -- knowledge_resources IDs
    linked_gap_ids      uuid[] DEFAULT '{}',    -- user_skill_gaps IDs
    created_at          timestamptz DEFAULT now(),
    updated_at          timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_learning_goals_user ON user_learning_goals(user_id);
CREATE INDEX IF NOT EXISTS idx_user_learning_goals_status ON user_learning_goals(status);

-- ── 6. Resource recommendations (AI-generated linkages) ─────────────────────
CREATE TABLE IF NOT EXISTS resource_recommendations (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    resource_id     uuid NOT NULL REFERENCES knowledge_resources(id) ON DELETE CASCADE,
    reason          text NOT NULL,              -- why this was recommended
    source          text NOT NULL CHECK (source IN (
        'skill_gap', 'career_goal', 'application_need', 'profile_analysis', 'trending'
    )),
    relevance_score numeric(5,2) DEFAULT 0,     -- 0-100
    linked_skill    text,                       -- which skill gap triggered this
    linked_app_id   uuid,                       -- which application triggered this
    is_dismissed    boolean DEFAULT false,
    is_completed    boolean DEFAULT false,
    created_at      timestamptz DEFAULT now(),
    UNIQUE(user_id, resource_id, source)
);

CREATE INDEX IF NOT EXISTS idx_resource_recommendations_user ON resource_recommendations(user_id);
CREATE INDEX IF NOT EXISTS idx_resource_recommendations_relevance ON resource_recommendations(relevance_score DESC);

-- ── 7. Enable RLS ───────────────────────────────────────────────────────────

ALTER TABLE knowledge_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_knowledge_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_skill_gaps ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_learning_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE resource_recommendations ENABLE ROW LEVEL SECURITY;

-- Knowledge resources: readable by all authenticated users
CREATE POLICY "knowledge_resources_read" ON knowledge_resources
    FOR SELECT TO authenticated USING (is_published = true);

-- Service role can manage all knowledge resources
CREATE POLICY "knowledge_resources_service" ON knowledge_resources
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- User-owned tables: users can only see/edit their own rows
CREATE POLICY "user_knowledge_progress_own" ON user_knowledge_progress
    FOR ALL TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_skills_own" ON user_skills
    FOR ALL TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_skill_gaps_own" ON user_skill_gaps
    FOR ALL TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_learning_goals_own" ON user_learning_goals
    FOR ALL TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "resource_recommendations_own" ON resource_recommendations
    FOR ALL TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- Service role bypass for all user tables
CREATE POLICY "user_knowledge_progress_service" ON user_knowledge_progress
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "user_skills_service" ON user_skills
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "user_skill_gaps_service" ON user_skill_gaps
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "user_learning_goals_service" ON user_learning_goals
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "resource_recommendations_service" ON resource_recommendations
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── 8. Seed featured knowledge resources ────────────────────────────────────
INSERT INTO knowledge_resources (title, description, resource_type, category, url, provider, is_free, difficulty, estimated_time, skills, tags, is_featured, sort_order) VALUES
-- Resume & CV
('The Complete Guide to ATS-Optimized Resumes', 'Learn how to write resumes that pass Applicant Tracking Systems with keyword optimization, formatting rules, and common pitfalls.', 'guide', 'resume_writing', NULL, 'HireStack', true, 'beginner', '45 min', ARRAY['resume_writing', 'ats_optimization'], ARRAY['resume', 'ats', 'job_search'], true, 1),
('Action Verb Power List for Resumes', 'A comprehensive reference of 200+ strong action verbs organized by skill category to make your resume more impactful.', 'reference', 'resume_writing', NULL, 'HireStack', true, 'beginner', '10 min', ARRAY['resume_writing'], ARRAY['resume', 'writing', 'reference'], true, 2),
('Cover Letter Templates by Industry', 'Proven cover letter frameworks for tech, finance, healthcare, marketing, and more. Includes fill-in-the-blank templates.', 'template', 'resume_writing', NULL, 'HireStack', true, 'beginner', '20 min', ARRAY['cover_letter_writing'], ARRAY['cover_letter', 'template'], true, 3),

-- Interview Preparation
('STAR Method Interview Guide', 'Master the Situation-Task-Action-Result framework for behavioral interviews. Includes 50+ example questions with model answers.', 'guide', 'interview_prep', NULL, 'HireStack', true, 'intermediate', '1 hour', ARRAY['interviewing', 'communication'], ARRAY['interview', 'behavioral', 'star_method'], true, 4),
('Technical Interview Patterns', 'Common coding patterns, system design templates, and problem-solving frameworks for technical interviews.', 'guide', 'interview_prep', NULL, 'HireStack', true, 'advanced', '3 hours', ARRAY['algorithms', 'system_design', 'problem_solving'], ARRAY['interview', 'technical', 'coding'], true, 5),
('Salary Negotiation Playbook', 'Step-by-step guide to negotiating your compensation package. Includes scripts, counter-offer strategies, and market research methods.', 'guide', 'salary_negotiation', NULL, 'HireStack', true, 'intermediate', '45 min', ARRAY['negotiation', 'salary_research'], ARRAY['salary', 'negotiation', 'compensation'], true, 6),

-- Career Strategy
('Career Transition Roadmap', 'A structured approach to changing careers: self-assessment, transferable skills mapping, networking strategies, and timeline planning.', 'guide', 'career_strategy', NULL, 'HireStack', true, 'intermediate', '2 hours', ARRAY['career_planning', 'self_assessment'], ARRAY['career_change', 'strategy', 'planning'], true, 7),
('LinkedIn Profile Optimization Checklist', 'Transform your LinkedIn profile from passive to active. Headline formulas, summary templates, and engagement tactics.', 'cheatsheet', 'personal_branding', NULL, 'HireStack', true, 'beginner', '30 min', ARRAY['personal_branding', 'networking'], ARRAY['linkedin', 'profile', 'networking'], true, 8),
('Portfolio Building for Non-Designers', 'How to create a compelling portfolio even if you are not a designer. Project showcase templates, storytelling frameworks, and hosting options.', 'guide', 'personal_branding', NULL, 'HireStack', true, 'beginner', '1 hour', ARRAY['portfolio_building', 'personal_branding'], ARRAY['portfolio', 'projects', 'showcase'], true, 9),

-- Skill Development
('Learning to Learn: Meta-Skills for Fast Skill Acquisition', 'Evidence-based techniques for learning any skill faster: spaced repetition, deliberate practice, and the Feynman technique.', 'guide', 'skill_development', NULL, 'HireStack', true, 'beginner', '45 min', ARRAY['learning_skills', 'self_improvement'], ARRAY['learning', 'meta_skills', 'productivity'], true, 10),
('Soft Skills That Win Jobs', 'The most in-demand soft skills and how to develop and demonstrate them: leadership, communication, problem-solving, adaptability.', 'guide', 'soft_skills', NULL, 'HireStack', true, 'beginner', '1 hour', ARRAY['communication', 'leadership', 'teamwork', 'problem_solving'], ARRAY['soft_skills', 'professional_development'], true, 11),
('Free Certification Paths by Industry', 'Curated list of free and affordable certifications in tech, project management, data science, marketing, and more.', 'reference', 'skill_development', NULL, 'HireStack', true, 'intermediate', '15 min', ARRAY['certifications'], ARRAY['certifications', 'free_learning', 'career_growth'], true, 12)

ON CONFLICT DO NOTHING;
