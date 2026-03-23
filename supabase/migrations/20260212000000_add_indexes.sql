-- HireStack AI — Security hardening migration
-- M11-F16: Missing indexes on foreign key columns
-- M11-F17: CHECK constraints on status/type columns
-- M11-F19: TEXT column size limits

-- ════════════════════════════════════════════════════════════════
-- M11-F16: Add missing indexes on foreign key columns
-- ════════════════════════════════════════════════════════════════

-- Create indexes only for tables that exist (safe for partial schema)
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'documents') THEN
    CREATE INDEX IF NOT EXISTS idx_documents_user_id ON public.documents(user_id);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'interview_sessions') THEN
    CREATE INDEX IF NOT EXISTS idx_interview_sessions_application_id ON public.interview_sessions(application_id);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'interview_answers') THEN
    CREATE INDEX IF NOT EXISTS idx_interview_answers_user_id ON public.interview_answers(user_id);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'doc_versions') THEN
    CREATE INDEX IF NOT EXISTS idx_doc_versions_user_id ON public.doc_versions(user_id);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'learning_plans') THEN
    CREATE INDEX IF NOT EXISTS idx_learning_plans_application_id ON public.learning_plans(application_id);
  END IF;
END $$;

-- ════════════════════════════════════════════════════════════════
-- M11-F17: CHECK constraints on status/type enum columns
-- ════════════════════════════════════════════════════════════════

-- applications.status
ALTER TABLE public.applications
  DROP CONSTRAINT IF EXISTS chk_applications_status;
ALTER TABLE public.applications
  ADD CONSTRAINT chk_applications_status
  CHECK (status IN ('draft', 'active', 'submitted', 'interview', 'offer', 'rejected', 'withdrawn', 'archived'));

-- documents.document_type
ALTER TABLE public.documents
  DROP CONSTRAINT IF EXISTS chk_documents_document_type;
ALTER TABLE public.documents
  ADD CONSTRAINT chk_documents_document_type
  CHECK (document_type IN ('cv', 'cover_letter', 'personal_statement', 'portfolio', 'resume', 'other'));

-- documents.status
ALTER TABLE public.documents
  DROP CONSTRAINT IF EXISTS chk_documents_status;
ALTER TABLE public.documents
  ADD CONSTRAINT chk_documents_status
  CHECK (status IN ('draft', 'final', 'archived'));

-- evidence.kind
ALTER TABLE public.evidence
  DROP CONSTRAINT IF EXISTS chk_evidence_kind;
ALTER TABLE public.evidence
  ADD CONSTRAINT chk_evidence_kind
  CHECK (kind IN ('link', 'file'));

-- evidence.type
ALTER TABLE public.evidence
  DROP CONSTRAINT IF EXISTS chk_evidence_type;
ALTER TABLE public.evidence
  ADD CONSTRAINT chk_evidence_type
  CHECK (type IN ('cert', 'project', 'course', 'award', 'publication', 'other'));

-- tasks.status
ALTER TABLE public.tasks
  DROP CONSTRAINT IF EXISTS chk_tasks_status;
ALTER TABLE public.tasks
  ADD CONSTRAINT chk_tasks_status
  CHECK (status IN ('todo', 'in-progress', 'done', 'skipped'));

-- tasks.priority
ALTER TABLE public.tasks
  DROP CONSTRAINT IF EXISTS chk_tasks_priority;
ALTER TABLE public.tasks
  ADD CONSTRAINT chk_tasks_priority
  CHECK (priority IN ('low', 'medium', 'high'));

-- interview_sessions constraints (skip if columns don't exist)
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'interview_sessions' AND column_name = 'status') THEN
    ALTER TABLE public.interview_sessions DROP CONSTRAINT IF EXISTS chk_interview_sessions_status;
    ALTER TABLE public.interview_sessions ADD CONSTRAINT chk_interview_sessions_status CHECK (status IN ('in_progress', 'completed', 'abandoned'));
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'interview_sessions' AND column_name = 'interview_type') THEN
    ALTER TABLE public.interview_sessions DROP CONSTRAINT IF EXISTS chk_interview_sessions_type;
    ALTER TABLE public.interview_sessions ADD CONSTRAINT chk_interview_sessions_type CHECK (interview_type IN ('behavioral', 'technical', 'situational', 'mixed'));
  END IF;
END $$;

-- exports and gap_reports constraints (skip if columns don't exist)
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'exports' AND column_name = 'format') THEN
    ALTER TABLE public.exports DROP CONSTRAINT IF EXISTS chk_exports_format;
    ALTER TABLE public.exports ADD CONSTRAINT chk_exports_format CHECK (format IN ('pdf', 'docx', 'html', 'txt', 'md', 'json'));
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'exports' AND column_name = 'status') THEN
    ALTER TABLE public.exports DROP CONSTRAINT IF EXISTS chk_exports_status;
    ALTER TABLE public.exports ADD CONSTRAINT chk_exports_status CHECK (status IN ('pending', 'processing', 'completed', 'failed'));
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'gap_reports' AND column_name = 'status') THEN
    ALTER TABLE public.gap_reports DROP CONSTRAINT IF EXISTS chk_gap_reports_status;
    ALTER TABLE public.gap_reports ADD CONSTRAINT chk_gap_reports_status CHECK (status IN ('pending', 'generated', 'reviewed'));
  END IF;
END $$;

-- ════════════════════════════════════════════════════════════════
-- M11-F19: TEXT column size limits via CHECK constraints
-- ════════════════════════════════════════════════════════════════

-- Text length constraints (only add if columns exist)
DO $$ BEGIN
  -- applications
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'applications' AND column_name = 'title') THEN
    ALTER TABLE public.applications DROP CONSTRAINT IF EXISTS chk_applications_title_length;
    ALTER TABLE public.applications ADD CONSTRAINT chk_applications_title_length CHECK (length(title) <= 500);
  END IF;
  -- documents
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'title') THEN
    ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS chk_documents_title_length;
    ALTER TABLE public.documents ADD CONSTRAINT chk_documents_title_length CHECK (length(title) <= 500);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'content') THEN
    ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS chk_documents_content_length;
    ALTER TABLE public.documents ADD CONSTRAINT chk_documents_content_length CHECK (length(content) <= 100000);
  END IF;
  -- evidence
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'evidence' AND column_name = 'title') THEN
    ALTER TABLE public.evidence DROP CONSTRAINT IF EXISTS chk_evidence_title_length;
    ALTER TABLE public.evidence ADD CONSTRAINT chk_evidence_title_length CHECK (length(title) <= 500);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'evidence' AND column_name = 'description') THEN
    ALTER TABLE public.evidence DROP CONSTRAINT IF EXISTS chk_evidence_description_length;
    ALTER TABLE public.evidence ADD CONSTRAINT chk_evidence_description_length CHECK (length(description) <= 5000);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'evidence' AND column_name = 'url') THEN
    ALTER TABLE public.evidence DROP CONSTRAINT IF EXISTS chk_evidence_url_length;
    ALTER TABLE public.evidence ADD CONSTRAINT chk_evidence_url_length CHECK (length(url) <= 2048);
  END IF;
  -- tasks
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'tasks' AND column_name = 'title') THEN
    ALTER TABLE public.tasks DROP CONSTRAINT IF EXISTS chk_tasks_title_length;
    ALTER TABLE public.tasks ADD CONSTRAINT chk_tasks_title_length CHECK (length(title) <= 500);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'tasks' AND column_name = 'description') THEN
    ALTER TABLE public.tasks DROP CONSTRAINT IF EXISTS chk_tasks_description_length;
    ALTER TABLE public.tasks ADD CONSTRAINT chk_tasks_description_length CHECK (length(description) <= 5000);
  END IF;
END $$;

-- interview_sessions length constraints (skip if columns don't exist)
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'interview_sessions' AND column_name = 'job_title') THEN
    ALTER TABLE public.interview_sessions DROP CONSTRAINT IF EXISTS chk_interview_sessions_title_length;
    ALTER TABLE public.interview_sessions ADD CONSTRAINT chk_interview_sessions_title_length CHECK (length(job_title) <= 500);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'interview_sessions' AND column_name = 'overall_feedback') THEN
    ALTER TABLE public.interview_sessions DROP CONSTRAINT IF EXISTS chk_interview_sessions_feedback_length;
    ALTER TABLE public.interview_sessions ADD CONSTRAINT chk_interview_sessions_feedback_length CHECK (length(overall_feedback) <= 10000);
  END IF;
END $$;

-- Remaining length constraints (safe for partial schemas)
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'full_name') THEN
    ALTER TABLE public.users DROP CONSTRAINT IF EXISTS chk_users_full_name_length;
    ALTER TABLE public.users ADD CONSTRAINT chk_users_full_name_length CHECK (length(full_name) <= 255);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'job_descriptions' AND column_name = 'title') THEN
    ALTER TABLE public.job_descriptions DROP CONSTRAINT IF EXISTS chk_job_descriptions_title_length;
    ALTER TABLE public.job_descriptions ADD CONSTRAINT chk_job_descriptions_title_length CHECK (length(title) <= 500);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'job_descriptions' AND column_name = 'description') THEN
    ALTER TABLE public.job_descriptions DROP CONSTRAINT IF EXISTS chk_job_descriptions_desc_length;
    ALTER TABLE public.job_descriptions ADD CONSTRAINT chk_job_descriptions_desc_length CHECK (length(description) <= 50000);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'doc_versions' AND column_name = 'html') THEN
    ALTER TABLE public.doc_versions DROP CONSTRAINT IF EXISTS chk_doc_versions_html_length;
    ALTER TABLE public.doc_versions ADD CONSTRAINT chk_doc_versions_html_length CHECK (length(html) <= 100000);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'salary_analyses') THEN
    CREATE INDEX IF NOT EXISTS idx_salary_analyses_application_id ON public.salary_analyses(application_id);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'learning_challenges') THEN
    CREATE INDEX IF NOT EXISTS idx_learning_challenges_user_id ON public.learning_challenges(user_id);
  END IF;
END $$;
