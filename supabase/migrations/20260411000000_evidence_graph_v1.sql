-- Evidence Graph v1: User-scoped canonical evidence layer
-- ════════════════════════════════════════════════════════
-- Promotes job-scoped evidence ledger items into user-level
-- canonical facts, enabling cross-job consistency checking,
-- contradiction detection, and adaptive planning.

-- ── 1. Canonical evidence nodes ──────────────────────────
-- Immutable facts that span all of a user's jobs.
-- Each node represents a single canonical piece of evidence
-- (e.g., "5 years Python experience at Acme Corp").
CREATE TABLE IF NOT EXISTS user_evidence_nodes (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_text  text NOT NULL,
    tier            text NOT NULL CHECK (tier IN ('verbatim', 'derived', 'inferred', 'user_stated')),
    source          text NOT NULL CHECK (source IN ('profile', 'jd', 'company', 'tool', 'memory')),
    source_field    text NOT NULL DEFAULT '',
    confidence      real NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    first_seen_job_id uuid,
    metadata        jsonb DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_evidence_nodes_user
    ON user_evidence_nodes(user_id);
CREATE INDEX IF NOT EXISTS idx_user_evidence_nodes_tier
    ON user_evidence_nodes(user_id, tier);

ALTER TABLE user_evidence_nodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_evidence_nodes_owner ON user_evidence_nodes
    FOR ALL USING (auth.uid() = user_id);


-- ── 2. Evidence aliases ──────────────────────────────────
-- Maps job-scoped ledger items to canonical nodes via fuzzy matching.
-- Example: "Sr. Software Engineer" and "Senior Dev" → same canonical node.
CREATE TABLE IF NOT EXISTS user_evidence_aliases (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_node_id   uuid NOT NULL REFERENCES user_evidence_nodes(id) ON DELETE CASCADE,
    alias_text          text NOT NULL,
    similarity_score    real NOT NULL DEFAULT 1.0 CHECK (similarity_score >= 0 AND similarity_score <= 1),
    source_job_id       uuid,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_evidence_aliases_node
    ON user_evidence_aliases(canonical_node_id);
CREATE INDEX IF NOT EXISTS idx_user_evidence_aliases_user
    ON user_evidence_aliases(user_id);

ALTER TABLE user_evidence_aliases ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_evidence_aliases_owner ON user_evidence_aliases
    FOR ALL USING (auth.uid() = user_id);


-- ── 3. Claim edges ───────────────────────────────────────
-- Relationships between evidence nodes.
-- "supports" = node A corroborates node B.
-- "contradicts" = node A conflicts with node B.
-- "supersedes" = node A is a newer version of node B.
CREATE TABLE IF NOT EXISTS user_claim_edges (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_node_id      uuid NOT NULL REFERENCES user_evidence_nodes(id) ON DELETE CASCADE,
    target_node_id      uuid NOT NULL REFERENCES user_evidence_nodes(id) ON DELETE CASCADE,
    relationship        text NOT NULL CHECK (relationship IN ('supports', 'contradicts', 'supersedes')),
    weight              real NOT NULL DEFAULT 1.0 CHECK (weight >= 0 AND weight <= 1),
    metadata            jsonb DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT no_self_edge CHECK (source_node_id != target_node_id)
);

CREATE INDEX IF NOT EXISTS idx_user_claim_edges_source
    ON user_claim_edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_user_claim_edges_target
    ON user_claim_edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_user_claim_edges_user
    ON user_claim_edges(user_id);

ALTER TABLE user_claim_edges ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_claim_edges_owner ON user_claim_edges
    FOR ALL USING (auth.uid() = user_id);


-- ── 4. Detected contradictions ───────────────────────────
-- When the canonicalization engine finds conflicting evidence,
-- it records it here for user resolution and planner scoring.
CREATE TABLE IF NOT EXISTS evidence_contradictions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    node_a_id           uuid NOT NULL REFERENCES user_evidence_nodes(id) ON DELETE CASCADE,
    node_b_id           uuid NOT NULL REFERENCES user_evidence_nodes(id) ON DELETE CASCADE,
    contradiction_type  text NOT NULL CHECK (contradiction_type IN (
        'company_name', 'title_conflict', 'date_overlap',
        'certification_conflict', 'metric_conflict'
    )),
    severity            text NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    description         text NOT NULL DEFAULT '',
    resolved_at         timestamptz,
    resolution_note     text,
    metadata            jsonb DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT no_self_contradiction CHECK (node_a_id != node_b_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_contradictions_user
    ON evidence_contradictions(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_contradictions_unresolved
    ON evidence_contradictions(user_id) WHERE resolved_at IS NULL;

ALTER TABLE evidence_contradictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY evidence_contradictions_owner ON evidence_contradictions
    FOR ALL USING (auth.uid() = user_id);


-- ── 5. Pipeline plans (for adaptive planner audit trail) ─
-- Persists the PlanArtifact so we can replay decisions.
CREATE TABLE IF NOT EXISTS pipeline_plans (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_id              uuid,
    application_id      uuid,
    plan_artifact       jsonb NOT NULL DEFAULT '{}'::jsonb,
    risk_mode           text NOT NULL DEFAULT 'balanced',
    jd_quality_score    integer,
    profile_quality_score integer,
    evidence_strength_score integer,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_plans_user
    ON pipeline_plans(user_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_plans_job
    ON pipeline_plans(job_id) WHERE job_id IS NOT NULL;

ALTER TABLE pipeline_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY pipeline_plans_owner ON pipeline_plans
    FOR ALL USING (auth.uid() = user_id);
