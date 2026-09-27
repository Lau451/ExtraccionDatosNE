-- =============================================================================
-- Migration 0029: uploader de extraction_results (validar-extraccion-organizacion, T1)
--
-- extraction_results no persiste quién subió el documento -- `client_id` se
-- acepta en POST /procesar pero nunca se guarda (services/extraccion/
-- persistent_output.py, ver docstring de persistir_output_final). El filtro
-- "Solo mías" de la pantalla de validación (decisión de usuario, 2026-09-26,
-- odd/tasks/validar-extraccion-organizacion.md) necesita esa columna.
--
-- 1. subido_por UUID NULL: el usuario autenticado que hizo POST /procesar.
--    NULL en filas existentes (creadas antes de esta migración) y en filas
--    donde `services/extraccion/persistent_output.py::crear_extraction_processing`
--    no recibió un usuario_id (no debería pasar en el flujo real desde este
--    cambio, pero la columna es nullable por prudencia -- mismo criterio que
--    proceso_comercial_id/grupo_id en la misma tabla). Una fila con
--    subido_por=NULL nunca matchea el filtro "Solo mías", sin importar quién
--    pregunte (comportamiento aceptado explícitamente en la decisión de
--    usuario).
-- 2. FK a usuarios(id): mismo criterio que fk_pcp_createdby/fk_terceros_createdby
--    (0008/0011/0012) para columnas de auditoría de usuario. `validado_por` de
--    esta misma tabla es la única excepción histórica sin FK (schema base,
--    docs/schema/extractor_final.sql) -- no se corrige acá (fuera de alcance
--    de esta tarea), pero subido_por sí la lleva por decisión explícita del
--    usuario para este cambio.
-- 3. idx_er_subido_por: parcial + compuesto, mismo estilo que idx_er_sin_validar
--    (drogueria_id, created_at DESC) -- soporta el filtro "Solo mías" de
--    GET /extracciones (solo_mias=true: RLS ya acota por drogueria_id, este
--    índice agrega subido_por a esa misma forma de acceso, ordenado por
--    created_at DESC como el resto del listado). Parcial porque las filas
--    pre-existentes con subido_por NULL nunca participan de ese filtro.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE extraction_results ADD COLUMN IF NOT EXISTS subido_por UUID NULL;

ALTER TABLE extraction_results DROP CONSTRAINT IF EXISTS fk_er_subidopor;

ALTER TABLE extraction_results
  ADD CONSTRAINT fk_er_subidopor FOREIGN KEY (subido_por) REFERENCES usuarios (id);

COMMENT ON COLUMN extraction_results.subido_por IS
  'Usuario autenticado que hizo POST /procesar (services/extraccion/main.py). NULL en filas creadas antes de esta migración, o si la persistencia del uploader no estaba disponible. Nunca matchea el filtro "Solo mías" (validar-extraccion-organizacion). Agregada en 0029.';

CREATE INDEX IF NOT EXISTS idx_er_subido_por
    ON extraction_results (drogueria_id, subido_por, created_at DESC)
    WHERE subido_por IS NOT NULL;

NOTIFY pgrst, 'reload schema';
