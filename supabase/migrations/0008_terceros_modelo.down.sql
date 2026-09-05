-- =============================================================================
-- Reversión manual de 0008_terceros_modelo.sql
--
-- NO la ejecuta `supabase db push` (no es un archivo de migración numerado
-- estándar); es un script para correr a mano si hace falta revertir. Ver
-- openspec/changes/terceros-modelo/design.md, sección "Migration / Rollout":
-- segura mientras las 8 tablas nuevas sigan vacías. Con terceros ya cargados
-- de forma nativa, exportar antes de correr este script: direcciones,
-- contactos y catálogos no tienen destino en el esquema plano anterior.
--
-- Orden de ejecución: NO es un espejo línea a línea de M1-M10 en reversa,
-- porque eso rompería dependencias reales (p.ej. no se puede recrear una
-- vista que lee clientes.nombre antes de que esa columna vuelva a existir).
-- El orden real resuelve esas dependencias; el efecto neto revierte M1-M10.
-- =============================================================================

-- ---------- Reversión de M10: RPC ----------
DROP FUNCTION IF EXISTS upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID);

-- ---------- Reversión de M9: políticas, RLS, triggers de las 8 tablas nuevas ----------
DROP POLICY IF EXISTS terceros_sel ON terceros;
DROP POLICY IF EXISTS terceros_ins ON terceros;
DROP POLICY IF EXISTS terceros_upd ON terceros;
DROP POLICY IF EXISTS terceros_del ON terceros;

DROP POLICY IF EXISTS tdir_sel ON tercero_direcciones;
DROP POLICY IF EXISTS tdir_ins ON tercero_direcciones;
DROP POLICY IF EXISTS tdir_upd ON tercero_direcciones;
DROP POLICY IF EXISTS tdir_del ON tercero_direcciones;

DROP POLICY IF EXISTS du_sel ON direccion_usos;
DROP POLICY IF EXISTS du_ins ON direccion_usos;
DROP POLICY IF EXISTS du_upd ON direccion_usos;
DROP POLICY IF EXISTS du_del ON direccion_usos;

DROP POLICY IF EXISTS tc_sel ON terceros_contactos;
DROP POLICY IF EXISTS tc_ins ON terceros_contactos;
DROP POLICY IF EXISTS tc_upd ON terceros_contactos;
DROP POLICY IF EXISTS tc_del ON terceros_contactos;

DROP POLICY IF EXISTS tlm_sel ON terceros_legacy_map;
DROP POLICY IF EXISTS tlm_ins ON terceros_legacy_map;
DROP POLICY IF EXISTS tlm_upd ON terceros_legacy_map;
DROP POLICY IF EXISTS tlm_del ON terceros_legacy_map;

DROP POLICY IF EXISTS sec_sel ON sectores_contacto;
DROP POLICY IF EXISTS sec_ins ON sectores_contacto;
DROP POLICY IF EXISTS sec_upd ON sectores_contacto;
DROP POLICY IF EXISTS sec_del ON sectores_contacto;

DROP POLICY IF EXISTS cp_sel ON condiciones_pago;
DROP POLICY IF EXISTS cp_ins ON condiciones_pago;
DROP POLICY IF EXISTS cp_upd ON condiciones_pago;
DROP POLICY IF EXISTS cp_del ON condiciones_pago;

DROP POLICY IF EXISTS fp_sel ON formas_pago;
DROP POLICY IF EXISTS fp_ins ON formas_pago;
DROP POLICY IF EXISTS fp_upd ON formas_pago;
DROP POLICY IF EXISTS fp_del ON formas_pago;

REVOKE ALL ON terceros, tercero_direcciones, direccion_usos, terceros_contactos,
             terceros_legacy_map, sectores_contacto, condiciones_pago, formas_pago
  FROM service_role, authenticated;

DROP TRIGGER IF EXISTS trg_sectores_contacto_updated_at   ON sectores_contacto;
DROP TRIGGER IF EXISTS trg_condiciones_pago_updated_at    ON condiciones_pago;
DROP TRIGGER IF EXISTS trg_formas_pago_updated_at         ON formas_pago;
DROP TRIGGER IF EXISTS trg_terceros_updated_at            ON terceros;
DROP TRIGGER IF EXISTS trg_tercero_direcciones_updated_at ON tercero_direcciones;
DROP TRIGGER IF EXISTS trg_terceros_contactos_updated_at  ON terceros_contactos;

-- ---------- Reversión de M8: vistas WITH security_invoker ----------
DROP VIEW IF EXISTS v_presupuesto_revision;
DROP VIEW IF EXISTS v_matching_pendiente;
DROP VIEW IF EXISTS v_precios_especiales_vigentes;
DROP VIEW IF EXISTS v_renglones_ganados;
DROP VIEW IF EXISTS v_entregas_pendientes;
DROP VIEW IF EXISTS v_formato_para_prompt;
DROP VIEW IF EXISTS v_presupuesto_comercial;
DROP VIEW IF EXISTS v_calendario;
DROP VIEW IF EXISTS v_compras_vs_cotizado;

-- ---------- Reversión de M7: terceros_contactos; recrear cliente_contactos ----------
DROP TABLE IF EXISTS terceros_contactos;

CREATE TABLE IF NOT EXISTS cliente_contactos (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    cliente_id      UUID            NOT NULL,
    drogueria_id    UUID            NOT NULL,
    nombre          TEXT            NOT NULL,
    cargo           TEXT            NULL,
    email           TEXT            NULL,
    telefono        TEXT            NULL,
    es_principal    BOOLEAN         NOT NULL DEFAULT FALSE,
    notas           TEXT            NULL,
    activo          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
);
COMMENT ON COLUMN cliente_contactos.drogueria_id IS 'Denormalizado del cliente padre vía FK compuesta (cliente_id, drogueria_id) → clientes(id, drogueria_id). Evita JOIN en cada política RLS.';

ALTER TABLE cliente_contactos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cc_sel ON cliente_contactos;
CREATE POLICY cc_sel ON cliente_contactos FOR SELECT USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS cc_ins ON cliente_contactos;
CREATE POLICY cc_ins ON cliente_contactos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS cc_upd ON cliente_contactos;
CREATE POLICY cc_upd ON cliente_contactos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS cc_del ON cliente_contactos;
CREATE POLICY cc_del ON cliente_contactos FOR DELETE USING ((select es_superadmin()));

GRANT SELECT, INSERT, UPDATE, DELETE ON cliente_contactos TO service_role;
GRANT SELECT, INSERT, UPDATE          ON cliente_contactos TO authenticated;

-- ---------- Reversión de M6: direcciones y usos ----------
DROP TABLE IF EXISTS direccion_usos;
DROP TABLE IF EXISTS tercero_direcciones;

-- ---------- Reversión de M5: clientes / proveedores vuelven al esquema plano ----------
ALTER TABLE clientes
    DROP CONSTRAINT IF EXISTS fk_cli_tercero,
    DROP CONSTRAINT IF EXISTS fk_cli_condpago,
    DROP CONSTRAINT IF EXISTS fk_cli_formapago,
    DROP COLUMN IF EXISTS condicion_pago_id,
    DROP COLUMN IF EXISTS forma_pago_id,
    ADD  COLUMN IF NOT EXISTS nombre           TEXT NOT NULL DEFAULT '',
    ADD  COLUMN IF NOT EXISTS direccion        TEXT NULL,
    ADD  COLUMN IF NOT EXISTS ciudad           TEXT NULL,
    ADD  COLUMN IF NOT EXISTS provincia        TEXT NULL,
    ADD  COLUMN IF NOT EXISTS codigo_postal    TEXT NULL,
    ADD  COLUMN IF NOT EXISTS plazo_pago_dias  INTEGER NULL,
    ADD  COLUMN IF NOT EXISTS condiciones_pago TEXT NULL,
    ADD  COLUMN IF NOT EXISTS codigo_interno   TEXT NULL,
    ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE clientes ALTER COLUMN nombre DROP DEFAULT;
ALTER TABLE clientes ADD CONSTRAINT ck_clientes_plazo CHECK (plazo_pago_dias IS NULL OR plazo_pago_dias >= 0);
COMMENT ON COLUMN clientes.plazo_pago_dias  IS 'A cuántos días paga este cliente (30/60/90). Informativo para evaluar la conveniencia de una licitación.';
COMMENT ON COLUMN clientes.condiciones_pago IS 'Notas libres: "50% contra entrega", "paga con demora habitual", etc.';

ALTER TABLE proveedores
    DROP CONSTRAINT IF EXISTS fk_prov_tercero,
    DROP CONSTRAINT IF EXISTS fk_prov_condpago,
    DROP CONSTRAINT IF EXISTS fk_prov_formapago,
    DROP COLUMN IF EXISTS condicion_pago_id,
    DROP COLUMN IF EXISTS forma_pago_id,
    ADD  COLUMN IF NOT EXISTS codigo_interno   TEXT NULL,
    ADD  COLUMN IF NOT EXISTS razon_social     TEXT NOT NULL DEFAULT '',
    ADD  COLUMN IF NOT EXISTS nombre_comercial TEXT NULL,
    ADD  COLUMN IF NOT EXISTS cuit             TEXT NULL,
    ADD  COLUMN IF NOT EXISTS plazo_pago_dias  INTEGER NULL,
    ADD  COLUMN IF NOT EXISTS condiciones_pago TEXT NULL,
    ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE proveedores ALTER COLUMN razon_social DROP DEFAULT;
ALTER TABLE proveedores ADD CONSTRAINT ck_prov_plazo CHECK (plazo_pago_dias IS NULL OR plazo_pago_dias >= 0);
COMMENT ON COLUMN proveedores.codigo_interno  IS 'Código del sistema externo de la droguería. Distinto del id (clave interna de esta BD): permite el import idempotente.';
COMMENT ON COLUMN proveedores.plazo_pago_dias IS 'A cuántos días LE PAGAMOS a este proveedor (30/60/90). Informativo para el aprobador.';

-- NOTA: los valores de las columnas restauradas (nombre, razon_social, etc.)
-- no se recuperan: DROP COLUMN en M5 perdió esos datos. Este script solo
-- restaura la FORMA del esquema, consistente con "seguro mientras las 8
-- tablas nuevas sigan vacías" (design.md). Con datos nativos ya cargados en
-- terceros, hace falta un backfill manual antes de este DROP COLUMN original,
-- fuera del alcance de este script.

-- ---------- Reversión de M4: recrear las 9 vistas originales (ya sin security_invoker,
-- ahora que clientes/proveedores tienen de nuevo sus columnas planas) ----------
-- v_presupuesto_revision recrea la versión "final" en vivo (con el
-- enriquecimiento ajustado_por/usuarios de docs/schema/rls_final.sql), no la
-- base sin enriquecer de extractor_final.sql.
CREATE VIEW v_presupuesto_revision AS
SELECT
    p.id                        AS presupuesto_id,
    p.proceso_comercial_id,
    proc.nombre                 AS proceso,
    proc.clase,
    cl.nombre                   AS cliente,
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
    uaj.nombre                  AS ajustado_por,
    COALESCE(prov.nombre_comercial, prov.razon_social) AS proveedor_compra,
    COALESCE(pp.plazo_pago_dias, prov.plazo_pago_dias) AS plazo_pago_proveedor,
    cl.plazo_pago_dias          AS plazo_pago_cliente,
    pi.mantenimiento_hasta_usado,
    (pi.mantenimiento_hasta_usado IS NOT NULL
     AND proc.vencimiento IS NOT NULL
     AND pi.mantenimiento_hasta_usado < proc.vencimiento) AS alerta_mantenimiento
FROM presupuestos p
JOIN procesos_comerciales proc ON proc.id = p.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
JOIN presupuesto_items pi      ON pi.presupuesto_id = p.id
JOIN items_proceso ip          ON ip.id = pi.item_proceso_id
LEFT JOIN productos prod       ON prod.id = pi.producto_id
LEFT JOIN precios_proveedor pp ON pp.id = pi.precio_proveedor_id
LEFT JOIN proveedores prov     ON prov.id = pp.proveedor_id
LEFT JOIN usuarios uaj         ON uaj.id = pi.precio_ajustado_por
ORDER BY p.id, ip.numero_renglon;

ALTER VIEW v_presupuesto_revision SET (security_invoker = on);

CREATE VIEW v_matching_pendiente AS
SELECT
    ip.id                       AS item_proceso_id,
    ip.proceso_comercial_id,
    proc.nombre                 AS proceso,
    proc.clase,
    proc.cliente_id,
    cl.nombre                   AS cliente,
    ip.numero_renglon,
    ip.descripcion,
    ip.estado_matching,
    ip.confianza_matching,
    (SELECT COUNT(*) FROM matching_candidatos mc WHERE mc.item_proceso_id = ip.id) AS candidatos
FROM items_proceso ip
JOIN procesos_comerciales proc ON proc.id = ip.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
WHERE ip.estado_matching IN ('pendiente', 'sugerido')
  AND proc.estado IN ('abierto', 'presupuestado')
ORDER BY proc.vencimiento NULLS FIRST, ip.numero_renglon;

CREATE VIEW v_precios_especiales_vigentes AS
SELECT
    pp.id                       AS precio_proveedor_id,
    pp.drogueria_id,
    pp.producto_id,
    prod.nombre                 AS producto,
    pp.item_proceso_id,
    pp.precio_unitario,
    pp.cantidad_minima,
    pp.cantidad_maxima,
    COALESCE(prov.nombre_comercial, prov.razon_social) AS proveedor,
    COALESCE(pp.plazo_pago_dias, prov.plazo_pago_dias) AS plazo_pago_dias,
    pp.mantenimiento_hasta,
    pp.mantenimiento_hasta - CURRENT_DATE AS dias_restantes
FROM precios_proveedor pp
JOIN proveedores prov ON prov.id = pp.proveedor_id
JOIN productos prod   ON prod.id = pp.producto_id
WHERE pp.activa = TRUE AND pp.mantenimiento_hasta >= CURRENT_DATE
ORDER BY pp.producto_id, pp.precio_unitario;

CREATE VIEW v_renglones_ganados AS
SELECT
    c.proceso_comercial_id,
    proc.nombre                 AS proceso,
    cl.nombre                   AS cliente,
    oi.id                       AS oferta_item_id,
    oi.renglon_id,
    oi.descripcion,
    oi.precio_unitario,
    oi.cantidad_ofertada,
    oi.adjudicada               AS ganado_oficial,
    oi.adjudicacion_estimada    AS ganado_estimado,
    CASE WHEN oi.adjudicada THEN 'oficial'
         WHEN oi.adjudicacion_estimada THEN 'estimado' END AS nivel
FROM ofertas_items oi
JOIN comparativas c            ON c.id = oi.comparativa_id AND c.es_vigente = TRUE
JOIN procesos_comerciales proc ON proc.id = c.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
WHERE oi.es_drogueria_propia = TRUE
  AND (oi.adjudicada OR oi.adjudicacion_estimada);

CREATE VIEW v_entregas_pendientes AS
SELECT
    oc.numero_oc,
    cl.nombre AS cliente,
    e.numero_entrega,
    e.fecha_entrega_planificada,
    e.estado,
    CURRENT_DATE - e.fecha_entrega_planificada AS dias_atraso
FROM entregas_oc e
JOIN ordenes_compra oc ON oc.id = e.orden_compra_id
LEFT JOIN clientes cl  ON cl.id = oc.cliente_id
WHERE e.estado NOT IN ('entregada', 'rechazada');

CREATE VIEW v_formato_para_prompt AS
SELECT
    cf.cliente_id,
    cl.nombre AS cliente,
    cf.doc_type,
    cf.instrucciones_prompt,
    cf.archivo_ejemplo_path
FROM cliente_formato_documentos cf
JOIN clientes cl ON cl.id = cf.cliente_id
WHERE cf.activo = TRUE AND cf.instrucciones_prompt IS NOT NULL;

CREATE VIEW v_presupuesto_comercial AS
SELECT
    p.id                        AS presupuesto_id,
    p.proceso_comercial_id,
    proc.nombre                 AS proceso,
    proc.clase,
    cl.nombre                   AS cliente,
    p.estado,
    pi.id                       AS presupuesto_item_id,
    ip.numero_renglon,
    ip.descripcion,
    ip.cantidad                 AS cantidad_solicitada,
    prod.nombre                 AS producto,
    pi.precio_unitario,
    pi.cantidad_ofertada,
    pi.monto_total,
    pi.margen_resultante_pct,
    pi.precio_mercado_usado,
    pi.metodo_precio,
    pi.stock_verificado,
    pi.stock_al_generar,
    pi.excluido,
    pi.motivo_exclusion
FROM presupuestos p
JOIN procesos_comerciales proc ON proc.id = p.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
JOIN presupuesto_items pi      ON pi.presupuesto_id = p.id
JOIN items_proceso ip          ON ip.id = pi.item_proceso_id
LEFT JOIN productos prod       ON prod.id = pi.producto_id;

CREATE VIEW v_calendario AS
SELECT
    e.id                        AS evento_id,
    e.drogueria_id,
    e.tipo,
    e.titulo,
    e.estado,
    e.prioridad,
    e.origen,
    e.fecha_programada,
    e.fecha_limite,
    e.fecha_real,
    e.responsable_id,
    u.nombre                    AS responsable,
    e.proceso_comercial_id,
    e.cliente_id,
    cl.nombre                   AS cliente,
    CASE
        WHEN e.estado = ANY (ARRAY['completado','cancelado']) THEN FALSE
        WHEN e.fecha_limite IS NOT NULL AND e.fecha_limite < now() THEN TRUE
        ELSE FALSE
    END AS vencido
FROM eventos e
LEFT JOIN usuarios u  ON u.id = e.responsable_id
LEFT JOIN clientes cl ON cl.id = e.cliente_id
WHERE e.deleted_at IS NULL;

CREATE VIEW v_compras_vs_cotizado AS
SELECT
    cp.id                       AS compra_id,
    prod.nombre                 AS producto,
    COALESCE(prov.nombre_comercial, prov.razon_social) AS proveedor,
    cp.cantidad,
    cp.precio_unitario          AS precio_compra_real,
    pp.precio_unitario          AS precio_cotizado,
    (cp.precio_unitario - pp.precio_unitario) AS diferencia,
    cp.fecha_compra,
    pp.mantenimiento_hasta,
    (cp.fecha_compra > pp.mantenimiento_hasta) AS comprado_fuera_de_mantenimiento
FROM compras_proveedor cp
JOIN productos prod   ON prod.id = cp.producto_id
JOIN proveedores prov ON prov.id = cp.proveedor_id
LEFT JOIN precios_proveedor pp ON pp.id = cp.precio_proveedor_id
WHERE cp.precio_proveedor_id IS NOT NULL;

-- ---------- Reversión de M3, M2, M1 ----------
DROP TABLE IF EXISTS terceros_legacy_map;
DROP TABLE IF EXISTS terceros;
DROP TABLE IF EXISTS formas_pago;
DROP TABLE IF EXISTS condiciones_pago;
DROP TABLE IF EXISTS sectores_contacto;

NOTIFY pgrst, 'reload schema';
