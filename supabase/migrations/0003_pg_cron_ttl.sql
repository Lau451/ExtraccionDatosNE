-- =============================================================================
-- Migration 0003: TTL automático con pg_cron
--
-- Crea un job diario (2 AM UTC) que elimina sesiones completadas/fallidas
-- con más de 7 días de antigüedad, junto con sus chunks asociados.
--
-- IMPORTANTE: pg_cron debe estar habilitado en Supabase Extensions antes
-- de aplicar esta migración:
--   Dashboard → Database → Extensions → buscar "pg_cron" → Enable
--
-- Tablas afectadas:
--   chunk_results        — borradas via CASCADE desde processing_sessions
--   processing_sessions  — borradas si status IN (completed, failed, partial)
--                          y updated_at < NOW() - 7 días
--
-- NO toca extraction_results (tabla de auditoría permanente).
-- =============================================================================

-- Habilitar pg_cron (requiere estar habilitado en Supabase Extensions)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Agregar columna updated_at a processing_sessions para poder hacer TTL
-- (la tabla original no la tenía; usamos updated_at para la comparación temporal)
ALTER TABLE processing_sessions
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Trigger para mantener updated_at actualizado en processing_sessions
-- (reutilizamos la función trg_set_updated_at creada en 0001)
CREATE TRIGGER tr_sessions_updated
  BEFORE UPDATE ON processing_sessions
  FOR EACH ROW
  EXECUTE FUNCTION trg_set_updated_at();

-- Job pg_cron: limpia sesiones terminadas con más de 7 días de antigüedad.
-- Corre diariamente a las 2:00 AM UTC.
-- El nombre del job es único — si ya existe, la llamada es idempotente por
-- ON CONFLICT en la tabla cron.job.
SELECT cron.schedule(
  'cleanup-old-sessions',   -- nombre único del job
  '0 2 * * *',              -- cron expression: 2 AM UTC todos los días
  $$
  -- 1. Borrar chunks de sesiones expiradas
  --    (ON DELETE CASCADE haría esto automáticamente, pero lo hacemos
  --    explícito para evitar depender de la secuencia de borrado)
  DELETE FROM chunk_results
  WHERE session_id IN (
    SELECT id
    FROM processing_sessions
    WHERE status IN ('completed', 'failed', 'partial')
      AND updated_at < NOW() - INTERVAL '7 days'
  );

  -- 2. Borrar las sesiones expiradas
  DELETE FROM processing_sessions
  WHERE status IN ('completed', 'failed', 'partial')
    AND updated_at < NOW() - INTERVAL '7 days';
  $$
);
