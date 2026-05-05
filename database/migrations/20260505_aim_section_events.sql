-- HireStack AI — AIM section event log
--
-- Persists every streaming event emitted during AIM section generation so:
--   * the live agent dock can rehydrate after reconnect,
--   * `?since=` resume is supported by sequence number,
--   * dedup-on-event_id works on the client.
--
-- Mirrors the shape of generation_job_events but scoped to aim_sections.
-- RLS: only the owning user can read; service role writes via the backend.

CREATE TABLE IF NOT EXISTS aim_section_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    section_id UUID NOT NULL REFERENCES aim_sections(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,        -- agent_status | retry | complete | error
    agent VARCHAR(50) DEFAULT '',           -- parser | recon | writer | reviewer | aim
    status VARCHAR(30) DEFAULT '',          -- running | completed | failed | retrying
    message TEXT DEFAULT '',
    progress INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE aim_section_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "aim_section_events_owner_read" ON aim_section_events;
CREATE POLICY "aim_section_events_owner_read" ON aim_section_events
    FOR SELECT USING (auth.uid() = user_id);

-- Service-role writes only. (No public INSERT/UPDATE policy by design.)

CREATE INDEX IF NOT EXISTS idx_aim_section_events_section_seq
    ON aim_section_events(section_id, sequence);
CREATE INDEX IF NOT EXISTS idx_aim_section_events_user_recent
    ON aim_section_events(user_id, created_at DESC);
