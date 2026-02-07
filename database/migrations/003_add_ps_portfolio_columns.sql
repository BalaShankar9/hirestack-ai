-- Migration: Add personal statement & portfolio columns to applications
-- Run this in your Supabase SQL Editor

ALTER TABLE applications
  ADD COLUMN IF NOT EXISTS personal_statement_html TEXT,
  ADD COLUMN IF NOT EXISTS portfolio_html TEXT,
  ADD COLUMN IF NOT EXISTS ps_versions JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS portfolio_versions JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS validation JSONB;
