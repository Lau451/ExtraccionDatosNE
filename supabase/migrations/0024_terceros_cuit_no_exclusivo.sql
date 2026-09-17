-- =============================================================================
-- Migration 0024: terceros.cuit_no_exclusivo
--
-- Contexto: al migrar el legacy de Nueva Era aparecio un patron real de
-- entidades publicas/institucionales (hospitales bajo el CUIT del Ministerio
-- de Salud provincial, estaciones de servicio bajo el CUIT de la petrolera)
-- donde decenas de cuentas de cliente/proveedor DISTINTAS -- necesitan
-- entrega y facturacion separadas -- comparten legitimamente un mismo CUIT
-- fiscal. uq_terceros_cuit (0008) asume 1 CUIT = 1 empresa por drogueria, y
-- el paso 2 de upsert_terceros_legacy vincula agresivamente por CUIT -- ambos
-- correctos para el caso general (evitar duplicar una empresa, fusionar
-- cliente+proveedor), pero exactamente lo que rompe este patron.
--
-- Decision: NO se afloja la unicidad de CUIT para todos (debilitaria la
-- garantia que motivo el modelo entero). Se agrega una excepcion explicita,
-- opt-in por fila: terceros.cuit_no_exclusivo. Un tercero marcado asi:
--   - queda fuera de uq_terceros_cuit (puede repetir CUIT con otros).
--   - upsert_terceros_legacy nunca lo busca ni lo encuentra por CUIT (paso 2
--     se saltea), asi que nunca se fusiona con nada por esa via.
-- El resto de los terceros (default cuit_no_exclusivo = false) se comportan
-- exactamente igual que antes -- sin cambios de comportamiento para el 99%
-- de los casos.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE terceros ADD COLUMN IF NOT EXISTS cuit_no_exclusivo BOOLEAN NOT NULL DEFAULT FALSE;
COMMENT ON COLUMN terceros.cuit_no_exclusivo IS
  'true: este tercero comparte legitimamente su CUIT con otros (entidad institucional multi-sede). Queda fuera de uq_terceros_cuit y upsert_terceros_legacy nunca lo vincula por CUIT.';

DROP INDEX IF EXISTS uq_terceros_cuit;
CREATE UNIQUE INDEX uq_terceros_cuit
    ON terceros (drogueria_id, cuit)
    WHERE cuit IS NOT NULL AND deleted_at IS NULL AND NOT cuit_no_exclusivo;

CREATE OR REPLACE FUNCTION upsert_terceros_legacy(
    p_drogueria_id   UUID,
    p_sistema_origen TEXT,
    p_entidad_legacy TEXT,      -- 'cliente' | 'proveedor' | 'transporte' | 'banco' | 'otro'
    p_filas          JSONB,     -- array de objetos: codigo_legacy, razon_social, cuit, tipo, cuit_no_exclusivo, ...
    p_usuario_id     UUID
) RETURNS TABLE (codigo_legacy TEXT, tercero_id UUID, accion TEXT)
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
  fila JSONB;
  v_tid UUID;
  v_accion TEXT;
  v_codigo_colisiona BOOLEAN;
  v_cuit_no_exclusivo BOOLEAN;
BEGIN
  FOR fila IN SELECT * FROM jsonb_array_elements(p_filas) LOOP
    v_cuit_no_exclusivo := coalesce((fila->>'cuit_no_exclusivo')::bool, FALSE);

    -- 1) clave de idempotencia
    SELECT m.tercero_id INTO v_tid FROM terceros_legacy_map m
     WHERE m.drogueria_id = p_drogueria_id AND m.sistema_origen = p_sistema_origen
       AND m.entidad_legacy = p_entidad_legacy AND m.codigo_legacy = fila->>'codigo_legacy'
     FOR UPDATE;
    v_accion := 'reusado';

    -- 2) misma empresa ya cargada bajo el otro rol -- se saltea por completo
    -- si la fila viene marcada cuit_no_exclusivo (0024): nunca se vincula por
    -- CUIT, siempre crea su propio tercero.
    IF v_tid IS NULL AND NOT v_cuit_no_exclusivo AND nullif(fila->>'cuit','') IS NOT NULL THEN
      SELECT t.id INTO v_tid FROM terceros t
       WHERE t.drogueria_id = p_drogueria_id AND t.cuit = fila->>'cuit' AND t.deleted_at IS NULL
         AND NOT t.cuit_no_exclusivo
       FOR UPDATE;
      IF v_tid IS NOT NULL THEN v_accion := 'vinculado'; END IF;
    END IF;

    -- 3) alta
    IF v_tid IS NULL THEN
      SELECT EXISTS (
        SELECT 1 FROM terceros t
         WHERE t.drogueria_id = p_drogueria_id
           AND t.codigo_interno = fila->>'codigo_legacy'
      ) INTO v_codigo_colisiona;

      INSERT INTO terceros (drogueria_id, codigo_interno, razon_social, cuit, cuit_no_exclusivo, created_by, updated_by)
      VALUES (
        p_drogueria_id,
        CASE WHEN v_codigo_colisiona THEN NULL ELSE fila->>'codigo_legacy' END,
        fila->>'razon_social',
        nullif(fila->>'cuit',''), v_cuit_no_exclusivo, p_usuario_id, p_usuario_id
      )
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

    -- 5) tabla de rol (id compartido) -- solo cliente/proveedor arman fila de
    -- rol (0023). transporte/banco/otro dejan el tercero sin rol.
    IF p_entidad_legacy = 'cliente' THEN
      INSERT INTO clientes (id, drogueria_id, tipo, activo, created_by, updated_by)
      VALUES (v_tid, p_drogueria_id, coalesce(fila->>'tipo','otro'), TRUE, p_usuario_id, p_usuario_id)
      ON CONFLICT (id) DO UPDATE SET tipo = excluded.tipo, activo = TRUE, updated_by = p_usuario_id;
    ELSIF p_entidad_legacy = 'proveedor' THEN
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

REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM anon;
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM authenticated;
GRANT  EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) TO service_role;

COMMENT ON FUNCTION upsert_terceros_legacy IS
  'Upsert idempotente del import legado. Desde 0024: filas con cuit_no_exclusivo=true en el JSON nunca se buscan/vinculan por CUIT (paso 2 se saltea) y quedan fuera de uq_terceros_cuit -- soporta entidades institucionales multi-sede con CUIT fiscal compartido.';
