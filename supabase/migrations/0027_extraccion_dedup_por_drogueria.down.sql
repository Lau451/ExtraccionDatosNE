-- Down migration para 0027.
--
-- AVISO (datos antes que esquema): si en algún momento entre el up y este down se
-- subió el MISMO source_sha256 desde DOS droguerías distintas, uq_er_sha256 (global)
-- no puede recrearse -- violaría unicidad sobre filas reales. Verificar antes de
-- correr este down:
--   SELECT source_sha256, COUNT(DISTINCT drogueria_id) AS n_droguerias
--     FROM extraction_results
--    GROUP BY source_sha256
--   HAVING COUNT(DISTINCT drogueria_id) > 1;
-- Si devuelve filas, resolver manualmente (fusionar o eliminar duplicados) antes de
-- bajar esta migración.

DROP FUNCTION IF EXISTS reserve_extraction(TEXT, UUID);

CREATE OR REPLACE FUNCTION reserve_extraction(p_sha TEXT)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_id     UUID;
  v_status TEXT;
BEGIN
  SELECT id, status
    INTO v_id, v_status
    FROM extraction_results
   WHERE source_sha256 = p_sha
     FOR UPDATE;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  IF v_status = 'completed' THEN
    RETURN v_id;
  END IF;

  RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION reserve_extraction(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reserve_extraction(TEXT) TO service_role;

ALTER TABLE extraction_results DROP CONSTRAINT IF EXISTS uq_er_drog_sha;

ALTER TABLE extraction_results
  ADD CONSTRAINT uq_er_sha256 UNIQUE (source_sha256);

NOTIFY pgrst, 'reload schema';
