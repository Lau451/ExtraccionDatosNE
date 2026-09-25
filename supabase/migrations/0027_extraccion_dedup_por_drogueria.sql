-- =============================================================================
-- Migration 0027: dedup de extracciones por droguería
--
-- uq_er_sha256 UNIQUE (source_sha256) era GLOBAL: el mismo sha256 subido por dos
-- droguerías distintas colisionaba, y la RPC reserve_extraction(p_sha) devolvía
-- el extraction_id de la PRIMERA droguería que lo subió -- el 409 de /procesar podía
-- filtrar el id (y por transitividad, la existencia de una extracción) de OTRA
-- droguería (odd/tasks/extraccion-multi-tenant.md, Problem).
--
-- 1. uq_er_sha256 -> uq_er_drog_sha UNIQUE (drogueria_id, source_sha256): mismo
--    archivo, distinta droguería, ya no colisiona.
-- 2. reserve_extraction(p_sha) -> reserve_extraction(p_sha, p_drogueria_id): el
--    SELECT ... FOR UPDATE ahora filtra por ambos, así el 409 nunca puede devolver
--    un extraction_id de otra droguería. Firma vieja eliminada (no hay overload).
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

-- 1) unicidad por droguería ----------------------------------------------------
ALTER TABLE extraction_results DROP CONSTRAINT IF EXISTS uq_er_sha256;

ALTER TABLE extraction_results
  ADD CONSTRAINT uq_er_drog_sha UNIQUE (drogueria_id, source_sha256);

COMMENT ON CONSTRAINT uq_er_drog_sha ON extraction_results IS
  'Dedup por droguería, no global (migración 0027) -- el mismo archivo binario subido por dos droguerías distintas produce dos extraction_results independientes.';

-- 2) RPC re-firmada -------------------------------------------------------------
DROP FUNCTION IF EXISTS reserve_extraction(TEXT);

CREATE OR REPLACE FUNCTION reserve_extraction(p_sha TEXT, p_drogueria_id UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_id     UUID;
  v_status TEXT;
BEGIN
  -- SELECT FOR UPDATE bloquea la fila mientras dura la transacción.
  -- Si dos requests llegan al mismo tiempo con el mismo (sha256, drogueria_id):
  --   el 2do espera hasta que el 1ro libere el lock (commit/rollback).
  SELECT id, status
    INTO v_id, v_status
    FROM extraction_results
   WHERE source_sha256 = p_sha
     AND drogueria_id = p_drogueria_id
     FOR UPDATE;

  -- Si no existe ningún registro para esta droguería → NULL (proceder con extracción)
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  -- Si existe con status='completed' → retornar el UUID existente (duplicado),
  -- siempre de la MISMA droguería que pidió el filtro.
  IF v_status = 'completed' THEN
    RETURN v_id;
  END IF;

  -- Si existe con status='partial' o 'failed' → NULL (permitir reprocesamiento)
  RETURN NULL;
END;
$$;

-- Permisos: solo el service role puede invocar esta función
-- (en Supabase el service role bypasea RLS automáticamente)
REVOKE ALL ON FUNCTION reserve_extraction(TEXT, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reserve_extraction(TEXT, UUID) TO service_role;

NOTIFY pgrst, 'reload schema';
