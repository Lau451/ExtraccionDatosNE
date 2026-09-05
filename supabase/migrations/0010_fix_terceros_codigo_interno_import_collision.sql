-- =============================================================================
-- Fix: upsert_terceros_legacy — colisión de codigo_interno entre los espacios
-- de códigos legados de cliente y proveedor (D-TERCEROS-001, ver
-- docs/modulos/terceros/decisiones.md y openspec/changes/terceros-modelo/
-- tasks.md 9.13/12.3)
--
-- Descubierto en Fase 9 (terceros-modelo, PR5), documentado como xfail
-- intencional en
-- tests/imports/test_service.py::test_codigo_legacy_colisiona_entre_cliente_y_proveedor_produce_dos_terceros_distintos:
-- `terceros.uq_terceros_codigo` es UNIQUE(drogueria_id, codigo_interno) SIN
-- componente de entidad_legacy (0008_terceros_modelo.sql, sección 2). El RPC
-- solo desambigua colisiones vía terceros_legacy_map (por entidad_legacy) o
-- CUIT — nunca por codigo_interno. Cuando dos empresas DISTINTAS (sin CUIT en
-- común) comparten el mismo codigo_legacy en el CSV de clientes y en el de
-- proveedores, el segundo INSERT en `terceros` violaba uq_terceros_codigo y
-- el RPC entero fallaba, en vez de crear dos terceros distintos como exige
-- D1 (design.md).
--
-- Fix: en el paso 3 (alta) de upsert_terceros_legacy, antes del INSERT INTO
-- terceros, se verifica si codigo_interno = fila->>'codigo_legacy' ya existe
-- para OTRO tercero en esa drogueria_id. Si es así, se inserta con
-- codigo_interno = NULL en vez de fallar — uq_terceros_codigo ya tolera NULL
-- (índice UNIQUE estándar de Postgres, NULL no colisiona con NULL). El alta
-- nativa vía crear_tercero() puede setear codigo_interno manualmente más
-- adelante si hace falta desambiguar a mano. No se cambia ningún DDL: es
-- puramente CREATE OR REPLACE FUNCTION, mismo patrón que
-- 0009_fix_upsert_terceros_legacy_ambiguous_column.sql (incluye
-- #variable_conflict use_column, sin la cual v_codigo_colisiona chocaría con
-- toda referencia futura a una columna homónima).
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
      -- D-TERCEROS-001: si codigo_interno ya está tomado por OTRO tercero en
      -- esta drogueria (típicamente porque el mismo codigo_legacy aparece en
      -- el CSV de clientes y en el de proveedores para dos empresas
      -- distintas, sin CUIT en común), no fallamos uq_terceros_codigo — se
      -- inserta con codigo_interno = NULL en su lugar, preservando el alta
      -- de dos terceros independientes.
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
