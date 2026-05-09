-- =============================================================================
-- Migration 0002: RPC reserve_extraction
--
-- Función PostgreSQL que verifica si ya existe un extraction_result completado
-- para un SHA256 dado, usando SELECT FOR UPDATE para evitar race conditions
-- cuando dos uploads del mismo archivo llegan simultáneamente.
--
-- Retorna:
--   NULL  → no existe registro con ese SHA256 (proceder con extracción normal)
--   UUID  → existe registro con status='completed' (duplicado detectado)
--
-- NOTA: Si el registro existe con status != 'completed' (partial, failed),
-- retorna NULL para permitir el reprocesamiento.
-- =============================================================================

CREATE OR REPLACE FUNCTION reserve_extraction(p_sha TEXT)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_id     UUID;
  v_status TEXT;
BEGIN
  -- SELECT FOR UPDATE bloquea la fila mientras dura la transacción.
  -- Si dos requests llegan al mismo tiempo con el mismo SHA256:
  --   el 2do espera hasta que el 1ro libere el lock (commit/rollback).
  SELECT id, status
    INTO v_id, v_status
    FROM extraction_results
   WHERE source_sha256 = p_sha
     FOR UPDATE;

  -- Si no existe ningún registro → NULL (proceder con extracción)
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  -- Si existe con status='completed' → retornar el UUID existente (duplicado)
  IF v_status = 'completed' THEN
    RETURN v_id;
  END IF;

  -- Si existe con status='partial' o 'failed' → NULL (permitir reprocesamiento)
  RETURN NULL;
END;
$$;

-- Permisos: solo el service role puede invocar esta función
-- (en Supabase el service role bypasea RLS automáticamente)
REVOKE ALL ON FUNCTION reserve_extraction(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reserve_extraction(TEXT) TO service_role;
