-- B0.persist.idempotency: per-user dedup index on batch-imported apps.
--
-- The /api/generate/batch/commit route stores a stable
-- ``dedup_key`` (sha256 of user_id\x1fcanonical_url, 32 hex)
-- inside ``confirmed_facts`` JSONB on every row it inserts.
-- Without an index, the same user pasting the same URL twice
-- produces duplicate Drafts.  This migration adds DB-enforced
-- idempotency *and* the route layer pre-queries existing keys
-- so the duplicate is reported back as "skipped" rather than
-- raising an IntegrityError mid-batch.
--
-- Why a partial unique index (WHERE clause):
--   * Only batch-imported rows have ``confirmed_facts.dedup_key``;
--     manually-created applications, API-imported rows, and rows
--     written before this migration shipped have no key and must
--     not be constrained.
--   * Postgres ``CREATE UNIQUE INDEX ... WHERE confirmed_facts ?
--     'dedup_key'`` excludes those rows from uniqueness entirely.
--
-- Why no CREATE INDEX CONCURRENTLY:
--   Supabase wraps each migration in a transaction and
--   CONCURRENTLY cannot run inside one.  The applications table
--   is small enough that the brief lock is acceptable.
--
-- Idempotent via IF NOT EXISTS so re-runs are safe.

CREATE UNIQUE INDEX IF NOT EXISTS applications_batch_dedup_uniq
    ON public.applications (user_id, ((confirmed_facts->>'dedup_key')))
    WHERE confirmed_facts ? 'dedup_key';
