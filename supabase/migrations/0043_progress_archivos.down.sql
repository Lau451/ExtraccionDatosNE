-- Down migration para 0043.
-- AVISO: se pierde el registro de archivos intercambiados con Progress
-- (duplicados, errores, reprocesos); los archivos en disco quedan.

DROP POLICY IF EXISTS parch_sel ON progress_archivos;
DROP POLICY IF EXISTS parch_del ON progress_archivos;
DROP TRIGGER IF EXISTS trg_progress_archivos_updated_at ON progress_archivos;

REVOKE ALL ON progress_archivos FROM authenticated;
REVOKE ALL ON progress_archivos FROM service_role;

DROP TABLE IF EXISTS progress_archivos;

NOTIFY pgrst, 'reload schema';
