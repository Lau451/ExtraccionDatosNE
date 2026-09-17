-- =============================================================================
-- Migration 0023: terceros_legacy_map admite transporte/banco/otro
--
-- Contexto: la carga real del CSV legado de Nueva Era escopeo deliberadamente
-- solo cliente/proveedor (ver decisiones.md D-TERCEROS-001). Transporte(6),
-- Banco(3) y Otros(69) del legacy quedaron afuera porque ck_tlm_entidad solo
-- aceptaba 'cliente'/'proveedor'. Esta migracion amplia esa constraint para
-- poder trazarlos con el mismo mecanismo de import (terceros_legacy_map +
-- upsert_terceros_legacy), sin crearles ninguna fila de rol: un tercero puede
-- existir con identidad sola, sin clientes/proveedores asociado (ya soportado
-- por el modelo, ver base_de_datos.md).
--
-- Hallazgo critico antes de aplicar: el paso 5 de upsert_terceros_legacy
-- (0008/0009/0010) es un IF p_entidad_legacy = 'cliente' ... ELSE INSERT INTO
-- proveedores ... END IF -- binario. Ampliar solo el CHECK sin tocar esto
-- haria que transporte/banco/otro cayeran en el ELSE y se cargaran como
-- proveedor (con es_competidor=true por default), exactamente lo que NO se
-- quiere. Se corrige el paso 5 a IF/ELSIF/END IF explicito en la misma
-- migracion: cliente y proveedor arman su fila de rol como antes; cualquier
-- otro valor (transporte/banco/otro) no toca clientes ni proveedores, deja el
-- tercero solo con su identidad.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE terceros_legacy_map DROP CONSTRAINT IF EXISTS ck_tlm_entidad;
ALTER TABLE terceros_legacy_map ADD CONSTRAINT ck_tlm_entidad
  CHECK (entidad_legacy IN ('cliente','proveedor','transporte','banco','otro'));

CREATE OR REPLACE FUNCTION upsert_terceros_legacy(
    p_drogueria_id   UUID,
    p_sistema_origen TEXT,
    p_entidad_legacy TEXT,      -- 'cliente' | 'proveedor' | 'transporte' | 'banco' | 'otro'
    p_filas          JSONB,     -- array de objetos: codigo_legacy, razon_social, cuit, tipo, ...
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
      -- D-TERCEROS-001: si codigo_interno ya esta tomado por OTRO tercero en
      -- esta drogueria, no fallamos uq_terceros_codigo — se inserta con
      -- codigo_interno = NULL en su lugar.
      SELECT EXISTS (
        SELECT 1 FROM terceros t
         WHERE t.drogueria_id = p_drogueria_id
           AND t.codigo_interno = fila->>'codigo_legacy'
      ) INTO v_codigo_colisiona;

      INSERT INTO terceros (drogueria_id, codigo_interno, razon_social, cuit, created_by, updated_by)
      VALUES (
        p_drogueria_id,
        CASE WHEN v_codigo_colisiona THEN NULL ELSE fila->>'codigo_legacy' END,
        fila->>'razon_social',
        nullif(fila->>'cuit',''), p_usuario_id, p_usuario_id
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

    -- 5) tabla de rol (id compartido) — SOLO cliente/proveedor arman fila de
    -- rol. transporte/banco/otro (migracion 0023) dejan el tercero sin rol.
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
  'Upsert idempotente del import legado. Desde 0023 acepta tambien transporte/banco/otro en entidad_legacy, sin crear fila de rol para esos tres (paso 5 solo cubre cliente/proveedor).';
