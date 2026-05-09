-- ════════════════════════════════════════════════════════════════════
-- Feature flag audit log (P1-9 / m12-pr09).
--
-- Append-only history of feature-flag value changes (deploys, runtime
-- flips via admin API, ops scripts). Today's flags are env-driven via
-- pydantic Settings, so the only writers will be:
--
--   * record_snapshot_from_registry()  — called from boot/ops scripts to
--     capture per-deploy values; idempotent (skips when value unchanged
--     since last entry for the same scope+tenant).
--   * record_change()                  — called by future admin/api
--     handlers when an operator flips a flag at runtime.
--
-- Schema notes:
--   * scope='global' for env/process-wide values; tenant_id NULL.
--   * scope='tenant' for per-tenant overrides; tenant_id required.
--   * old_value / new_value stored as text (matches YAML/env reality:
--     "true", "false", "1", "off", numeric strings, JSON blobs for
--     more complex flags).
--   * actor is freeform — 'system', 'env', '<user-uuid>', '<service>'.
--   * One index on (flag_name, scope, tenant_id, recorded_at DESC) so
--     the "last value for this flag" lookup powering idempotency stays
--     constant-time.
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.feature_flag_audit (
    id           BIGSERIAL PRIMARY KEY,
    flag_name    TEXT        NOT NULL,
    scope        TEXT        NOT NULL DEFAULT 'global'
                             CHECK (scope IN ('global', 'tenant')),
    tenant_id    UUID        NULL,
    old_value    TEXT        NULL,
    new_value    TEXT        NOT NULL,
    actor        TEXT        NOT NULL DEFAULT 'system',
    reason       TEXT        NULL,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- tenant scope must carry a tenant_id; global scope must not.
    CONSTRAINT feature_flag_audit_scope_tenant_chk
        CHECK (
            (scope = 'global' AND tenant_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_feature_flag_audit_lookup
    ON public.feature_flag_audit (flag_name, scope, tenant_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_feature_flag_audit_recent
    ON public.feature_flag_audit (recorded_at DESC);

ALTER TABLE public.feature_flag_audit ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
     WHERE tablename = 'feature_flag_audit'
       AND policyname = 'Service role full access on feature_flag_audit'
  ) THEN
    CREATE POLICY "Service role full access on feature_flag_audit"
        ON public.feature_flag_audit
        FOR ALL
        USING (auth.role() = 'service_role');
  END IF;
END $$;

COMMENT ON TABLE  public.feature_flag_audit IS
    'Append-only history of feature flag value changes. Powers compliance '
    'review (who flipped what, when, why) and per-deploy drift detection. '
    'Wired by FeatureFlagAuditService; populated on first deploy after '
    'every value change.';
COMMENT ON COLUMN public.feature_flag_audit.scope IS
    'global = env/process-wide; tenant = per-tenant override.';
COMMENT ON COLUMN public.feature_flag_audit.actor IS
    'Who changed it: system, env, <user-uuid>, <service>.';
COMMENT ON COLUMN public.feature_flag_audit.reason IS
    'Free-form rationale; PR link, incident ID, ticket reference.';
