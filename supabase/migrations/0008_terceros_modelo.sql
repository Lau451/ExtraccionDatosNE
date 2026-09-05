-- =============================================================================
-- Migration 0008: modelo de terceros
--
-- Reescritura clean-slate (0 filas en producción): unifica la identidad de
-- clientes y proveedores en una tabla `terceros` compartida. `clientes` y
-- `proveedores` pasan a ser tablas de rol angostas cuyo `id` es a la vez PK y
-- FK compuesta hacia `terceros(id, drogueria_id)`. Ver
-- openspec/changes/terceros-modelo/design.md para las decisiones D1-D6.
--
-- Un solo archivo = una sola transacción (`supabase db push` envuelve cada
-- migración en una transacción propia; no se agregan BEGIN/COMMIT explícitos).
--
-- Pasos (M0-M10):
--   M0  Guard de versión de Postgres (>=15, requerida por WITH security_invoker)
--   M1  Catálogos: sectores_contacto, condiciones_pago, formas_pago
--   M2  terceros
--   M3  terceros_legacy_map
--   M4  DROP de las 9 vistas que dependen de columnas eliminadas en M5
--   M5  ALTER TABLE clientes / proveedores (columnas + FKs a terceros/catálogos)
--   M6  tercero_direcciones + direccion_usos
--   M7  terceros_contactos; DROP TABLE cliente_contactos
--   M8  Recrear las 9 vistas de M4, WITH (security_invoker = true)
--   M9  Triggers de updated_at, RLS + políticas, GRANTs, NOTIFY pgrst
--   M10 RPC upsert_terceros_legacy (import legado idempotente)
-- =============================================================================

-- =============================================================================
-- M0 — Guard de versión de Postgres
-- WITH (security_invoker = true) en vistas requiere PostgreSQL 15+. La versión
-- en vivo no se pudo verificar en el momento del diseño (ver design.md, Open
-- Questions); en vez de asumirla, la migración la impone y aborta con un
-- mensaje accionable si no se cumple, en lugar de crear vistas que evadirían
-- RLS silenciosamente.
-- =============================================================================
DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'terceros-modelo requiere PostgreSQL 15+ para WITH (security_invoker = true); '
                    'version detectada: %', current_setting('server_version');
  END IF;
END $$;

-- =============================================================================
-- M1 — Catálogos comerciales por droguería
-- =============================================================================
CREATE TABLE IF NOT EXISTS sectores_contacto (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,
    descripcion     TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_sec_id_drog  UNIQUE (id, drogueria_id),
    CONSTRAINT uq_sec_nombre   UNIQUE (drogueria_id, nombre),
    CONSTRAINT fk_sec_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON TABLE sectores_contacto IS 'Catálogo por droguería de sectores de contacto (compras, farmacia, tesorería...) para clasificar terceros_contactos.';

CREATE TABLE IF NOT EXISTS condiciones_pago (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,                       -- '30/60/90', 'contado'
    plazos_dias     SMALLINT[]  NOT NULL DEFAULT '{}'::smallint[],
    descripcion     TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_cp_id_drog   UNIQUE (id, drogueria_id),
    CONSTRAINT uq_cp_nombre    UNIQUE (drogueria_id, nombre),
    CONSTRAINT ck_cp_plazos    CHECK (0 <= ALL (plazos_dias)),
    CONSTRAINT fk_cp_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON COLUMN condiciones_pago.plazos_dias IS
  'Reemplaza plazo_pago_dias (INTEGER) de clientes/proveedores: un pago en cuotas se expresa como {30,60,90}.';

CREATE TABLE IF NOT EXISTS formas_pago (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,
    tipo            TEXT        NOT NULL DEFAULT 'otro',
    descripcion     TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_fp_id_drog   UNIQUE (id, drogueria_id),
    CONSTRAINT uq_fp_nombre    UNIQUE (drogueria_id, nombre),
    CONSTRAINT ck_fp_tipo      CHECK (tipo IN ('transferencia','cheque','echeq','efectivo','deposito','otro')),
    CONSTRAINT fk_fp_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);

-- =============================================================================
-- M2 — terceros
-- =============================================================================
CREATE TABLE IF NOT EXISTS terceros (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    codigo_interno  TEXT        NULL,
    razon_social    TEXT        NOT NULL,
    nombre_fantasia TEXT        NULL,
    cuit            TEXT        NULL,
    email           TEXT        NULL,
    telefono        TEXT        NULL,
    sitio_web       TEXT        NULL,
    notas           TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_by      UUID        NULL,
    updated_by      UUID        NULL,
    deleted_at      TIMESTAMPTZ NULL,
    deleted_by      UUID        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_terceros_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT uq_terceros_codigo  UNIQUE (drogueria_id, codigo_interno),
    CONSTRAINT ck_terceros_cuit    CHECK (cuit IS NULL OR cuit ~ '^[0-9]{11}$'),
    CONSTRAINT fk_terceros_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_terceros_createdby FOREIGN KEY (created_by) REFERENCES usuarios (id),
    CONSTRAINT fk_terceros_updatedby FOREIGN KEY (updated_by) REFERENCES usuarios (id),
    CONSTRAINT fk_terceros_deletedby FOREIGN KEY (deleted_by) REFERENCES usuarios (id)
);
COMMENT ON TABLE terceros IS 'Identidad única de cualquier tercero (cliente y/o proveedor) por droguería. clientes/proveedores son tablas de rol angostas cuyo id comparte identidad con esta.';

-- Un CUIT identifica una sola empresa viva por droguería. Parcial: permite CUIT NULL repetido
-- y no bloquea recrear un tercero borrado lógicamente.
CREATE UNIQUE INDEX IF NOT EXISTS uq_terceros_cuit
    ON terceros (drogueria_id, cuit)
    WHERE cuit IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_terceros_drog_activo ON terceros (drogueria_id) WHERE activo AND deleted_at IS NULL;

-- =============================================================================
-- M3 — terceros_legacy_map
-- Clave de idempotencia del import legado (D1): el espacio de códigos de
-- clientes y el de proveedores del sistema legado son independientes y pueden
-- colisionar entre sí, por eso la clave incluye entidad_legacy.
-- =============================================================================
CREATE TABLE IF NOT EXISTS terceros_legacy_map (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    tercero_id      UUID        NOT NULL,
    drogueria_id    UUID        NOT NULL,
    sistema_origen  TEXT        NOT NULL DEFAULT 'legacy',
    entidad_legacy  TEXT        NOT NULL,
    codigo_legacy   TEXT        NOT NULL,
    datos_legacy    JSONB       NULL,
    importado_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_tlm_id_drog  UNIQUE (id, drogueria_id),
    CONSTRAINT uq_tlm_codigo   UNIQUE (drogueria_id, sistema_origen, entidad_legacy, codigo_legacy),
    CONSTRAINT ck_tlm_entidad  CHECK (entidad_legacy IN ('cliente','proveedor')),
    CONSTRAINT fk_tlm_tercero  FOREIGN KEY (tercero_id, drogueria_id)
                               REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_tlm_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON CONSTRAINT uq_tlm_codigo ON terceros_legacy_map IS
  'Clave de idempotencia del import: el espacio de codigos de clientes y el de proveedores del sistema legado son independientes y pueden colisionar entre si.';

-- =============================================================================
-- M4 — DROP de las 9 vistas que dependen de columnas eliminadas en M5
-- Bloqueante: v_presupuesto_revision, v_matching_pendiente, v_renglones_ganados,
-- v_entregas_pendientes, v_formato_para_prompt, v_presupuesto_comercial y
-- v_calendario seleccionan cl.nombre; v_precios_especiales_vigentes y
-- v_compras_vs_cotizado seleccionan prov.razon_social/prov.nombre_comercial
-- (v_precios_especiales_vigentes también prov.plazo_pago_dias).
-- Corrección post-diseño: design.md (D6) solo relevó 5 de estas 9 vistas;
-- verificado en vivo contra pg_class/pg_get_viewdef antes de aplicar. Sin
-- este DROP previo, el ALTER TABLE ... DROP COLUMN de M5 falla por
-- dependencia y la migración entera revierte.
-- =============================================================================
DROP VIEW IF EXISTS v_presupuesto_revision;
DROP VIEW IF EXISTS v_matching_pendiente;
DROP VIEW IF EXISTS v_precios_especiales_vigentes;
DROP VIEW IF EXISTS v_renglones_ganados;
DROP VIEW IF EXISTS v_entregas_pendientes;
DROP VIEW IF EXISTS v_formato_para_prompt;
DROP VIEW IF EXISTS v_presupuesto_comercial;
DROP VIEW IF EXISTS v_calendario;
DROP VIEW IF EXISTS v_compras_vs_cotizado;

-- =============================================================================
-- M5 — clientes / proveedores como tablas de rol
-- =============================================================================
ALTER TABLE clientes
    DROP COLUMN IF EXISTS nombre,
    DROP COLUMN IF EXISTS direccion,
    DROP COLUMN IF EXISTS ciudad,
    DROP COLUMN IF EXISTS provincia,
    DROP COLUMN IF EXISTS codigo_postal,
    DROP COLUMN IF EXISTS plazo_pago_dias,
    DROP COLUMN IF EXISTS condiciones_pago,
    DROP COLUMN IF EXISTS codigo_interno,                 -- arrastra uq_cli_codigo si existiera
    ADD  COLUMN IF NOT EXISTS condicion_pago_id UUID NULL,
    ADD  COLUMN IF NOT EXISTS forma_pago_id     UUID NULL,
    ALTER COLUMN id DROP DEFAULT;                          -- el id lo provee terceros, no gen_random_uuid()

ALTER TABLE clientes
    ADD CONSTRAINT fk_cli_tercero   FOREIGN KEY (id, drogueria_id)
                                    REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_cli_condpago  FOREIGN KEY (condicion_pago_id, drogueria_id)
                                    REFERENCES condiciones_pago (id, drogueria_id),
    ADD CONSTRAINT fk_cli_formapago FOREIGN KEY (forma_pago_id, drogueria_id)
                                    REFERENCES formas_pago (id, drogueria_id);

-- Sobreviven: id, drogueria_id, tipo (+ck_clientes_tipo), activo, created_by, updated_by,
-- deleted_at, deleted_by, created_at, updated_at, uq_cli_id_drog.

ALTER TABLE proveedores
    DROP COLUMN IF EXISTS codigo_interno,
    DROP COLUMN IF EXISTS razon_social,
    DROP COLUMN IF EXISTS nombre_comercial,
    DROP COLUMN IF EXISTS cuit,
    DROP COLUMN IF EXISTS plazo_pago_dias,
    DROP COLUMN IF EXISTS condiciones_pago,
    ADD  COLUMN IF NOT EXISTS condicion_pago_id UUID NULL,
    ADD  COLUMN IF NOT EXISTS forma_pago_id     UUID NULL,
    ALTER COLUMN id DROP DEFAULT;

ALTER TABLE proveedores
    ADD CONSTRAINT fk_prov_tercero   FOREIGN KEY (id, drogueria_id)
                                     REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_prov_condpago  FOREIGN KEY (condicion_pago_id, drogueria_id)
                                     REFERENCES condiciones_pago (id, drogueria_id),
    ADD CONSTRAINT fk_prov_formapago FOREIGN KEY (forma_pago_id, drogueria_id)
                                     REFERENCES formas_pago (id, drogueria_id);

-- Sobreviven: id, drogueria_id, tipo (+ck_prov_tipo), es_competidor, es_proveedor_compra,
-- activo, auditoría, uq_prov_id_drog.

-- =============================================================================
-- M6 — Direcciones y usos
-- =============================================================================
CREATE TABLE IF NOT EXISTS tercero_direcciones (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    tercero_id      UUID        NOT NULL,
    drogueria_id    UUID        NOT NULL,
    etiqueta        TEXT        NULL,
    calle           TEXT        NOT NULL,
    numero          TEXT        NULL,
    piso_depto      TEXT        NULL,
    ciudad          TEXT        NULL,
    provincia       TEXT        NULL,
    codigo_postal   TEXT        NULL,
    pais            TEXT        NOT NULL DEFAULT 'AR',
    observaciones   TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_tdir_id_drog    UNIQUE (id, drogueria_id),
    CONSTRAINT uq_tdir_id_tercero UNIQUE (id, tercero_id),   -- destino de fk_du_dir_tercero
    CONSTRAINT fk_tdir_tercero    FOREIGN KEY (tercero_id, drogueria_id)
                                  REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_tdir_drog       FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
CREATE INDEX IF NOT EXISTS idx_tdir_tercero ON tercero_direcciones (tercero_id) WHERE activo;

CREATE TABLE IF NOT EXISTS direccion_usos (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    direccion_id    UUID        NOT NULL,
    tercero_id      UUID        NOT NULL,   -- denormalizado: habilita uq_du_principal
    drogueria_id    UUID        NOT NULL,
    uso             TEXT        NOT NULL,
    es_principal    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_du_id_drog      UNIQUE (id, drogueria_id),
    CONSTRAINT uq_du_dir_uso      UNIQUE (direccion_id, uso),
    CONSTRAINT ck_du_uso          CHECK (uso IN ('facturacion','entrega','documentacion','otra')),
    CONSTRAINT fk_du_dir_drog     FOREIGN KEY (direccion_id, drogueria_id)
                                  REFERENCES tercero_direcciones (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_du_dir_tercero  FOREIGN KEY (direccion_id, tercero_id)
                                  REFERENCES tercero_direcciones (id, tercero_id) ON DELETE CASCADE,
    CONSTRAINT fk_du_drog         FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);

-- Como maximo una direccion principal por uso y por tercero, garantizado por la base.
CREATE UNIQUE INDEX IF NOT EXISTS uq_du_principal ON direccion_usos (tercero_id, uso) WHERE es_principal;
CREATE INDEX IF NOT EXISTS idx_du_uso ON direccion_usos (tercero_id, uso);

-- =============================================================================
-- M7 — Contactos; retiro de cliente_contactos
-- =============================================================================
CREATE TABLE IF NOT EXISTS terceros_contactos (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    tercero_id      UUID        NOT NULL,
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,
    apellido        TEXT        NULL,
    sector_id       UUID        NULL,
    cargo           TEXT        NULL,
    email           TEXT        NULL,
    telefono        TEXT        NULL,
    celular         TEXT        NULL,
    es_principal    BOOLEAN     NOT NULL DEFAULT FALSE,
    notas           TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_tc_id_drog   UNIQUE (id, drogueria_id),
    CONSTRAINT fk_tc_tercero   FOREIGN KEY (tercero_id, drogueria_id)
                               REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_tc_sector    FOREIGN KEY (sector_id, drogueria_id)
                               REFERENCES sectores_contacto (id, drogueria_id),
    CONSTRAINT fk_tc_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);

-- 'activo' en el predicado: dar de baja al contacto principal libera el lugar (regla D4).
CREATE UNIQUE INDEX IF NOT EXISTS uq_tc_principal ON terceros_contactos (tercero_id) WHERE es_principal AND activo;
CREATE INDEX IF NOT EXISTS idx_tc_tercero ON terceros_contactos (tercero_id) WHERE activo;

DROP TABLE IF EXISTS cliente_contactos;   -- reemplazada por terceros_contactos

-- =============================================================================
-- M8 — Recrear las 9 vistas de M4, WITH (security_invoker = true)
-- Hoy no declaraban security_invoker y por lo tanto evadían RLS (D6): esta es
-- la oportunidad de corregirlo, además de leer el nombre desde terceros y el
-- plazo de pago desde condiciones_pago.plazos_dias en lugar de las columnas
-- eliminadas en M5.
--
-- Nota de diseño: condiciones_pago.plazos_dias es un arreglo (una condición
-- puede tener varios términos, p.ej. {30,60,90}); las columnas informativas
-- "plazo_pago_*" de estas vistas siguen siendo un único INTEGER (comparadas
-- con precios_proveedor.plazo_pago_dias, que no cambia en este change), así
-- que se usa el primer término del arreglo como valor representativo. El
-- listado completo de plazos vive en condiciones_pago y se expone via API.
--
-- v_presupuesto_revision preserva el enriquecimiento con usuarios (ajustado_por)
-- agregado por docs/schema/rls_final.sql vía CREATE OR REPLACE VIEW después de
-- la definición base de extractor_final.sql; esta migración reemplaza esa
-- versión "final" en vivo, no la base original.
-- =============================================================================

-- Pantalla de aprobación del presupuesto
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
    uaj.nombre                  AS ajustado_por,
    COALESCE(t_prov.nombre_fantasia, t_prov.razon_social) AS proveedor_compra,
    COALESCE(pp.plazo_pago_dias, (cp_prov.plazos_dias[1])::integer) AS plazo_pago_proveedor,
    (cp_cli.plazos_dias[1])::integer AS plazo_pago_cliente,
    pi.mantenimiento_hasta_usado,
    (pi.mantenimiento_hasta_usado IS NOT NULL
     AND proc.vencimiento IS NOT NULL
     AND pi.mantenimiento_hasta_usado < proc.vencimiento) AS alerta_mantenimiento
FROM presupuestos p
JOIN procesos_comerciales proc  ON proc.id = p.proceso_comercial_id
LEFT JOIN clientes cl           ON cl.id = proc.cliente_id
LEFT JOIN terceros t_cli        ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
LEFT JOIN condiciones_pago cp_cli ON cp_cli.id = cl.condicion_pago_id
JOIN presupuesto_items pi       ON pi.presupuesto_id = p.id
JOIN items_proceso ip           ON ip.id = pi.item_proceso_id
LEFT JOIN productos prod        ON prod.id = pi.producto_id
LEFT JOIN precios_proveedor pp  ON pp.id = pi.precio_proveedor_id
LEFT JOIN proveedores prov      ON prov.id = pp.proveedor_id
LEFT JOIN terceros t_prov       ON t_prov.id = prov.id AND t_prov.drogueria_id = prov.drogueria_id
LEFT JOIN condiciones_pago cp_prov ON cp_prov.id = prov.condicion_pago_id
LEFT JOIN usuarios uaj          ON uaj.id = pi.precio_ajustado_por
ORDER BY p.id, ip.numero_renglon;

-- Cola de matching pendiente
CREATE VIEW v_matching_pendiente WITH (security_invoker = true) AS
SELECT
    ip.id                       AS item_proceso_id,
    ip.proceso_comercial_id,
    proc.nombre                 AS proceso,
    proc.clase,
    proc.cliente_id,
    t_cli.razon_social          AS cliente,
    ip.numero_renglon,
    ip.descripcion,
    ip.estado_matching,
    ip.confianza_matching,
    (SELECT COUNT(*) FROM matching_candidatos mc WHERE mc.item_proceso_id = ip.id) AS candidatos
FROM items_proceso ip
JOIN procesos_comerciales proc ON proc.id = ip.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
LEFT JOIN terceros t_cli       ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
WHERE ip.estado_matching IN ('pendiente', 'sugerido')
  AND proc.estado IN ('abierto', 'presupuestado')
ORDER BY proc.vencimiento NULLS FIRST, ip.numero_renglon;

-- Precios especiales vigentes (costo alternativo del motor)
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

-- Renglones ganados (oficial o estimado) para anticipar compras
CREATE VIEW v_renglones_ganados WITH (security_invoker = true) AS
SELECT
    c.proceso_comercial_id,
    proc.nombre                 AS proceso,
    t_cli.razon_social          AS cliente,
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
LEFT JOIN terceros t_cli       ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
WHERE oi.es_drogueria_propia = TRUE
  AND (oi.adjudicada OR oi.adjudicacion_estimada);

-- Entregas pendientes con atraso
CREATE VIEW v_entregas_pendientes WITH (security_invoker = true) AS
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

-- Instrucciones de formato de documento por cliente (usadas por el prompt de extracción)
CREATE VIEW v_formato_para_prompt WITH (security_invoker = true) AS
SELECT
    cf.cliente_id,
    t_cli.razon_social AS cliente,
    cf.doc_type,
    cf.instrucciones_prompt,
    cf.archivo_ejemplo_path
FROM cliente_formato_documentos cf
JOIN clientes cl        ON cl.id = cf.cliente_id
LEFT JOIN terceros t_cli ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
WHERE cf.activo = TRUE AND cf.instrucciones_prompt IS NOT NULL;

-- Presupuesto comercial (variante sin el enriquecimiento de v_presupuesto_revision)
CREATE VIEW v_presupuesto_comercial WITH (security_invoker = true) AS
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
LEFT JOIN terceros t_cli       ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
JOIN presupuesto_items pi      ON pi.presupuesto_id = p.id
JOIN items_proceso ip          ON ip.id = pi.item_proceso_id
LEFT JOIN productos prod       ON prod.id = pi.producto_id;

-- Calendario de eventos comerciales
CREATE VIEW v_calendario WITH (security_invoker = true) AS
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
    t_cli.razon_social          AS cliente,
    CASE
        WHEN e.estado = ANY (ARRAY['completado','cancelado']) THEN FALSE
        WHEN e.fecha_limite IS NOT NULL AND e.fecha_limite < now() THEN TRUE
        ELSE FALSE
    END AS vencido
FROM eventos e
LEFT JOIN usuarios u     ON u.id = e.responsable_id
LEFT JOIN clientes cl    ON cl.id = e.cliente_id
LEFT JOIN terceros t_cli ON t_cli.id = cl.id AND t_cli.drogueria_id = cl.drogueria_id
WHERE e.deleted_at IS NULL;

-- Compras reales vs. lo cotizado por el proveedor
CREATE VIEW v_compras_vs_cotizado WITH (security_invoker = true) AS
SELECT
    cp.id                       AS compra_id,
    prod.nombre                 AS producto,
    COALESCE(t_prov.nombre_fantasia, t_prov.razon_social) AS proveedor,
    cp.cantidad,
    cp.precio_unitario          AS precio_compra_real,
    pp.precio_unitario          AS precio_cotizado,
    (cp.precio_unitario - pp.precio_unitario) AS diferencia,
    cp.fecha_compra,
    pp.mantenimiento_hasta,
    (cp.fecha_compra > pp.mantenimiento_hasta) AS comprado_fuera_de_mantenimiento
FROM compras_proveedor cp
JOIN productos prod       ON prod.id = cp.producto_id
JOIN proveedores prov     ON prov.id = cp.proveedor_id
LEFT JOIN terceros t_prov ON t_prov.id = prov.id AND t_prov.drogueria_id = prov.drogueria_id
LEFT JOIN precios_proveedor pp ON pp.id = cp.precio_proveedor_id
WHERE cp.precio_proveedor_id IS NOT NULL;

-- =============================================================================
-- M9 — Triggers de updated_at, RLS + políticas, GRANTs, NOTIFY pgrst
-- =============================================================================

-- ---------- updated_at ----------
DROP TRIGGER IF EXISTS trg_sectores_contacto_updated_at ON sectores_contacto;
CREATE TRIGGER trg_sectores_contacto_updated_at
  BEFORE UPDATE ON sectores_contacto
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_condiciones_pago_updated_at ON condiciones_pago;
CREATE TRIGGER trg_condiciones_pago_updated_at
  BEFORE UPDATE ON condiciones_pago
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_formas_pago_updated_at ON formas_pago;
CREATE TRIGGER trg_formas_pago_updated_at
  BEFORE UPDATE ON formas_pago
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_terceros_updated_at ON terceros;
CREATE TRIGGER trg_terceros_updated_at
  BEFORE UPDATE ON terceros
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_tercero_direcciones_updated_at ON tercero_direcciones;
CREATE TRIGGER trg_tercero_direcciones_updated_at
  BEFORE UPDATE ON tercero_direcciones
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_terceros_contactos_updated_at ON terceros_contactos;
CREATE TRIGGER trg_terceros_contactos_updated_at
  BEFORE UPDATE ON terceros_contactos
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- direccion_usos y terceros_legacy_map no llevan updated_at (D4: solo terceros
-- lleva soft delete auditado; los usos/mapa legado son filas de asociación).

-- ---------- RLS: terceros, tercero_direcciones, direccion_usos, terceros_contactos,
-- terceros_legacy_map — union de roles de escritura de clientes y proveedores
-- (D6 en design.md sección 6): un tercero puede cumplir ambos roles, así que
-- restringir a un solo conjunto de roles bloquearía al otro. ----------
ALTER TABLE terceros ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS terceros_sel ON terceros;
CREATE POLICY terceros_sel ON terceros FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS terceros_ins ON terceros;
CREATE POLICY terceros_ins ON terceros FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS terceros_upd ON terceros;
CREATE POLICY terceros_upd ON terceros FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS terceros_del ON terceros;
CREATE POLICY terceros_del ON terceros FOR DELETE USING ((select es_superadmin()));

ALTER TABLE tercero_direcciones ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tdir_sel ON tercero_direcciones;
CREATE POLICY tdir_sel ON tercero_direcciones FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tdir_ins ON tercero_direcciones;
CREATE POLICY tdir_ins ON tercero_direcciones FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tdir_upd ON tercero_direcciones;
CREATE POLICY tdir_upd ON tercero_direcciones FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tdir_del ON tercero_direcciones;
CREATE POLICY tdir_del ON tercero_direcciones FOR DELETE USING ((select es_superadmin()));

ALTER TABLE direccion_usos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS du_sel ON direccion_usos;
CREATE POLICY du_sel ON direccion_usos FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS du_ins ON direccion_usos;
CREATE POLICY du_ins ON direccion_usos FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS du_upd ON direccion_usos;
CREATE POLICY du_upd ON direccion_usos FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS du_del ON direccion_usos;
CREATE POLICY du_del ON direccion_usos FOR DELETE USING ((select es_superadmin()));

ALTER TABLE terceros_contactos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tc_sel ON terceros_contactos;
CREATE POLICY tc_sel ON terceros_contactos FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tc_ins ON terceros_contactos;
CREATE POLICY tc_ins ON terceros_contactos FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tc_upd ON terceros_contactos;
CREATE POLICY tc_upd ON terceros_contactos FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tc_del ON terceros_contactos;
CREATE POLICY tc_del ON terceros_contactos FOR DELETE USING ((select es_superadmin()));

ALTER TABLE terceros_legacy_map ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tlm_sel ON terceros_legacy_map;
CREATE POLICY tlm_sel ON terceros_legacy_map FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tlm_ins ON terceros_legacy_map;
CREATE POLICY tlm_ins ON terceros_legacy_map FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tlm_upd ON terceros_legacy_map;
CREATE POLICY tlm_upd ON terceros_legacy_map FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tlm_del ON terceros_legacy_map;
CREATE POLICY tlm_del ON terceros_legacy_map FOR DELETE USING ((select es_superadmin()));

-- ---------- RLS: catálogos — lectura para el tenant, escritura acotada a admin/gerencia ----------
ALTER TABLE sectores_contacto ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sec_sel ON sectores_contacto;
CREATE POLICY sec_sel ON sectores_contacto FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS sec_ins ON sectores_contacto;
CREATE POLICY sec_ins ON sectores_contacto FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS sec_upd ON sectores_contacto;
CREATE POLICY sec_upd ON sectores_contacto FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS sec_del ON sectores_contacto;
CREATE POLICY sec_del ON sectores_contacto FOR DELETE USING ((select es_superadmin()));

ALTER TABLE condiciones_pago ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cp_sel ON condiciones_pago;
CREATE POLICY cp_sel ON condiciones_pago FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS cp_ins ON condiciones_pago;
CREATE POLICY cp_ins ON condiciones_pago FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS cp_upd ON condiciones_pago;
CREATE POLICY cp_upd ON condiciones_pago FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS cp_del ON condiciones_pago;
CREATE POLICY cp_del ON condiciones_pago FOR DELETE USING ((select es_superadmin()));

ALTER TABLE formas_pago ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fp_sel ON formas_pago;
CREATE POLICY fp_sel ON formas_pago FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS fp_ins ON formas_pago;
CREATE POLICY fp_ins ON formas_pago FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS fp_upd ON formas_pago;
CREATE POLICY fp_upd ON formas_pago FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS fp_del ON formas_pago;
CREATE POLICY fp_del ON formas_pago FOR DELETE USING ((select es_superadmin()));

-- ---------- GRANTs explícitos ----------
-- Supabase no autoexpone tablas nuevas al Data API (precedente:
-- 0007_apellido_y_planes.sql). Sin DELETE para authenticated: la API nunca
-- borra físicamente estas filas (D4), solo activo=false.
GRANT SELECT, INSERT, UPDATE, DELETE ON
    terceros, tercero_direcciones, direccion_usos, terceros_contactos, terceros_legacy_map,
    sectores_contacto, condiciones_pago, formas_pago
  TO service_role;
GRANT SELECT, INSERT, UPDATE ON
    terceros, tercero_direcciones, direccion_usos, terceros_contactos, terceros_legacy_map,
    sectores_contacto, condiciones_pago, formas_pago
  TO authenticated;

-- Forzar reload de PostgREST para que detecte las tablas y vistas nuevas
NOTIFY pgrst, 'reload schema';

-- =============================================================================
-- M10 — RPC upsert_terceros_legacy: upsert idempotente del import legado
-- Sin SECURITY DEFINER (mismo criterio que reserve_extraction,
-- 0002_rpc_reserve.sql): la invoca get_service_client(), que ya bypasea RLS.
-- Cuerpo íntegro en una transacción: un fallo en el paso 5 revierte los pasos
-- 3 y 4, no quedan terceros huérfanos.
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
DECLARE fila JSONB; v_tid UUID; v_accion TEXT;
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
      INSERT INTO terceros (drogueria_id, codigo_interno, razon_social, cuit, created_by, updated_by)
      VALUES (p_drogueria_id, fila->>'codigo_legacy', fila->>'razon_social',
              nullif(fila->>'cuit',''), p_usuario_id, p_usuario_id)
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

REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM anon;
REVOKE EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM authenticated;
GRANT  EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) TO service_role;

COMMENT ON FUNCTION upsert_terceros_legacy IS
  'Upsert idempotente del import legado (ver openspec/changes/terceros-modelo/design.md sección 7). Sin SECURITY DEFINER: la invoca get_service_client(), que ya bypasea RLS.';
