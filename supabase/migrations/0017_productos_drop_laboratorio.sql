-- =============================================================================
-- Migration 0017: retiro definitivo de productos.laboratorio
--
-- Continuacion de 0016_productos_marca_envase_caracteristicas.sql: esa
-- migracion dejo productos.laboratorio sin usar (reemplazada por marca_id)
-- pero sin DROP, porque productos tenia 15 filas en el proyecto de test en
-- vez de las 0 esperadas.
--
-- Verificado ahora, fila por fila (select id, codigo_interno, nombre,
-- laboratorio, created_at from productos order by created_at):
--   - Las 15 filas son fixtures/demo: codigo_interno con prefijo PROD-TEST-,
--     TEST-<hash> o DEMO-PCP-, creadas entre 2026-09-06 y 2026-09-12 por
--     corridas de test de productos/imports/PCP.
--   - Las 15 tienen laboratorio IS NULL. Ninguna fila, real o de test, tiene
--     un valor en esa columna. No hay dato que perder con el DROP.
--
-- El codigo de aplicacion ya no lee ni escribe laboratorio desde 0016
-- (services/productos, services/presupuestacion/imports, frontend). Este
-- DROP es el cierre de ese retiro, no un cambio de comportamiento.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE productos DROP COLUMN IF EXISTS laboratorio;

-- Forzar reload de PostgREST para que el esquema deje de exponer la columna
NOTIFY pgrst, 'reload schema';
