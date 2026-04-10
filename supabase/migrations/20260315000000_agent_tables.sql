-- Agent Memory: per-user learning across pipeline runs
CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_type VARCHAR(50) NOT NULL,
    memory_key VARCHAR(255) NOT NULL,
    memory_value JSONB NOT NULL,
    relevance_score NUMERIC(3,2) DEFAULT 1.0,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, agent_type, memory_key)
);

CREATE INDEX idx_agent_memory_user ON agent_memory(user_id, agent_type);

-- Agent Traces: full pipeline observability
CREATE TABLE IF NOT EXISTS agent_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pipeline_name VARCHAR(100) NOT NULL,
    stages JSONB NOT NULL,
    total_latency_ms INTEGER NOT NULL,
    iterations_used INTEGER DEFAULT 0,
    quality_scores JSONB,
    fact_check_flags JSONB,
    status VARCHAR(20) DEFAULT 'completed',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_traces_user ON agent_traces(user_id);
CREATE INDEX idx_agent_traces_pipeline ON agent_traces(pipeline_name);

-- RLS policies
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_traces ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own agent memory"
    ON agent_memory FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "Users can view own agent traces"
    ON agent_traces FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can insert agent traces"
    ON agent_traces FOR INSERT
    WITH CHECK (true);
