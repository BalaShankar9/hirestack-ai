-- HireStack AI — Tool Registry sandbox tier classifier (PR m7-pr29)
-- Per ADR-0033. Adds three columns to ai_tools:
--   sandbox_tier              — VARCHAR(2), one of L0/L1/L2/L3 (L3 reserved)
--   egress_allowlist          — JSONB array of allowed hostnames for L1 tools
--   requires_capability_token — BOOLEAN per-tool kill-switch from ADR-0032
--
-- Defaults match current behaviour: every existing row becomes L0, no
-- egress restrictions, no token required. Backfill is a no-op.
--
-- Expand phase only. Contract phase (drop DEFAULT 'L0' once seed.py
-- populates every row explicitly) tracked as m7-pr29b.

ALTER TABLE ai_tools
    ADD COLUMN IF NOT EXISTS sandbox_tier VARCHAR(2)
        NOT NULL DEFAULT 'L0',
    ADD COLUMN IF NOT EXISTS egress_allowlist JSONB
        NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS requires_capability_token BOOLEAN
        NOT NULL DEFAULT FALSE;

-- Constraint added separately so IF NOT EXISTS columns don't conflict with
-- the CHECK clause on re-runs.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ai_tools_sandbox_tier_check'
    ) THEN
        ALTER TABLE ai_tools
            ADD CONSTRAINT ai_tools_sandbox_tier_check
            CHECK (sandbox_tier IN ('L0', 'L1', 'L2', 'L3'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ai_tools_sandbox_tier
    ON ai_tools(sandbox_tier);

COMMENT ON COLUMN ai_tools.sandbox_tier IS
    'Isolation tier per ADR-0033. L0=in-process, L1=in-process+egress allowlist, L2=sidecar, L3=Firecracker (reserved).';
COMMENT ON COLUMN ai_tools.egress_allowlist IS
    'JSONB array of allowed hostnames (lowercase, no scheme) for L1 tools. Ignored for other tiers.';
COMMENT ON COLUMN ai_tools.requires_capability_token IS
    'Per-tool kill-switch (ADR-0032). When TRUE, dispatcher requires a valid CapabilityToken even with ff_tool_capability_tokens OFF.';
