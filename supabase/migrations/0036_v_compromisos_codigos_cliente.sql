-- =============================================================================
-- 0036: v_compromisos_entregas con los códigos del cliente, para que la agenda
-- de compromisos busque por código además de por razón social y número de OC.
--
-- cliente_codigo: terceros.codigo_interno (el "Código interno" de Terceros).
-- cliente_codigos_legacy: códigos de Progress del cliente en terceros_legacy_map
-- (entidad_legacy = 'cliente'). Un cliente puede tener varios, por eso es un
-- array ordenado; '{}' si no tiene ninguno.
--
-- Columnas nuevas al final: la vista solo admite agregar columnas al final con
-- un reemplazo. Mismo security_invoker = true: la subconsulta lee
-- terceros_legacy_map con la RLS de quien consulta (tlm_sel, mismo tenant).
-- =============================================================================

CREATE OR REPLACE VIEW v_compromisos_entregas WITH (security_invoker = true) AS
SELECT
    oc.drogueria_id,
    oc.id AS orden_compra_id,
    oc.numero_oc,
    oc.version_numero,
    oc.exportado_at,
    t.razon_social AS cliente,
    e.id AS entrega_oc_id,
    e.numero_entrega,
    e.fecha_entrega_planificada,
    oi.numero_renglon,
    p.codigo_interno AS codigo_articulo,
    oi.descripcion,
    ei.cantidad_planificada,
    CASE WHEN e.fecha_entrega_planificada
              < (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
         THEN 'vencida' ELSE 'futura' END AS situacion,
    GREATEST((now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
             - e.fecha_entrega_planificada, 0) AS dias_atraso,
    plan.posicion_en_plan,
    plan.entregas_en_plan,
    t.codigo_interno AS cliente_codigo,
    COALESCE(
        (SELECT array_agg(tlm.codigo_legacy ORDER BY tlm.codigo_legacy)
         FROM terceros_legacy_map tlm
         WHERE tlm.tercero_id = t.id
           AND tlm.drogueria_id = t.drogueria_id
           AND tlm.entidad_legacy = 'cliente'),
        '{}'::text[]
    ) AS cliente_codigos_legacy
FROM entregas_oc e
JOIN ordenes_compra oc    ON oc.id = e.orden_compra_id AND oc.drogueria_id = e.drogueria_id
JOIN entregas_oc_items ei ON ei.entrega_oc_id = e.id AND ei.drogueria_id = e.drogueria_id
JOIN oc_items oi          ON oi.id = ei.oc_item_id AND oi.drogueria_id = ei.drogueria_id
JOIN (
    SELECT
        ep.id,
        (row_number() OVER (PARTITION BY ep.orden_compra_id ORDER BY ep.numero_entrega))::int
            AS posicion_en_plan,
        (count(*) OVER (PARTITION BY ep.orden_compra_id))::int AS entregas_en_plan
    FROM entregas_oc ep
    WHERE EXISTS (
        SELECT 1 FROM entregas_oc_items eip
        WHERE eip.entrega_oc_id = ep.id
          AND eip.drogueria_id = ep.drogueria_id
          AND eip.cantidad_planificada > 0
    )
) plan                    ON plan.id = e.id
LEFT JOIN productos p     ON p.id = oi.producto_id AND p.drogueria_id = oi.drogueria_id
LEFT JOIN terceros t      ON t.id = oc.cliente_id AND t.drogueria_id = oc.drogueria_id
WHERE oc.exportado_at IS NOT NULL
  AND oc.deleted_at IS NULL
  AND oc.es_vigente
  AND oc.estado <> 'cancelada'
  AND e.estado NOT IN ('entregada', 'rechazada')
  AND ei.cantidad_planificada > 0;

COMMENT ON VIEW v_compromisos_entregas IS
  'Compromisos de entrega: una fila por ítem de entrega abierta (estado distinto de entregada/rechazada, mismo criterio que v_entregas_pendientes) de una OC exportada a Progress (exportado_at), vigente y no cancelada. situacion = vencida si la fecha planificada es anterior a hoy (hora Argentina), futura en otro caso (hoy cuenta como futura); dias_atraso >= 0. Solo ítems con cantidad_planificada > 0: las entregas reales de compras (cantidad_planificada = 0) no son compromisos. posicion_en_plan / entregas_en_plan: lugar de la entrega entre las entregas del plan de la OC (con algún ítem cantidad_planificada > 0, cualquier estado, por numero_entrega) y cuántas son. cliente_codigo: terceros.codigo_interno del cliente; cliente_codigos_legacy: sus códigos de Progress (terceros_legacy_map, entidad cliente, ordenados; vacío si no tiene). Agregada en 0032, ajustada en 0034, 0035 y 0036.';

NOTIFY pgrst, 'reload schema';
