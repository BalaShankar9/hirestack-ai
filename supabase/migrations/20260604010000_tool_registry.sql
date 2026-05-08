-- HireStack AI — Tool Registry (PR m5-pr14)
-- Three tables back the dispatcher:
--   ai_tools             — catalog of callable tools (name, schemas, code id)
--   ai_agent_tool_grants — per-agent ACL: which agents may invoke which tools
--   ai_tool_invocations  — audit log of every dispatch (partitioned by month)
--
-- All tables are service-role-only writeable; readable by authenticated users
-- via grant lookups only. The dispatcher is short-circuited when the
-- ff_tool_registry feature flag is off (default), so this schema is
-- additive and ships dark.

-- ─── ai_tools ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_tools (
    name           VARCHAR(120) PRIMARY KEY,
    version        INTEGER NOT NULL DEFAULT 1,
    description    TEXT NOT NULL DEFAULT '',
    code_ref       VARCHAR(255) NOT NULL,            -- dotted path: pkg.mod:Class
    input_schema   JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_schema  JSONB NOT NULL DEFAULT '{}'::jsonb,
    timeout_ms     INTEGER NOT NULL DEFAULT 15000,
    enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_tools_enabled ON ai_tools(enabled) WHERE enabled;
ALTER TABLE ai_tools ENABLE ROW LEVEL SECURITY;
CREATE POLICY "ai_tools_read_all" ON ai_tools FOR SELECT USING (TRUE);

-- ─── ai_agent_tool_grants ─────────────────────────────────────────────
-- Wildcard agent_name '*' grants the tool to every agent.
CREATE TABLE IF NOT EXISTS ai_agent_tool_grants (
    agent_name   VARCHAR(120) NOT NULL,
    tool_name    VARCHAR(120) NOT NULL REFERENCES ai_tools(name) ON DELETE CASCADE,
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (agent_name, tool_name)
);
CREATE INDEX IF NOT EXISTS idx_ai_grants_tool ON ai_agent_tool_grants(tool_name);
ALTER TABLE ai_agent_tool_grants ENABLE ROW LEVEL SECURITY;
CREATE POLICY "ai_agent_tool_grants_read_all" ON ai_agent_tool_grants FOR SELECT USING (TRUE);

-- ─── ai_tool_invocations (partitioned by month) ───────────────────────
CREATE TABLE IF NOT EXISTS ai_tool_invocations (
    id             UUID NOT NULL DEFAULT gen_random_uuid(),
    tool_name      VARCHAR(120) NOT NULL,
    agent_name     VARCHAR(120) NOT NULL,
    org_id         UUID,
    user_id        UUID,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at   TIMESTAMPTZ,
    duration_ms    INTEGER,
    status         VARCHAR(20) NOT NULL,            -- ok | error | timeout | denied | invalid_input | invalid_output
    error_message  TEXT,
    input_hash     VARCHAR(64),
    PRIMARY KEY (id, started_at)
) PARTITION BY RANGE (started_at);

CREATE INDEX IF NOT EXISTS idx_ai_invocations_tool_started
    ON ai_tool_invocations(tool_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_invocations_status_started
    ON ai_tool_invocations(status, started_at DESC) WHERE status <> 'ok';

-- Bootstrap two months so production starts dispatch immediately.
DO $$
DECLARE
    cur DATE := date_trunc('month', NOW())::DATE;
    nxt DATE := (date_trunc('month', NOW()) + INTERVAL '1 month')::DATE;
    afr DATE := (date_trunc('month', NOW()) + INTERVAL '2 month')::DATE;
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS ai_tool_invocations_%s PARTITION OF ai_tool_invocations FOR VALUES FROM (%L) TO (%L);',
        to_char(cur, 'YYYYMM'), cur, nxt
    );
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS ai_tool_invocations_%s PARTITION OF ai_tool_invocations FOR VALUES FROM (%L) TO (%L);',
        to_char(nxt, 'YYYYMM'), nxt, afr
    );
END $$;

ALTER TABLE ai_tool_invocations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "ai_tool_invocations_read_owner" ON ai_tool_invocations
    FOR SELECT USING (auth.uid() = user_id OR user_id IS NULL);
