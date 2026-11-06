-- Down migration para 0044: restaura la política de 0043 (sin efecto práctico,
-- authenticated sigue sin GRANT DELETE).

DROP POLICY IF EXISTS parch_del ON progress_archivos;
CREATE POLICY parch_del ON progress_archivos FOR DELETE USING ((select es_superadmin()));

NOTIFY pgrst, 'reload schema';
