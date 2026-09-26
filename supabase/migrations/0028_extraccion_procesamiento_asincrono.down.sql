-- Down migration para 0028.
--
-- AVISO (datos antes que esquema): si queda alguna fila con status='processing' al
-- momento de correr este down (un robot murió a mitad de camino y el sweep de
-- arranque -- services/extraccion/main.py -- todavía no la marcó 'failed'), el
-- ALTER que restaura el CHECK sin 'processing' va a fallar. Verificar antes:
--   SELECT id, source_filename, created_at FROM extraction_results
--    WHERE status = 'processing';
-- Si devuelve filas, marcarlas 'failed' manualmente (o esperar al sweep de
-- arranque del servicio) antes de bajar esta migración.

DROP FUNCTION IF EXISTS reserve_extraction(TEXT, UUID);

CREATE OR REPLACE FUNCTION reserve_extraction(p_sha TEXT, p_drogueria_id UUID)
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
     AND drogueria_id = p_drogueria_id
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

REVOKE ALL ON FUNCTION reserve_extraction(TEXT, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reserve_extraction(TEXT, UUID) TO service_role;

ALTER TABLE extraction_results DROP COLUMN IF EXISTS error_msg;

ALTER TABLE extraction_results DROP CONSTRAINT IF EXISTS ck_er_status;

ALTER TABLE extraction_results
  ADD CONSTRAINT ck_er_status CHECK (status IN ('completed', 'partial', 'failed'));

NOTIFY pgrst, 'reload schema';
