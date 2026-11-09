-- 0045: "hoy" en hora argentina en las vistas de precios vigentes y entregas pendientes.
--
-- CURRENT_DATE es la fecha UTC de Supabase: entre las 21:00 y las 24:00 (UTC-3)
-- ya es mañana, así que v_precios_especiales_vigentes mostraba un
-- dias_restantes de menos y escondía los precios que vencen hoy, y
-- v_entregas_pendientes sumaba un día de atraso. Mismo criterio que
-- v_compromisos_entregas (0032). Las columnas no cambian de nombre ni de tipo,
-- así que CREATE OR REPLACE conserva dependencias y permisos;
-- WITH (security_invoker = true) se repite para no perderlo.

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
    pp.mantenimiento_hasta - (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS dias_restantes
FROM precios_proveedor pp
JOIN proveedores prov ON prov.id = pp.proveedor_id
JOIN terceros t_prov  ON t_prov.id = prov.id AND t_prov.drogueria_id = prov.drogueria_id
JOIN productos prod   ON prod.id = pp.producto_id
LEFT JOIN condiciones_pago cp_prov ON cp_prov.id = prov.condicion_pago_id
LEFT JOIN condiciones_pago cp_pp   ON cp_pp.id = pp.condicion_pago_id
WHERE pp.activa = TRUE AND pp.mantenimiento_hasta >= (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
ORDER BY pp.producto_id, pp.precio_unitario;

CREATE OR REPLACE VIEW v_entregas_pendientes WITH (security_invoker = true) AS
SELECT
    oc.numero_oc,
    t_cli.razon_social AS cliente,
    e.numero_entrega,
    e.fecha_entrega_planificada,
    e.estado,
    (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date - e.fecha_entrega_planificada AS dias_atraso
FROM entregas_oc e
JOIN ordenes_compra oc  ON oc.id = e.orden_compra_id
LEFT JOIN clientes cl   ON cl.id = oc.cliente_id
LEFT JOIN terceros t_cli ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
WHERE e.estado NOT IN ('entregada', 'rechazada');

NOTIFY pgrst, 'reload schema';
