-- =============================================================================
-- Fix: upsert_terceros_legacy — "column reference codigo_legacy is ambiguous"
--
-- Descubierto en Fase 9 (terceros-modelo, PR5) al ejecutar la RPC real contra
-- la base de test: TODA llamada a upsert_terceros_legacy(...) falla con
--   postgrest.exceptions.APIError: {'message': 'column reference "codigo_legacy"
--   is ambiguous', 'code': '42702', ...
--     'details': 'It could refer to either a PL/pgSQL variable or a table column.'}
--
-- Causa raíz: `RETURNS TABLE (codigo_legacy TEXT, tercero_id UUID, accion TEXT)`
-- crea 3 parámetros OUT que PL/pgSQL expone como variables de nivel de función.
-- Los parámetros de entrada usan el prefijo `p_` justamente para evitar esta
-- colisión con columnas reales (p_drogueria_id vs drogueria_id), pero los OUT
-- no lo tienen. `codigo_legacy` colisiona con `terceros_legacy_map.codigo_legacy`
-- y aparece sin calificar en el conflict target de:
--     INSERT INTO terceros_legacy_map (...)
--     ON CONFLICT (drogueria_id, sistema_origen, entidad_legacy, codigo_legacy)
--     DO NOTHING;
-- A diferencia de la lista de columnas de un INSERT (resuelta solo contra la
-- relación destino), el conflict target de ON CONFLICT sí pasa por el
-- resolutor general de expresiones de PL/pgSQL, que por default
-- (plpgsql.variable_conflict = error) rechaza cualquier identificador
-- ambiguo entre variable y columna.
--
-- Fix: `#variable_conflict use_column` como primera línea del cuerpo,
-- exactamente para este caso (recomendación estándar de la documentación de
-- PL/pgSQL). No cambia el contrato externo de la función (misma firma, mismas
-- columnas de retorno) ni la lógica de negocio — la única línea que asigna a
-- la variable OUT (`codigo_legacy := fila->>'codigo_legacy';`) es una
-- asignación PL/pgSQL directa, no una sentencia SQL embebida, así que el
-- pragma no la afecta.
-- =============================================================================

CREATE OR REPLACE FUNCTION upsert_terceros_legacy(
    p_drogueria_id   UUID,
    p_sistema_origen TEXT,
    p_entidad_legacy TEXT,      -- 'cliente' | 'proveedor'
    p_filas          JSONB,     -- array de objetos: codigo_legacy, razon_social, cuit, tipo, ...
    p_usuario_id     UUID
) RETURNS TABLE (codigo_legacy TEXT, tercero_id UUID, accion TEXT)
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE fila JSONB; v_tid UUID; v_accion TEXT;
BEGIN
  FOR fila IN SELECT * FROM jsonb_array_elements(p_filas) LOOP
    -- 1) clave de idempotencia
    SELECT m.tercero_id INTO v_tid FROM terceros_legacy_map m
     WHERE m.drogueria_id = p_drogueria_id AND m.sistema_origen = p_sistema_origen
       AND m.entidad_legacy = p_entidad_legacy AND m.codigo_legacy = fila->>'codigo_legacy'
     FOR UPDATE;
    v_accion := 'reusado';

    -- 2) misma empresa ya cargada bajo el otro rol
    IF v_tid IS NULL AND nullif(fila->>'cuit','') IS NOT NULL THEN
      SELECT t.id INTO v_tid FROM terceros t
       WHERE t.drogueria_id = p_drogueria_id AND t.cuit = fila->>'cuit' AND t.deleted_at IS NULL
       FOR UPDATE;
      IF v_tid IS NOT NULL THEN v_accion := 'vinculado'; END IF;
    END IF;

    -- 3) alta
    IF v_tid IS NULL THEN
      INSERT INTO terceros (drogueria_id, codigo_interno, razon_social, cuit, created_by, updated_by)
      VALUES (p_drogueria_id, fila->>'codigo_legacy', fila->>'razon_social',
              nullif(fila->>'cuit',''), p_usuario_id, p_usuario_id)
      RETURNING id INTO v_tid;
      v_accion := 'creado';
    ELSE
      UPDATE terceros SET razon_social = coalesce(fila->>'razon_social', razon_social),
                          cuit = coalesce(nullif(fila->>'cuit',''), cuit),
                          updated_by = p_usuario_id, activo = TRUE
       WHERE id = v_tid;
    END IF;

    -- 4) mapa (idempotente)
    INSERT INTO terceros_legacy_map (tercero_id, drogueria_id, sistema_origen,
                                     entidad_legacy, codigo_legacy, datos_legacy)
    VALUES (v_tid, p_drogueria_id, p_sistema_origen, p_entidad_legacy,
            fila->>'codigo_legacy', fila)
    ON CONFLICT (drogueria_id, sistema_origen, entidad_legacy, codigo_legacy) DO NOTHING;

    -- 5) tabla de rol (id compartido)
    IF p_entidad_legacy = 'cliente' THEN
      INSERT INTO clientes (id, drogueria_id, tipo, activo, created_by, updated_by)
      VALUES (v_tid, p_drogueria_id, coalesce(fila->>'tipo','otro'), TRUE, p_usuario_id, p_usuario_id)
      ON CONFLICT (id) DO UPDATE SET tipo = excluded.tipo, activo = TRUE, updated_by = p_usuario_id;
    ELSE
      INSERT INTO proveedores (id, drogueria_id, tipo, es_competidor, es_proveedor_compra,
                               activo, created_by, updated_by)
      VALUES (v_tid, p_drogueria_id, coalesce(fila->>'tipo','otro'),
              coalesce((fila->>'es_competidor')::bool, TRUE),
              coalesce((fila->>'es_proveedor_compra')::bool, FALSE),
              TRUE, p_usuario_id, p_usuario_id)
      ON CONFLICT (id) DO UPDATE SET tipo = excluded.tipo, activo = TRUE, updated_by = p_usuario_id;
    END IF;

    codigo_legacy := fila->>'codigo_legacy'; tercero_id := v_tid; accion := v_accion;
    RETURN NEXT;
  END LOOP;
END $$;

-- REVOKE/GRANT no cambian (mismo owner, misma firma) pero se dejan explícitos
-- por si CREATE OR REPLACE alguna vez corriera contra una función que no
-- existía aún (idempotencia del script de migración).
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM anon;
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM authenticated;
GRANT  EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) TO service_role;
