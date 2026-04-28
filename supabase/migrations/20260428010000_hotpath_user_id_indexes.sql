-- S2-F4: hot-path indexes flagged by the index audit.
--
-- audit_logs.user_id and api_usage.user_id are queried by every
-- per-user audit / billing endpoint but neither column had an
-- index. Existing indexes only covered the org / api_key / time
-- dimensions. With prod data growing past a few thousand rows
-- per day each, the missing indexes turn O(log n) lookups into
-- O(n) sequential scans.
--
-- Both are simple b-tree indexes on a UUID column. We do not use
-- CREATE INDEX CONCURRENTLY because Supabase wraps each migration
-- in a transaction and CONCURRENTLY is incompatible with that.
-- The tables are small enough today that a brief table lock
-- during creation is acceptable.
--
-- Idempotent: IF NOT EXISTS makes re-runs safe.

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id
    ON public.audit_logs (user_id);

CREATE INDEX IF NOT EXISTS idx_api_usage_user_id
    ON public.api_usage (user_id);
