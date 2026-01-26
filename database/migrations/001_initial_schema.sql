-- HireStack AI - Initial Database Schema
-- Run this in your Supabase SQL Editor

-- Enable pgvector extension for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table (extends Supabase Auth)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    is_premium BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Users can only access their own data
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

-- Profiles table (parsed resume data)
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255),
    title VARCHAR(255),
    summary TEXT,
    raw_resume_text TEXT,
    file_url TEXT,
    file_type VARCHAR(50),
    parsed_data JSONB,
    contact_info JSONB,
    skills JSONB,
    experience JSONB,
    education JSONB,
    certifications JSONB,
    languages JSONB,
    projects JSONB,
    achievements JSONB,
    embedding vector(1536),
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own profiles" ON profiles
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_profiles_user_id ON profiles(user_id);
CREATE INDEX idx_profiles_is_primary ON profiles(user_id, is_primary);

-- Job Descriptions table
CREATE TABLE IF NOT EXISTS job_descriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    location VARCHAR(255),
    job_type VARCHAR(50),
    experience_level VARCHAR(50),
    salary_range VARCHAR(100),
    description TEXT NOT NULL,
    raw_text TEXT,
    parsed_data JSONB,
    required_skills JSONB,
    preferred_skills JSONB,
    requirements JSONB,
    responsibilities JSONB,
    benefits JSONB,
    company_info JSONB,
    embedding vector(1536),
    source_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE job_descriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own jobs" ON job_descriptions
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_job_descriptions_user_id ON job_descriptions(user_id);

-- Benchmarks table (ideal candidate)
CREATE TABLE IF NOT EXISTS benchmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_description_id UUID NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    ideal_profile JSONB,
    ideal_skills JSONB,
    ideal_experience JSONB,
    ideal_education JSONB,
    ideal_certifications JSONB,
    ideal_cv TEXT,
    ideal_cover_letter TEXT,
    ideal_portfolio JSONB,
    ideal_case_studies JSONB,
    ideal_action_plan JSONB,
    ideal_proposals JSONB,
    compatibility_criteria JSONB,
    scoring_weights JSONB,
    version INTEGER DEFAULT 1,
    status VARCHAR(50) DEFAULT 'generated',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE benchmarks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view benchmarks for own jobs" ON benchmarks
    FOR ALL USING (
        job_description_id IN (
            SELECT id FROM job_descriptions WHERE user_id = auth.uid()
        )
    );

CREATE INDEX idx_benchmarks_job_id ON benchmarks(job_description_id);

-- Gap Reports table
CREATE TABLE IF NOT EXISTS gap_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    benchmark_id UUID NOT NULL REFERENCES benchmarks(id) ON DELETE CASCADE,
    compatibility_score INTEGER DEFAULT 0,
    skill_score INTEGER DEFAULT 0,
    experience_score INTEGER DEFAULT 0,
    education_score INTEGER DEFAULT 0,
    certification_score INTEGER DEFAULT 0,
    project_score INTEGER DEFAULT 0,
    skill_gaps JSONB,
    experience_gaps JSONB,
    education_gaps JSONB,
    certification_gaps JSONB,
    project_gaps JSONB,
    strengths JSONB,
    recommendations JSONB,
    priority_actions JSONB,
    summary JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE gap_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own gap reports" ON gap_reports
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_gap_reports_user_id ON gap_reports(user_id);
CREATE INDEX idx_gap_reports_profile_id ON gap_reports(profile_id);
CREATE INDEX idx_gap_reports_benchmark_id ON gap_reports(benchmark_id);

-- Roadmaps table
CREATE TABLE IF NOT EXISTS roadmaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gap_report_id UUID NOT NULL REFERENCES gap_reports(id) ON DELETE CASCADE,
    title VARCHAR(255) DEFAULT 'Career Roadmap',
    description TEXT,
    learning_path JSONB,
    milestones JSONB,
    timeline JSONB,
    resources JSONB,
    skill_development JSONB,
    certification_path JSONB,
    experience_recommendations JSONB,
    action_items JSONB,
    progress JSONB,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE roadmaps ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own roadmaps" ON roadmaps
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_roadmaps_user_id ON roadmaps(user_id);

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    roadmap_id UUID REFERENCES roadmaps(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    summary TEXT,
    tech_stack JSONB,
    difficulty VARCHAR(50),
    estimated_duration VARCHAR(100),
    implementation_guide JSONB,
    milestones JSONB,
    features JSONB,
    skills_developed JSONB,
    learning_outcomes JSONB,
    resources JSONB,
    "references" JSONB,
    status VARCHAR(50) DEFAULT 'suggested',
    progress INTEGER DEFAULT 0,
    repo_url TEXT,
    demo_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own projects" ON projects
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_projects_user_id ON projects(user_id);

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    structured_content JSONB,
    metadata JSONB,
    target_job_id UUID,
    target_company VARCHAR(255),
    version INTEGER DEFAULT 1,
    parent_id UUID,
    template_id VARCHAR(100),
    status VARCHAR(50) DEFAULT 'draft',
    is_benchmark BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own documents" ON documents
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_type ON documents(document_type);

-- Exports table
CREATE TABLE IF NOT EXISTS exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_ids UUID[] NOT NULL,
    format VARCHAR(20) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_url TEXT,
    file_size INTEGER,
    options JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

ALTER TABLE exports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own exports" ON exports
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_exports_user_id ON exports(user_id);

-- Analytics table
CREATE TABLE IF NOT EXISTS analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB,
    session_id VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    entity_type VARCHAR(50),
    entity_id UUID,
    duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE analytics ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own analytics" ON analytics
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own analytics" ON analytics
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE INDEX idx_analytics_user_id ON analytics(user_id);
CREATE INDEX idx_analytics_event_type ON analytics(event_type);
CREATE INDEX idx_analytics_created_at ON analytics(created_at);

-- Function to handle user creation from auth
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email, full_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.email,
        NEW.raw_user_meta_data->>'full_name',
        NEW.raw_user_meta_data->>'avatar_url'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to auto-create user on auth signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_job_descriptions_updated_at BEFORE UPDATE ON job_descriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_benchmarks_updated_at BEFORE UPDATE ON benchmarks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_roadmaps_updated_at BEFORE UPDATE ON roadmaps
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
