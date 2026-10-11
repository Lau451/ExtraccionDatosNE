-- =============================================================================
-- Migration 0033: cierre a nivel DB de la carrera exportación vs replanificado
-- (oc-export-progress, follow-up de la review de T3; design.md D7)
--
-- El chequeo D7 de oc_entregas.planificar_entregas es read-then-write y el
-- replanificado son varios statements (DELETE entregas_oc, INSERT entregas_oc +
-- entregas_oc_items, UPDATE ordenes_compra.cantidad_entregas): una exportación
-- concurrente podía dejar el CSV con el plan viejo. Se cierra con:
--
-- 1. hash_plan_oc(p_orden_compra_id): md5 canónico del plan (entregas + items
--    ordenados por numero_entrega / oc_item_id, con fecha y cantidad). Es la
--    ÚNICA definición de "el plan": el service la llama al leer y
--    marcar_oc_exportada la recalcula al marcar.
-- 2. marcar_oc_exportada(...): CAS atómico. Bloquea la OC FOR UPDATE, verifica
--    exportado_at IS NULL y que el hash actual sea el que el service leyó, y
--    recién entonces escribe las tres columnas exportado_*. Devuelve 'ok',
--    'ya_exportada', 'plan_cambiado' o 'no_encontrada'. SECURITY INVOKER, solo
--    service_role (mismo criterio que upsert_terceros_legacy, 0008).
-- 3. trg_oc_exportada_congela_plan + triggers en entregas_oc y
--    entregas_oc_items (BEFORE INSERT/UPDATE/DELETE): bloquean la OC FOR UPDATE
--    y levantan SQLSTATE 'OC409' si exportado_at IS NOT NULL. Solo se disparan
--    ante cambios del PLAN. NO bloquean los flujos legítimos posteriores a la
--    exportación: compras.crear_entrega registra entregas reales (INSERT con
--    fecha_entrega_real y cantidad_planificada = 0) y los cambios de
--    estado / cantidad_entregada / lote / observaciones son UPDATE de columnas
--    que no son del plan. Por eso se considera plan: entregas_oc con
--    estado 'pendiente' y fecha_entrega_real NULL (INSERT/DELETE) y cambios de
--    orden_compra_id / numero_entrega / fecha_entrega_planificada (UPDATE);
--    entregas_oc_items con cantidad_planificada > 0 (INSERT/DELETE) y cambios de
--    entrega_oc_id / oc_item_id / cantidad_planificada (UPDATE).
--    La función es SECURITY DEFINER (con search_path fijo) para que el bloqueo
--    de la OC no dependa de la RLS de ordenes_compra de quien escribe.
-- =============================================================================

CREATE OR REPLACE FUNCTION hash_plan_oc(p_orden_compra_id UUID)
RETURNS TEXT
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT md5(COALESCE(string_agg(
        e.numero_entrega::text
        || '|' || COALESCE(to_char(e.fecha_entrega_planificada, 'YYYY-MM-DD'), '')
        || '|' || COALESCE(ei.oc_item_id::text, '')
        || '|' || COALESCE(ei.cantidad_planificada::text, ''),
        E'\n' ORDER BY e.numero_entrega, ei.oc_item_id
    ), ''))
    FROM entregas_oc e
    LEFT JOIN entregas_oc_items ei
           ON ei.entrega_oc_id = e.id AND ei.drogueria_id = e.drogueria_id
    WHERE e.orden_compra_id = p_orden_compra_id;
$$;

COMMENT ON FUNCTION hash_plan_oc(UUID) IS
  'md5 canónico del plan de entregas de una OC (numero_entrega, fecha planificada, oc_item_id, cantidad_planificada, ordenados). Única definición de "el plan" para marcar_oc_exportada y el service de exportación. Agregada en 0033.';

CREATE OR REPLACE FUNCTION marcar_oc_exportada(
    p_orden_compra_id UUID,
    p_drogueria_id    UUID,
    p_usuario_id      UUID,
    p_archivo         TEXT,
    p_plan_hash       TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_exportado_at TIMESTAMPTZ;
BEGIN
    SELECT exportado_at INTO v_exportado_at
      FROM ordenes_compra
     WHERE id = p_orden_compra_id AND drogueria_id = p_drogueria_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RETURN 'no_encontrada';
    END IF;
    IF v_exportado_at IS NOT NULL THEN
        RETURN 'ya_exportada';
    END IF;
    IF hash_plan_oc(p_orden_compra_id) IS DISTINCT FROM p_plan_hash THEN
        RETURN 'plan_cambiado';
    END IF;

    UPDATE ordenes_compra
       SET exportado_at = now(),
           exportado_por = p_usuario_id,
           archivo_exportado = p_archivo
     WHERE id = p_orden_compra_id AND drogueria_id = p_drogueria_id;
    RETURN 'ok';
END;
$$;

COMMENT ON FUNCTION marcar_oc_exportada(UUID, UUID, UUID, TEXT, TEXT) IS
  'CAS de la exportación a Progress: con la OC bloqueada FOR UPDATE, verifica exportado_at IS NULL y que hash_plan_oc coincida con p_plan_hash antes de marcar exportado_at/exportado_por/archivo_exportado. Devuelve ok | ya_exportada | plan_cambiado | no_encontrada. Agregada en 0033.';

REVOKE EXECUTE ON FUNCTION hash_plan_oc(UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION hash_plan_oc(UUID) FROM anon;
REVOKE EXECUTE ON FUNCTION hash_plan_oc(UUID) FROM authenticated;
GRANT  EXECUTE ON FUNCTION hash_plan_oc(UUID) TO service_role;
REVOKE EXECUTE ON FUNCTION marcar_oc_exportada(UUID,UUID,UUID,TEXT,TEXT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION marcar_oc_exportada(UUID,UUID,UUID,TEXT,TEXT) FROM anon;
REVOKE EXECUTE ON FUNCTION marcar_oc_exportada(UUID,UUID,UUID,TEXT,TEXT) FROM authenticated;
GRANT  EXECUTE ON FUNCTION marcar_oc_exportada(UUID,UUID,UUID,TEXT,TEXT) TO service_role;

CREATE OR REPLACE FUNCTION trg_oc_exportada_congela_plan()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_oc_id        UUID;
    v_cambia_plan  BOOLEAN := FALSE;
    v_exportado_at TIMESTAMPTZ;
BEGIN
    IF TG_TABLE_NAME = 'entregas_oc' THEN
        IF TG_OP = 'INSERT' THEN
            v_oc_id := NEW.orden_compra_id;
            v_cambia_plan := NEW.estado = 'pendiente' AND NEW.fecha_entrega_real IS NULL;
        ELSIF TG_OP = 'DELETE' THEN
            v_oc_id := OLD.orden_compra_id;
            v_cambia_plan := OLD.estado = 'pendiente' AND OLD.fecha_entrega_real IS NULL;
        ELSE
            v_oc_id := OLD.orden_compra_id;
            v_cambia_plan :=
                (OLD.orden_compra_id, OLD.numero_entrega, OLD.fecha_entrega_planificada)
                IS DISTINCT FROM
                (NEW.orden_compra_id, NEW.numero_entrega, NEW.fecha_entrega_planificada);
        END IF;
    ELSE  -- entregas_oc_items
        IF TG_OP = 'INSERT' THEN
            v_cambia_plan := NEW.cantidad_planificada > 0;
            SELECT orden_compra_id INTO v_oc_id FROM entregas_oc WHERE id = NEW.entrega_oc_id;
        ELSIF TG_OP = 'DELETE' THEN
            v_cambia_plan := OLD.cantidad_planificada > 0;
            -- En un DELETE en cascada desde entregas_oc la entrega padre ya no existe:
            -- v_oc_id queda NULL y no hay nada que bloquear (el DELETE de la entrega ya
            -- pasó por este mismo guard).
            SELECT orden_compra_id INTO v_oc_id FROM entregas_oc WHERE id = OLD.entrega_oc_id;
        ELSE
            v_cambia_plan :=
                (OLD.entrega_oc_id, OLD.oc_item_id, OLD.cantidad_planificada)
                IS DISTINCT FROM
                (NEW.entrega_oc_id, NEW.oc_item_id, NEW.cantidad_planificada);
            SELECT orden_compra_id INTO v_oc_id FROM entregas_oc WHERE id = OLD.entrega_oc_id;
        END IF;
    END IF;

    IF v_cambia_plan AND v_oc_id IS NOT NULL THEN
        SELECT exportado_at INTO v_exportado_at
          FROM ordenes_compra
         WHERE id = v_oc_id
           FOR UPDATE;
        IF v_exportado_at IS NOT NULL THEN
            RAISE EXCEPTION 'La orden de compra ya fue exportada a Progress -- no se puede replanificar.'
                USING ERRCODE = 'OC409';
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION trg_oc_exportada_congela_plan() IS
  'Guard de entregas_oc / entregas_oc_items: bloquea la OC FOR UPDATE y rechaza (SQLSTATE OC409) todo cambio del PLAN de una OC con exportado_at. No toca los registros de entregas reales ni los cambios de estado. Agregada en 0033.';

REVOKE EXECUTE ON FUNCTION trg_oc_exportada_congela_plan() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_eoc_congela_plan ON entregas_oc;
CREATE TRIGGER trg_eoc_congela_plan
    BEFORE INSERT OR UPDATE OR DELETE ON entregas_oc
    FOR EACH ROW EXECUTE FUNCTION trg_oc_exportada_congela_plan();

DROP TRIGGER IF EXISTS trg_eoci_congela_plan ON entregas_oc_items;
CREATE TRIGGER trg_eoci_congela_plan
    BEFORE INSERT OR UPDATE OR DELETE ON entregas_oc_items
    FOR EACH ROW EXECUTE FUNCTION trg_oc_exportada_congela_plan();

NOTIFY pgrst, 'reload schema';
