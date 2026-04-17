-- Lifecycle: cascade-delete document_library rows when parent application is deleted.
-- Previous behaviour was ON DELETE SET NULL which orphaned documents.

ALTER TABLE public.document_library
  DROP CONSTRAINT IF EXISTS document_library_application_id_fkey;

ALTER TABLE public.document_library
  ADD CONSTRAINT document_library_application_id_fkey
  FOREIGN KEY (application_id)
  REFERENCES public.applications(id)
  ON DELETE CASCADE;
