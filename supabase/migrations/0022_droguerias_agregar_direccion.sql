-- =============================================================================
-- Migration 0022: agrega droguerias.direccion
--
-- droguerias no tenia columna de direccion (solo ciudad/provincia/codigo_postal),
-- necesaria para cargar los datos reales de la primera drogueria en produccion
-- (Drogueria Nueva Era). Columna nullable: las droguerias existentes no tienen
-- dato que perder ni backfill posible.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE droguerias ADD COLUMN IF NOT EXISTS direccion TEXT NULL;

-- Forzar reload de PostgREST para que el esquema exponga la columna nueva
NOTIFY pgrst, 'reload schema';
