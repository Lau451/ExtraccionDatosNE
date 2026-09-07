-- =============================================================================
-- Reversion manual de 0012_pcp_extras.sql
--
-- NO la ejecuta `supabase db push` (no es un archivo de migracion numerado
-- estandar); es un script para correr a mano si hace falta revertir.
--
-- Orden: RPC, luego politicas/RLS/triggers/GRANTs, luego las dos vistas
-- vuelven a su forma pre-0012 (leyendo pp.plazo_pago_dias directo), luego las
-- FKs diferidas de PR1 y las columnas nuevas de precios_proveedor, y por
-- ultimo las tablas nuevas (hijas antes que padres). plazo_pago_dias nunca se
-- toco (D5: sobrevive nullable) asi que no hace falta backfill inverso.
-- =============================================================================

-- ---------- M8: RPC ----------
DROP FUNCTION IF EXISTS upsert_pcp_legacy(UUID,TEXT,JSONB,UUID);

-- ---------- M7: politicas, RLS, triggers, GRANTs ----------
DROP POLICY IF EXISTS pcph_sel ON pcp_historial;
DROP POLICY IF EXISTS pcph_ins ON pcp_historial;

DROP POLICY IF EXISTS rpcp_sel ON reglas_pcp;
DROP POLICY IF EXISTS rpcp_ins ON reglas_pcp;
DROP POLICY IF EXISTS rpcp_upd ON reglas_pcp;
DROP POLICY IF EXISTS rpcp_del ON reglas_pcp;

DROP POLICY IF EXISTS pcplm_sel ON pcp_legacy_map;
DROP POLICY IF EXISTS pcplm_ins ON pcp_legacy_map;
DROP POLICY IF EXISTS pcplm_upd ON pcp_legacy_map;
DROP POLICY IF EXISTS pcplm_del ON pcp_legacy_map;

DROP POLICY IF EXISTS pcpc_sel ON pcp_consultas;
DROP POLICY IF EXISTS pcpc_ins ON pcp_consultas;
DROP POLICY IF EXISTS pcpc_upd ON pcp_consultas;
DROP POLICY IF EXISTS pcpc_del ON pcp_consultas;

DROP POLICY IF EXISTS pcpcr_sel ON pcp_consulta_renglones;
DROP POLICY IF EXISTS pcpcr_ins ON pcp_consulta_renglones;
DROP POLICY IF EXISTS pcpcr_upd ON pcp_consulta_renglones;
DROP POLICY IF EXISTS pcpcr_del ON pcp_consulta_renglones;

REVOKE ALL ON pcp_historial, reglas_pcp, pcp_legacy_map, pcp_consultas, pcp_consulta_renglones
  FROM service_role, authenticated;

DROP TRIGGER IF EXISTS trg_reglas_pcp_updated_at   ON reglas_pcp;
DROP TRIGGER IF EXISTS trg_pcp_consultas_updated_at ON pcp_consultas;

-- ---------- M6: vistas vuelven a la forma pre-0012 (post-0011) ----------
DROP VIEW IF EXISTS v_precios_especiales_vigentes;
CREATE VIEW v_precios_especiales_vigentes WITH (security_invoker = true) AS
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
    COALESCE(pp.plazo_pago_dias, (cp_prov.plazos_dias[1])::integer) AS plazo_pago_dias,
    pp.mantenimiento_hasta,
    pp.mantenimiento_hasta - CURRENT_DATE AS dias_restantes
FROM precios_proveedor pp
JOIN proveedores prov ON prov.id = pp.proveedor_id
JOIN terceros t_prov  ON t_prov.id = prov.id AND t_prov.drogueria_id = prov.drogueria_id
JOIN productos prod   ON prod.id = pp.producto_id
LEFT JOIN condiciones_pago cp_prov ON cp_prov.id = prov.condicion_pago_id
WHERE pp.activa = TRUE AND pp.mantenimiento_hasta >= CURRENT_DATE
ORDER BY pp.producto_id, pp.precio_unitario;

DROP VIEW IF EXISTS v_presupuesto_revision;
CREATE VIEW v_presupuesto_revision WITH (security_invoker = true) AS
SELECT
    p.id                        AS presupuesto_id,
    p.proceso_comercial_id,
    proc.nombre                 AS proceso,
    proc.clase,
    t_cli.razon_social          AS cliente,
    p.estado,
    pi.id                       AS presupuesto_item_id,
    ip.numero_renglon,
    ip.descripcion,
    ip.cantidad                 AS cantidad_solicitada,
    prod.nombre                 AS producto,
    pi.precio_unitario,
    pi.cantidad_ofertada,
    pi.monto_total,
    pi.metodo_precio,
    pi.costo_usado,
    pi.origen_costo,
    pi.precio_mercado_usado,
    pi.margen_resultante_pct,
    pi.stock_verificado,
    pi.stock_al_generar,
    pi.excluido,
    pi.motivo_exclusion,
    (pi.precio_ajustado_por IS NOT NULL) AS ajustado_por_humano,
    COALESCE(t_prov.nombre_fantasia, t_prov.razon_social) AS proveedor_compra,
    COALESCE(pp.plazo_pago_dias, (cp_prov.plazos_dias[1])::integer) AS plazo_pago_proveedor,
    (cp_cli.plazos_dias[1])::integer AS plazo_pago_cliente,
    pi.mantenimiento_hasta_usado,
    (pi.mantenimiento_hasta_usado IS NOT NULL
     AND proc.vencimiento IS NOT NULL
     AND pi.mantenimiento_hasta_usado < proc.vencimiento) AS alerta_mantenimiento
FROM presupuestos p
JOIN procesos_comerciales proc     ON proc.id = p.proceso_comercial_id
LEFT JOIN clientes cl              ON cl.id = proc.cliente_id
LEFT JOIN terceros t_cli           ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
LEFT JOIN condiciones_pago cp_cli  ON cp_cli.id = cl.condicion_pago_id
JOIN presupuesto_items pi          ON pi.presupuesto_id = p.id
JOIN items_proceso ip              ON ip.id = pi.item_proceso_id
LEFT JOIN productos prod           ON prod.id = pi.producto_id
LEFT JOIN precios_proveedor pp     ON pp.id = pi.precio_proveedor_id
LEFT JOIN proveedores prov         ON prov.id = pp.proveedor_id
LEFT JOIN terceros t_prov          ON t_prov.id = prov.id AND t_prov.drogueria_id = prov.drogueria_id
LEFT JOIN condiciones_pago cp_prov ON cp_prov.id = prov.condicion_pago_id
ORDER BY p.id, ip.numero_renglon;

-- ---------- M5b/M5: funcion de backfill, FKs y columnas nuevas de precios_proveedor ----------
DROP FUNCTION IF EXISTS backfill_condicion_pago_desde_plazo(UUID);
ALTER TABLE precios_proveedor DROP CONSTRAINT IF EXISTS fk_pp_condpago;
ALTER TABLE precios_proveedor DROP CONSTRAINT IF EXISTS fk_pp_formapago;
ALTER TABLE precios_proveedor DROP COLUMN IF EXISTS condicion_pago_id;
ALTER TABLE precios_proveedor DROP COLUMN IF EXISTS forma_pago_id;

-- ---------- M4b: FKs diferidas de PR1 ----------
ALTER TABLE pcp                    DROP CONSTRAINT IF EXISTS fk_pcp_regla;
ALTER TABLE pcp_renglones          DROP CONSTRAINT IF EXISTS fk_pcpr_regla;
ALTER TABLE pcp_renglon_resultados DROP CONSTRAINT IF EXISTS fk_ppr_consulta;

-- ---------- M4, M3, M2, M1: tablas (hijas antes que padres) ----------
DROP TABLE IF EXISTS pcp_consulta_renglones;
DROP TABLE IF EXISTS pcp_consultas;
DROP TABLE IF EXISTS pcp_legacy_map;
DROP TABLE IF EXISTS reglas_pcp;
DROP TABLE IF EXISTS pcp_historial;

NOTIFY pgrst, 'reload schema';
