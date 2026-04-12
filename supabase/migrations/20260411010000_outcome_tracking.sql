-- Outcome tracking: close the feedback loop between AI outputs and real results
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── 1. Add outcome columns to applications ──────────────────────────
ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS callback_received_at   timestamptz,
    ADD COLUMN IF NOT EXISTS offer_received_at       timestamptz,
    ADD COLUMN IF NOT EXISTS user_rating             smallint CHECK (user_rating IS NULL OR (user_rating >= 1 AND user_rating <= 5)),
    ADD COLUMN IF NOT EXISTS user_feedback_text      text;

CREATE INDEX IF NOT EXISTS idx_applications_callback
    ON applications(user_id) WHERE callback_received_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_applications_offer
    ON applications(user_id) WHERE offer_received_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_applications_rated
    ON applications(user_id) WHERE user_rating IS NOT NULL;


-- ── 2. A/B test results ─────────────────────────────────────────────
-- Tracks which document variant (tone/style) led to better outcomes.
CREATE TABLE IF NOT EXISTS ab_test_results (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id      uuid NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    variant_id          text NOT NULL,          -- e.g. "conservative", "balanced", "creative"
    document_type       text NOT NULL,          -- "cv", "cover_letter", etc.
    ats_score           real,
    readability_score   real,
    keyword_density     real,
    outcome_type        text CHECK (outcome_type IN ('callback', 'offer', 'rejection', 'no_response', NULL)),
    outcome_recorded_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ab_test_results_user
    ON ab_test_results(user_id);
CREATE INDEX IF NOT EXISTS idx_ab_test_results_application
    ON ab_test_results(application_id);
CREATE INDEX IF NOT EXISTS idx_ab_test_results_variant
    ON ab_test_results(variant_id, outcome_type);

ALTER TABLE ab_test_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY ab_test_results_owner ON ab_test_results
    FOR ALL USING (auth.uid() = user_id);
