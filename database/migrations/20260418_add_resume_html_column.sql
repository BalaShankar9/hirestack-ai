-- Add resume_html column to applications table for tailored resume document
ALTER TABLE applications
  ADD COLUMN IF NOT EXISTS resume_html TEXT;
