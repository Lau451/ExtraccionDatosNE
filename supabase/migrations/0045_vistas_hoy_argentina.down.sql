-- Down migration para 0045: vuelve a CURRENT_DATE (UTC), las definiciones de 0012 y 0008.

CREATE OR REPLACE VIEW v_precios_especiales_vigentes WITH (security_invoker = true) AS
SELECT
    pp.id                       AS precio_proveedor_id,
    pp.drogueria_id,
    pp.producto_id,
    prod.nombre                 AS producto,
    pp.item_proceso_id,
    pp.precio_unitario,
    pp.cantidad_minima,
    pp.cantidad_maxima,
    COALESCE(t_prov.nombre_fantasia, t_prov.razon_social) AS proveedor,
    COALESCE((cp_pp.plazos_dias[1])::integer, pp.plazo_pago_dias, (cp_prov.plazos_dias[1])::integer) AS plazo_pago_dias,
    pp.mantenimiento_hasta,
    pp.mantenimiento_hasta - CURRENT_DATE AS dias_restantes
FROM precios_proveedor pp
JOIN proveedores prov ON prov.id = pp.proveedor_id
JOIN terceros t_prov  ON t_prov.id = prov.id AND t_prov.drogueria_id = prov.drogueria_id
JOIN productos prod   ON prod.id = pp.producto_id
LEFT JOIN condiciones_pago cp_prov ON cp_prov.id = prov.condicion_pago_id
LEFT JOIN condiciones_pago cp_pp   ON cp_pp.id = pp.condicion_pago_id
WHERE pp.activa = TRUE AND pp.mantenimiento_hasta >= CURRENT_DATE
ORDER BY pp.producto_id, pp.precio_unitario;

CREATE OR REPLACE VIEW v_entregas_pendientes WITH (security_invoker = true) AS
SELECT
    oc.numero_oc,
    t_cli.razon_social AS cliente,
    e.numero_entrega,
    e.fecha_entrega_planificada,
    e.estado,
    CURRENT_DATE - e.fecha_entrega_planificada AS dias_atraso
FROM entregas_oc e
JOIN ordenes_compra oc  ON oc.id = e.orden_compra_id
LEFT JOIN clientes cl   ON cl.id = oc.cliente_id
LEFT JOIN terceros t_cli ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
WHERE e.estado NOT IN ('entregada', 'rechazada');

NOTIFY pgrst, 'reload schema';
