-- HireStack AI — AIM output gate_action backfill
--
-- ``gate_action`` is persisted by the application layer to explain why a
-- section version is or is not current. Add the column for already-applied
-- databases and backfill existing rows from ``passed_gate``.

ALTER TABLE aim_section_outputs
    ADD COLUMN IF NOT EXISTS gate_action VARCHAR(20);

UPDATE aim_section_outputs
SET gate_action = CASE WHEN passed_gate THEN 'show' ELSE 'flag' END
WHERE gate_action IS NULL;

ALTER TABLE aim_section_outputs
    ALTER COLUMN gate_action SET DEFAULT 'flag';

ALTER TABLE aim_section_outputs
    ALTER COLUMN gate_action SET NOT NULL;