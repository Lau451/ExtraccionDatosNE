-- Down migration para 0024_terceros_cuit_no_exclusivo.sql
-- Restaura uq_terceros_cuit e upsert_terceros_legacy a la forma de 0023, y
-- borra la columna. AVISO: si existen terceros con cuit_no_exclusivo=true
-- que comparten CUIT entre si, ALTER TABLE ADD CONSTRAINT (el indice unico
-- sin la condicion NOT cuit_no_exclusivo) va a fallar por violacion de
-- unicidad -- resolver esos duplicados antes de bajar esta migracion.

DROP INDEX IF EXISTS uq_terceros_cuit;
CREATE UNIQUE INDEX uq_terceros_cuit
    ON terceros (drogueria_id, cuit)
    WHERE cuit IS NOT NULL AND deleted_at IS NULL;

ALTER TABLE terceros DROP COLUMN IF EXISTS cuit_no_exclusivo;

CREATE OR REPLACE FUNCTION upsert_terceros_legacy(
    p_drogueria_id   UUID,
    p_sistema_origen TEXT,
    p_entidad_legacy TEXT,
    p_filas          JSONB,
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
    SELECT m.tercero_id INTO v_tid FROM terceros_legacy_map m
     WHERE m.drogueria_id = p_drogueria_id AND m.sistema_origen = p_sistema_origen
       AND m.entidad_legacy = p_entidad_legacy AND m.codigo_legacy = fila->>'codigo_legacy'
     FOR UPDATE;
    v_accion := 'reusado';

    IF v_tid IS NULL AND nullif(fila->>'cuit','') IS NOT NULL THEN
      SELECT t.id INTO v_tid FROM terceros t
       WHERE t.drogueria_id = p_drogueria_id AND t.cuit = fila->>'cuit' AND t.deleted_at IS NULL
       FOR UPDATE;
      IF v_tid IS NOT NULL THEN v_accion := 'vinculado'; END IF;
    END IF;

    IF v_tid IS NULL THEN
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

    INSERT INTO terceros_legacy_map (tercero_id, drogueria_id, sistema_origen,
                                     entidad_legacy, codigo_legacy, datos_legacy)
    VALUES (v_tid, p_drogueria_id, p_sistema_origen, p_entidad_legacy,
            fila->>'codigo_legacy', fila)
    ON CONFLICT (drogueria_id, sistema_origen, entidad_legacy, codigo_legacy) DO NOTHING;

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
