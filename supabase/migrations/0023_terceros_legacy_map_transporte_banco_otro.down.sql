-- Down migration para 0023_terceros_legacy_map_transporte_banco_otro.sql
-- Vuelve el CHECK a solo cliente/proveedor y restaura el paso 5 de la RPC a
-- su forma binaria previa (0010). No borra filas transporte/banco/otro ya
-- cargadas con esta migracion activa -- si las hubiera, este down las deja
-- con un entidad_legacy que la constraint restaurada ya no permitiria
-- insertar de nuevo, pero las existentes no se tocan (el DROP/ADD CHECK de
-- Postgres no revalida filas ya insertadas... revalida SI: ALTER TABLE ADD
-- CONSTRAINT CHECK valida todas las filas existentes contra la nueva
-- condicion. Si hay filas transporte/banco/otro cargadas, este down FALLA a
-- proposito en vez de dejar datos inconsistentes con la constraint -- borralas
-- o resolvelas antes de bajar esta migracion.

ALTER TABLE terceros_legacy_map DROP CONSTRAINT IF EXISTS ck_tlm_entidad;
ALTER TABLE terceros_legacy_map ADD CONSTRAINT ck_tlm_entidad
  CHECK (entidad_legacy IN ('cliente','proveedor'));

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

REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM anon;
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM authenticated;
GRANT  EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) TO service_role;
