-- HireStack AI — Fix gap_reports: add missing status and updated_at columns
-- Also adds the update_updated_at trigger for gap_reports and exports.

ALTER TABLE public.gap_reports
  ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Apply updated_at trigger to gap_reports
DROP TRIGGER IF EXISTS update_gap_reports_updated_at ON public.gap_reports;
CREATE TRIGGER update_gap_reports_updated_at
  BEFORE UPDATE ON public.gap_reports
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Apply updated_at trigger to exports (was also missing)
DROP TRIGGER IF EXISTS update_exports_updated_at ON public.exports;
CREATE TRIGGER update_exports_updated_at
  BEFORE UPDATE ON public.exports
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
