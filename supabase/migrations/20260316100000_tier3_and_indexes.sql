-- Tier 3 CHECK constraints
ALTER TABLE doc_variants
  ADD CONSTRAINT ck_doc_variants_tone
  CHECK (tone IN ('conservative', 'balanced', 'creative'));

ALTER TABLE learning_challenges
  ADD CONSTRAINT ck_learning_difficulty
  CHECK (difficulty IN ('beginner', 'intermediate', 'advanced'));

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_applications_user_status
  ON applications(user_id, status);

CREATE INDEX IF NOT EXISTS idx_documents_user_type
  ON documents(user_id, document_type);

CREATE INDEX IF NOT EXISTS idx_applications_user_created
  ON applications(user_id, created_at DESC);

-- Realtime publication
ALTER PUBLICATION supabase_realtime ADD TABLE doc_variants;
ALTER PUBLICATION supabase_realtime ADD TABLE review_comments;
