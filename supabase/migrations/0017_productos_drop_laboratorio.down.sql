-- Down migration para 0017_productos_drop_laboratorio.sql
-- Re-crea la columna como nullable TEXT. No restaura datos: no habia
-- ninguno (las 15 filas existentes al momento del DROP tenian laboratorio
-- IS NULL).

ALTER TABLE productos ADD COLUMN IF NOT EXISTS laboratorio TEXT NULL;

NOTIFY pgrst, 'reload schema';
