-- HireStack AI — PR m6-pr19: pgvector embeddings for AIM sources.
--
-- Enables semantic search over the assignment-scoped source library so
-- the AIM reviewer (and future RAG paths) can pull relevant
-- evidence/quotes for a given section without paging the entire
-- library through the LLM.
--
-- Schema additions:
--   • pgvector extension (idempotent)
--   • aim_sources.embedding vector(1536)        — OpenAI text-embedding-3-small
--   • aim_sources.embedding_model varchar(64)   — provenance for re-embed waves
--   • aim_sources.embedded_at timestamptz       — when the embedding was written
--   • IVFFLAT index for cosine similarity search
--
-- The column is nullable so existing rows are valid. Backfill happens
-- asynchronously via the `aim_source_embed_consumer` worker behind the
-- `ff_aim_rag` flag.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE aim_sources
    ADD COLUMN IF NOT EXISTS embedding vector(1536),
    ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(64),
    ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMP WITH TIME ZONE;

-- IVFFLAT requires the table to have data before the planner picks the
-- index. lists=100 is a sane default for the expected single-org-scale
-- ranges we see today (1k–50k sources/org); revisit when an org grows
-- past 250k rows.
CREATE INDEX IF NOT EXISTS idx_aim_sources_embedding_cosine
    ON aim_sources
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Helper: nearest-neighbour search scoped to an assignment. Used by the
-- ai_engine RAG retriever via supabase RPC. Returns the top-k matches
-- with cosine distance (lower = closer).
CREATE OR REPLACE FUNCTION aim_sources_match(
    p_assignment_id UUID,
    p_query_embedding vector(1536),
    p_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    title VARCHAR(500),
    extracted_summary TEXT,
    relevant_quotes JSONB,
    reliability_tier VARCHAR(20),
    distance FLOAT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        s.id,
        s.title,
        s.extracted_summary,
        s.relevant_quotes,
        s.reliability_tier,
        (s.embedding <=> p_query_embedding) AS distance
    FROM aim_sources s
    WHERE s.assignment_id = p_assignment_id
      AND s.embedding IS NOT NULL
    ORDER BY s.embedding <=> p_query_embedding
    LIMIT GREATEST(1, LEAST(p_limit, 50));
$$;

COMMENT ON COLUMN aim_sources.embedding IS
    'OpenAI text-embedding-3-small (1536 dims) of title + extracted_summary.';
COMMENT ON FUNCTION aim_sources_match IS
    'Nearest-neighbour search over aim_sources within a single assignment. RAG retrieval scope. (PR m6-pr19)';
