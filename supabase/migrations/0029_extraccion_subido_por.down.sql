-- Down migration para 0029.

DROP INDEX IF EXISTS idx_er_subido_por;

ALTER TABLE extraction_results DROP CONSTRAINT IF EXISTS fk_er_subidopor;

ALTER TABLE extraction_results DROP COLUMN IF EXISTS subido_por;

NOTIFY pgrst, 'reload schema';
