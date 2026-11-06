-- 0044: progress_archivos no se borra desde el Data API.
--
-- La 0043 creó parch_del (DELETE para superadmin), pero authenticated nunca tuvo
-- GRANT DELETE sobre la tabla, así que la política no se podía ejecutar. Se
-- elimina en lugar de habilitarla: el registro es el rastro de cada archivo
-- intercambiado con Progress y la garantía de no procesar dos veces el mismo
-- contenido (uq_parch_contenido). Borrar una fila permitiría reimportar ese
-- archivo como si fuera nuevo. Solo el backend (service_role) mantiene la tabla.
-- (odd/tasks/integracion-progress.md L13 R3-delete-policy-unreachable, L16)

DROP POLICY IF EXISTS parch_del ON progress_archivos;

-- Explícito aunque 0043 ya solo otorgaba SELECT: authenticated no borra.
REVOKE DELETE ON progress_archivos FROM authenticated;

NOTIFY pgrst, 'reload schema';
