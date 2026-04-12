-- Atomic module status update — avoids read-modify-write race conditions
-- when multiple concurrent module generations try to update the same application row.
CREATE OR REPLACE FUNCTION public.jsonb_set_module_status(
  p_app_id UUID,
  p_module_key TEXT,
  p_status JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE applications
  SET modules = jsonb_set(
    COALESCE(modules, '{}'::jsonb),
    ARRAY[p_module_key],
    p_status,
    true  -- create if missing
  ),
  updated_at = NOW()
  WHERE id = p_app_id;
END;
$$;
