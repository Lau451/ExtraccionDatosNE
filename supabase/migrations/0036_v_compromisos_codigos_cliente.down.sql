-- Down migration para 0036: restaura la definición de 0035 (sin cliente_codigo ni
-- cliente_codigos_legacy). Un reemplazo de vista no puede quitar columnas: DROP + CREATE.
-- Las vistas del proyecto no llevan GRANT propio (0032).

DROP VIEW v_compromisos_entregas;

CREATE VIEW v_compromisos_entregas WITH (security_invoker = true) AS
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
    plan.entregas_en_plan
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
  'Compromisos de entrega: una fila por ítem de entrega abierta (estado distinto de entregada/rechazada, mismo criterio que v_entregas_pendientes) de una OC exportada a Progress (exportado_at), vigente y no cancelada. situacion = vencida si la fecha planificada es anterior a hoy (hora Argentina), futura en otro caso (hoy cuenta como futura); dias_atraso >= 0. Solo ítems con cantidad_planificada > 0: las entregas reales de compras (cantidad_planificada = 0) no son compromisos. posicion_en_plan / entregas_en_plan: lugar de la entrega entre las entregas del plan de la OC (con algún ítem cantidad_planificada > 0, cualquier estado, por numero_entrega) y cuántas son. Agregada en 0032, ajustada en 0034 y 0035.';

NOTIFY pgrst, 'reload schema';
