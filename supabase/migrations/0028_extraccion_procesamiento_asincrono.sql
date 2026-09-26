-- =============================================================================
-- Migration 0028: procesamiento asincrono de extracciones
--
-- POST /procesar deja de esperar al robot antes de responder: guarda el archivo,
-- valida duplicados, crea la sesion y responde 202 apenas inserta el registro de
-- extraction_results con status='processing'. El robot (Gemini) + la lectura del
-- CSV + la persistencia final corren en background (ver
-- services/extraccion/main.py::_procesar_documento_background,
-- odd/tasks/carga-asincrona.md). Esto requiere:
--
-- 1. ck_er_status admite 'processing' -- nuevo estado transitorio entre el INSERT
--    inicial (antes de invocar al robot) y el UPDATE final a 'completed' o
--    'failed'. 'failed' ya estaba permitido por el CHECK pero hasta esta migracion
--    nunca se escribia -- persistir_output_final solo insertaba con
--    status='completed' (si la persistencia fallaba, no se creaba fila alguna).
-- 2. error_msg TEXT NULL: mensaje de error legible en espanol cuando
--    status='failed', consumido por GET /api/documentos para mostrarlo en la UI
--    (RecentCard). NULL en cualquier otro estado.
-- 3. reserve_extraction: una fila en 'processing' cuenta como "tomada", igual que
--    'completed' -- devuelve su id (el caller de /procesar responde 409). Sin esto,
--    dos uploads simultaneos del mismo archivo arrancarian dos robots en paralelo
--    mientras el primero todavia esta procesando.
-- 4. Reproceso tras 'failed': el INSERT del nuevo intento (status=
--    'processing') pisaria la unique key (drogueria_id, source_sha256) si la fila
--    vieja sigue ahi (uq_er_drog_sha, migracion 0027). Se decide BORRAR la fila
--    vieja dentro de reserve_extraction, bajo el mismo SELECT ... FOR UPDATE que ya
--    usa para deduplicar -- asi el borrado es atomico con la decision de "permitir
--    reprocesar" y no hay ventana de carrera entre "borrar" y "el INSERT de
--    /procesar". Se pierde el registro historico del intento fallido (no existe
--    una tabla de auditoria separada hoy); se acepta porque el CSV en disco de un
--    intento fallido tampoco se conserva. Solo 'failed' se borra: una fila
--    'failed' nunca pudo validarse (validar_extraccion la rechaza), asi que no
--    tiene hijos en items_proceso/comparativas/ordenes_compra (FKs sin cascade).
--    'partial' (sin productor hoy, pero validable) pasa a contar como tomada:
--    borrarla podria violar esas FKs.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

-- 1) nuevo estado 'processing' ---------------------------------------------------
ALTER TABLE extraction_results DROP CONSTRAINT IF EXISTS ck_er_status;

ALTER TABLE extraction_results
  ADD CONSTRAINT ck_er_status CHECK (status IN ('completed', 'partial', 'failed', 'processing'));

-- 2) error_msg --------------------------------------------------------------------
ALTER TABLE extraction_results ADD COLUMN IF NOT EXISTS error_msg TEXT NULL;

COMMENT ON COLUMN extraction_results.error_msg IS
  'Mensaje de error legible (espanol) cuando status=''failed''. NULL en cualquier otro estado. Agregada en 0028 (procesamiento asincrono).';

-- 3) reserve_extraction re-firmada en su comportamiento (misma firma que 0027) ---
DROP FUNCTION IF EXISTS reserve_extraction(TEXT, UUID);

CREATE OR REPLACE FUNCTION reserve_extraction(p_sha TEXT, p_drogueria_id UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_id     UUID;
  v_status TEXT;
BEGIN
  -- SELECT FOR UPDATE bloquea la fila (si existe) mientras dura la transaccion:
  -- dos requests simultaneos con el mismo (sha256, drogueria_id) se serializan.
  SELECT id, status
    INTO v_id, v_status
    FROM extraction_results
   WHERE source_sha256 = p_sha
     AND drogueria_id = p_drogueria_id
     FOR UPDATE;

  -- Sin fila previa para esta droguería -> proceder con la extraccion.
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  -- 'completed' (ya termino) o 'processing' (hay un robot corriendo ahora mismo
  -- para este mismo archivo+drogueria) -> tomada: devolver su id, el caller
  -- responde 409 con ese extraction_id.
  IF v_status IN ('completed', 'processing', 'partial') THEN
    RETURN v_id;
  END IF;

  -- 'failed' -> se permite reprocesar. Se borra la fila vieja ACA,
  -- bajo el mismo lock, para liberar uq_er_drog_sha antes de que /procesar
  -- intente el INSERT (status='processing') del nuevo intento.
  DELETE FROM extraction_results WHERE id = v_id;
  RETURN NULL;
END;
$$;

-- Permisos: solo el service role puede invocar esta función
-- (en Supabase el service role bypasea RLS automáticamente)
REVOKE ALL ON FUNCTION reserve_extraction(TEXT, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reserve_extraction(TEXT, UUID) TO service_role;

NOTIFY pgrst, 'reload schema';
