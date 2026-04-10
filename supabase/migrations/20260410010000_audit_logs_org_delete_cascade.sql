DO $$
DECLARE
    existing_constraint text;
BEGIN
    SELECT con.conname
    INTO existing_constraint
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY(con.conkey)
    WHERE con.contype = 'f'
      AND nsp.nspname = 'public'
      AND rel.relname = 'audit_logs'
      AND att.attname = 'org_id'
      AND con.confrelid = 'public.organizations'::regclass
    LIMIT 1;

    IF existing_constraint IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.audit_logs DROP CONSTRAINT %I', existing_constraint);
    END IF;
END $$;

ALTER TABLE public.audit_logs
    ADD CONSTRAINT audit_logs_org_id_fkey
    FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;