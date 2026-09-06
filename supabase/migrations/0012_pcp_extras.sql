-- =============================================================================
-- Migration 0012: extras de PCP (gestor de mejora de precios de compra)
--
-- PR2 de la secuencia gestor-pcp (ver openspec/changes/gestor-pcp/design.md,
-- decisiones D5-D9, D11). Cubre las cinco tablas restantes del modulo
-- (pcp_historial, reglas_pcp, pcp_legacy_map, pcp_consultas,
-- pcp_consulta_renglones), las columnas FK de precios_proveedor
-- (condicion_pago_id/forma_pago_id) + backfill, y la recreacion de las dos
-- vistas que leen plazo_pago_dias. Se aplica despues de que
-- 0011_pcp_modelo.sql (PR1) fue mergeado a la base del test project.
--
-- Verificado en vivo contra el proyecto de test (grnamollopxdlstcpxhc, via
-- introspeccion del esquema OpenAPI de PostgREST, cross-checked contra
-- docs/schema/extractor_final.sql/rls_final.sql ya actualizados por PR1) antes
-- de escribir cualquier FK -- el MCP de Supabase no estaba disponible en este
-- contexto de sdd-apply, misma situacion que PR1 (ver tasks.md 1.1). Tablas
-- confirmadas en vivo con la forma esperada: precios_proveedor, terceros,
-- terceros_contactos, condiciones_pago, formas_pago, sectores_contacto,
-- usuarios, costos_productos, v_precios_especiales_vigentes,
-- v_presupuesto_revision, y las cuatro tablas de PR1 (pcp, pcp_renglones,
-- producto_proveedores, pcp_renglon_resultados) ya presentes con sus columnas
-- "referente llega en 0012" (regla_pcp_id, consulta_id) todavia sin FK.
--
-- Esquema aditivo puro salvo las dos vistas (DROP+CREATE en el lugar, mismas
-- columnas). Un solo archivo = una sola transaccion (supabase db push envuelve
-- cada migracion en su propia transaccion; no se agregan BEGIN/COMMIT
-- explicitos). Estilo: 0008_terceros_modelo.sql / 0011_pcp_modelo.sql.
--
-- Pasos (M0-M8):
--   M0  Guard de version de Postgres (>=15, consistente con 0008/0011)
--   M1  pcp_historial (D6, append-only)
--   M2  reglas_pcp (D7, seam only)
--   M3  pcp_legacy_map (D8)
--   M4  pcp_consultas + pcp_consulta_renglones (D9)
--   M4b FKs diferidas de PR1 hacia reglas_pcp / pcp_consultas
--   M5  precios_proveedor: columnas condicion_pago_id/forma_pago_id + FKs (D5)
--   M5b Backfill: condiciones_pago find-or-create por plazo_pago_dias distinto
--   M6  DROP+CREATE v_precios_especiales_vigentes y v_presupuesto_revision
--   M7  Triggers de updated_at, RLS + politicas, GRANTs, NOTIFY pgrst (D11)
--   M8  RPC upsert_pcp_legacy (D8)
-- =============================================================================

-- =============================================================================
-- M0 — Guard de version de Postgres
-- =============================================================================
DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'gestor-pcp requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

-- =============================================================================
-- M1 — pcp_historial (D6)
-- Dedicada y append-only: no extiende EntidadAuditable/historial_cambios (ese
-- Literal cerrado de 5 valores arrastraria PCP al router de auditoria
-- Comercial y su matriz de visibilidad). Append-only se logra omitiendo por
-- completo las politicas UPDATE/DELETE (RLS habilitado sin ellas = deny by
-- default para esos comandos) y no otorgando GRANT UPDATE/DELETE a
-- authenticated. Sin updated_at (no aplica a filas que nunca se modifican).
-- =============================================================================
CREATE TABLE IF NOT EXISTS pcp_historial (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    pcp_id          UUID        NOT NULL,
    pcp_renglon_id  UUID        NULL,
    tipo_evento     TEXT        NOT NULL,
    payload         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    origen          TEXT        NULL,
    usuario_id      UUID        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_pcph_id_drog     UNIQUE (id, drogueria_id),
    CONSTRAINT ck_pcph_tipo_evento CHECK (tipo_evento IN (
        'creada','estado_cambiado','renglon_agregado','renglon_quitado',
        'consulta_enviada','resultado_registrado','sugerencia_aplicada',
        'notificacion_enviada','importada')),
    CONSTRAINT fk_pcph_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_pcph_pcp      FOREIGN KEY (pcp_id, drogueria_id)
                                REFERENCES pcp (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_pcph_renglon  FOREIGN KEY (pcp_renglon_id, drogueria_id)
                                REFERENCES pcp_renglones (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_pcph_usuario  FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
);
COMMENT ON TABLE pcp_historial IS 'Auditoria dedicada y append-only de PCP: nunca escribe en historial_cambios ni extiende EntidadAuditable. Ver design.md D6. Sin UPDATE/DELETE via API.';
COMMENT ON COLUMN pcp_historial.payload IS 'Contexto libre del evento (p.ej. estado_anterior/estado_nuevo). Nunca lleva campos de costo (D2).';

CREATE INDEX IF NOT EXISTS idx_pcph_pcp ON pcp_historial (drogueria_id, pcp_id, created_at DESC);

-- =============================================================================
-- M2 — reglas_pcp (D7)
-- Seam unicamente: forma de tabla + FKs referentes, sin motor, sin filas, sin
-- codigo de servicio. Existe para que pcp.regla_pcp_id / pcp_renglones.regla_pcp_id
-- ya tengan un referente el dia que origen='regla' se escriba por primera vez.
-- =============================================================================
CREATE TABLE IF NOT EXISTS reglas_pcp (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,
    cliente_id      UUID        NULL,
    categoria_id    UUID        NULL,
    producto_id     UUID        NULL,
    clase_proceso   TEXT        NULL,
    condicion       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    prioridad       INTEGER     NOT NULL DEFAULT 0,
    activa          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_by      UUID        NULL,
    updated_by      UUID        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_rpcp_id_drog   UNIQUE (id, drogueria_id),
    CONSTRAINT ck_rpcp_clase     CHECK (clase_proceso IS NULL OR clase_proceso IN ('cotizacion','licitacion')),
    CONSTRAINT fk_rpcp_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_rpcp_cliente   FOREIGN KEY (cliente_id, drogueria_id) REFERENCES clientes (id, drogueria_id),
    CONSTRAINT fk_rpcp_categoria FOREIGN KEY (categoria_id) REFERENCES categorias (id),
    CONSTRAINT fk_rpcp_producto  FOREIGN KEY (producto_id) REFERENCES productos (id),
    CONSTRAINT fk_rpcp_createdby FOREIGN KEY (created_by) REFERENCES usuarios (id),
    CONSTRAINT fk_rpcp_updatedby FOREIGN KEY (updated_by) REFERENCES usuarios (id)
);
COMMENT ON TABLE reglas_pcp IS 'Seam de reglas automaticas de PCP: solo forma de tabla, sin motor ni filas. NULL en cliente_id/categoria_id/producto_id/clase_proceso = alcance por defecto; prioridad desempata. Ver design.md D7.';

-- =============================================================================
-- M3 — pcp_legacy_map (D8)
-- A diferencia de terceros_legacy_map, no hay discriminador entidad_legacy:
-- PCP es una sola entidad, los espacios de codigo no pueden colisionar entre
-- si. Sin updated_at (fila de asociacion, igual que terceros_legacy_map).
-- =============================================================================
CREATE TABLE IF NOT EXISTS pcp_legacy_map (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    pcp_id          UUID        NOT NULL,
    drogueria_id    UUID        NOT NULL,
    sistema_origen  TEXT        NOT NULL DEFAULT 'legacy',
    codigo_legacy   TEXT        NOT NULL,
    datos_legacy    JSONB       NULL,
    importado_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_pcplm_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT uq_pcplm_codigo  UNIQUE (drogueria_id, sistema_origen, codigo_legacy),
    CONSTRAINT fk_pcplm_pcp     FOREIGN KEY (pcp_id, drogueria_id)
                                REFERENCES pcp (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_pcplm_drog    FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON TABLE pcp_legacy_map IS 'Clave de idempotencia del import legado de PCP (ver design.md D8). uq_pcplm_codigo es la que usa upsert_pcp_legacy via ON CONFLICT.';

-- =============================================================================
-- M4 — pcp_consultas + pcp_consulta_renglones (D9)
-- pcp_consultas deliberadamente NO tiene pcp_id: el agrupamiento es un
-- many-to-many real. pcp_consulta_renglones es lo que permite que renglones
-- de varios PCP terminen en una sola consulta a un mismo proveedor.
-- =============================================================================
CREATE TABLE IF NOT EXISTS pcp_consultas (
    id                          UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id                UUID        NOT NULL,
    proveedor_id                UUID        NOT NULL,
    contacto_id                 UUID        NULL,
    estado                      TEXT        NOT NULL DEFAULT 'borrador',
    canal                       TEXT        NULL,
    fecha_envio                 TIMESTAMPTZ NULL,
    fecha_respuesta_esperada    DATE        NULL,
    documento_path              TEXT        NULL,
    created_by                  UUID        NULL,
    updated_by                  UUID        NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_pcpc_id_drog   UNIQUE (id, drogueria_id),
    CONSTRAINT ck_pcpc_estado    CHECK (estado IN ('borrador','enviada','respondida','cancelada')),
    CONSTRAINT fk_pcpc_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_pcpc_proveedor FOREIGN KEY (proveedor_id, drogueria_id)
                                  REFERENCES proveedores (id, drogueria_id),
    CONSTRAINT fk_pcpc_contacto  FOREIGN KEY (contacto_id, drogueria_id)
                                  REFERENCES terceros_contactos (id, drogueria_id),
    CONSTRAINT fk_pcpc_createdby FOREIGN KEY (created_by) REFERENCES usuarios (id),
    CONSTRAINT fk_pcpc_updatedby FOREIGN KEY (updated_by) REFERENCES usuarios (id)
);
COMMENT ON TABLE pcp_consultas IS 'Consulta agrupada a un proveedor. Sin pcp_id a proposito: el agrupamiento many-to-many vive en pcp_consulta_renglones. Ver design.md D9.';

CREATE TABLE IF NOT EXISTS pcp_consulta_renglones (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID            NOT NULL,
    consulta_id             UUID            NOT NULL,
    pcp_renglon_id          UUID            NOT NULL,
    cantidad_consultada     NUMERIC(12, 2)  NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_pcpcr_id_drog  UNIQUE (id, drogueria_id),
    CONSTRAINT uq_pcpcr_consulta_renglon UNIQUE (consulta_id, pcp_renglon_id),
    CONSTRAINT fk_pcpcr_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_pcpcr_consulta FOREIGN KEY (consulta_id, drogueria_id)
                                  REFERENCES pcp_consultas (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_pcpcr_renglon  FOREIGN KEY (pcp_renglon_id, drogueria_id)
                                  REFERENCES pcp_renglones (id, drogueria_id) ON DELETE CASCADE
);
COMMENT ON TABLE pcp_consulta_renglones IS 'Fila de asociacion N:M entre pcp_consultas y pcp_renglones (de PCPs potencialmente distintos). Ver design.md D9.';

-- =============================================================================
-- M4b — FKs diferidas de PR1: PR1 dejo regla_pcp_id/consulta_id sin FK porque
-- sus tablas referentes (reglas_pcp, pcp_consultas) recien existen aca.
-- =============================================================================
ALTER TABLE pcp
    ADD CONSTRAINT fk_pcp_regla FOREIGN KEY (regla_pcp_id, drogueria_id)
        REFERENCES reglas_pcp (id, drogueria_id);

ALTER TABLE pcp_renglones
    ADD CONSTRAINT fk_pcpr_regla FOREIGN KEY (regla_pcp_id, drogueria_id)
        REFERENCES reglas_pcp (id, drogueria_id);

ALTER TABLE pcp_renglon_resultados
    ADD CONSTRAINT fk_ppr_consulta FOREIGN KEY (consulta_id, drogueria_id)
        REFERENCES pcp_consultas (id, drogueria_id);

-- =============================================================================
-- M5 — precios_proveedor: columnas condicion_pago_id/forma_pago_id (D5)
-- Aditivo con rollback a un release: plazo_pago_dias queda en su lugar,
-- nullable, sin uso por codigo nuevo. Mismo patron que clientes/proveedores
-- en 0008 M5 (composite FK a condiciones_pago/formas_pago(id, drogueria_id)).
-- =============================================================================
ALTER TABLE precios_proveedor
    ADD COLUMN IF NOT EXISTS condicion_pago_id UUID NULL,
    ADD COLUMN IF NOT EXISTS forma_pago_id     UUID NULL;

ALTER TABLE precios_proveedor
    ADD CONSTRAINT fk_pp_condpago  FOREIGN KEY (condicion_pago_id, drogueria_id)
        REFERENCES condiciones_pago (id, drogueria_id),
    ADD CONSTRAINT fk_pp_formapago FOREIGN KEY (forma_pago_id, drogueria_id)
        REFERENCES formas_pago (id, drogueria_id);

COMMENT ON COLUMN precios_proveedor.condicion_pago_id IS 'Reemplaza plazo_pago_dias (D5). plazo_pago_dias sobrevive nullable y sin uso por un release para permitir rollback code-only.';
COMMENT ON COLUMN precios_proveedor.plazo_pago_dias IS 'DEPRECADO desde 0012 (D5): reemplazado por condicion_pago_id. Nullable, sin escritura de codigo nuevo; se retira en un release posterior.';

-- =============================================================================
-- M5b — Backfill: una fila de condiciones_pago por cada plazo_pago_dias
-- distinto, por drogueria (D5). find-or-create por (drogueria_id, nombre) con
-- nombre = N || ' dias'; set de la FK en las filas ya existentes con ese valor.
--
-- Implementado como funcion nombrada (no un DO anonimo) e idempotente
-- (guardas IS NULL en ambos pasos) por dos razones: (1) esta misma migracion
-- la invoca una vez para todas las droguerias al final de este bloque; (2) el
-- test de integracion de tasks.md 2.15 necesita poder re-invocarla contra
-- datos sembrados en el momento del test, sin depender de que su ejecucion
-- coincida con el momento en que esta migracion se aplico. Mismo criterio de
-- REVOKE/GRANT que el resto de las RPC del modulo (sin SECURITY DEFINER; la
-- invoca service_role, que ya bypasea RLS).
-- =============================================================================
CREATE OR REPLACE FUNCTION backfill_condicion_pago_desde_plazo(p_drogueria_id UUID DEFAULT NULL)
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    r RECORD;
    v_nombre TEXT;
    v_filas INTEGER;
    v_total INTEGER := 0;
BEGIN
    FOR r IN
        SELECT DISTINCT drogueria_id, plazo_pago_dias
        FROM precios_proveedor
        WHERE plazo_pago_dias IS NOT NULL
          AND condicion_pago_id IS NULL
          AND (p_drogueria_id IS NULL OR drogueria_id = p_drogueria_id)
    LOOP
        v_nombre := r.plazo_pago_dias || ' dias';

        INSERT INTO condiciones_pago (drogueria_id, nombre, plazos_dias)
        VALUES (r.drogueria_id, v_nombre, ARRAY[r.plazo_pago_dias]::smallint[])
        ON CONFLICT (drogueria_id, nombre) DO NOTHING;

        UPDATE precios_proveedor pp
        SET condicion_pago_id = cp.id
        FROM condiciones_pago cp
        WHERE cp.drogueria_id = r.drogueria_id
          AND cp.nombre = v_nombre
          AND pp.drogueria_id = r.drogueria_id
          AND pp.plazo_pago_dias = r.plazo_pago_dias
          AND pp.condicion_pago_id IS NULL;

        GET DIAGNOSTICS v_filas = ROW_COUNT;
        v_total := v_total + v_filas;
    END LOOP;
    RETURN v_total;
END $$;

REVOKE EXECUTE ON FUNCTION backfill_condicion_pago_desde_plazo(UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION backfill_condicion_pago_desde_plazo(UUID) FROM anon;
REVOKE EXECUTE ON FUNCTION backfill_condicion_pago_desde_plazo(UUID) FROM authenticated;
GRANT  EXECUTE ON FUNCTION backfill_condicion_pago_desde_plazo(UUID) TO service_role;

COMMENT ON FUNCTION backfill_condicion_pago_desde_plazo IS
  'Backfill idempotente de precios_proveedor.condicion_pago_id desde plazo_pago_dias (design.md D5). p_drogueria_id NULL = todas. Devuelve la cantidad de filas de precios_proveedor actualizadas.';

-- Ejecucion de esta migracion: una sola pasada, para todas las droguerias.
SELECT backfill_condicion_pago_desde_plazo();

-- =============================================================================
-- M6 — DROP+CREATE v_precios_especiales_vigentes y v_presupuesto_revision
-- Leen COALESCE(cp_pp.plazos_dias[1], pp.plazo_pago_dias, cp_prov.plazos_dias[1])
-- en vez del pp.plazo_pago_dias directo: prioriza la condicion puntual del
-- precio (nueva FK), cae al entero legado, y por ultimo a la condicion
-- general del proveedor. WITH (security_invoker = true) preservado en ambas
-- -- exactamente la clase de error que 0008 documento cometer una vez
-- (perder security_invoker al recrear una vista); se verifica con
-- pg_get_viewdef despues de aplicar (tasks.md 2.9), no solo leyendo esta
-- fuente.
-- =============================================================================
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
    COALESCE((cp_pp.plazos_dias[1])::integer, pp.plazo_pago_dias, (cp_prov.plazos_dias[1])::integer) AS plazo_pago_proveedor,
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
LEFT JOIN condiciones_pago cp_pp   ON cp_pp.id = pp.condicion_pago_id
ORDER BY p.id, ip.numero_renglon;

-- =============================================================================
-- M7 — Triggers de updated_at, RLS + politicas, GRANTs, NOTIFY pgrst (D11)
-- Mismo patron de roles que PR1 (0011 M5): lectura restringida a
-- compras/gerencia/admin (+superadmin), escritura admin/gerencia/compras,
-- DELETE solo superadmin. Excepcion: pcp_historial solo SELECT+INSERT (D6,
-- append-only) -- sin politicas UPDATE/DELETE y sin esos GRANTs.
-- =============================================================================

-- ---------- updated_at (pcp_legacy_map y pcp_consulta_renglones no llevan) ----------
DROP TRIGGER IF EXISTS trg_reglas_pcp_updated_at ON reglas_pcp;
CREATE TRIGGER trg_reglas_pcp_updated_at
  BEFORE UPDATE ON reglas_pcp
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_pcp_consultas_updated_at ON pcp_consultas;
CREATE TRIGGER trg_pcp_consultas_updated_at
  BEFORE UPDATE ON pcp_consultas
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ---------- RLS: pcp_historial (SELECT+INSERT only) ----------
ALTER TABLE pcp_historial ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pcph_sel ON pcp_historial;
CREATE POLICY pcph_sel ON pcp_historial FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcph_ins ON pcp_historial;
CREATE POLICY pcph_ins ON pcp_historial FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
-- Sin politicas UPDATE/DELETE: RLS habilitado sin politica = deny by default.

-- ---------- RLS: reglas_pcp ----------
ALTER TABLE reglas_pcp ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rpcp_sel ON reglas_pcp;
CREATE POLICY rpcp_sel ON reglas_pcp FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS rpcp_ins ON reglas_pcp;
CREATE POLICY rpcp_ins ON reglas_pcp FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS rpcp_upd ON reglas_pcp;
CREATE POLICY rpcp_upd ON reglas_pcp FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS rpcp_del ON reglas_pcp;
CREATE POLICY rpcp_del ON reglas_pcp FOR DELETE USING ((select es_superadmin()));

-- ---------- RLS: pcp_legacy_map ----------
ALTER TABLE pcp_legacy_map ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pcplm_sel ON pcp_legacy_map;
CREATE POLICY pcplm_sel ON pcp_legacy_map FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcplm_ins ON pcp_legacy_map;
CREATE POLICY pcplm_ins ON pcp_legacy_map FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcplm_upd ON pcp_legacy_map;
CREATE POLICY pcplm_upd ON pcp_legacy_map FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcplm_del ON pcp_legacy_map;
CREATE POLICY pcplm_del ON pcp_legacy_map FOR DELETE USING ((select es_superadmin()));

-- ---------- RLS: pcp_consultas ----------
ALTER TABLE pcp_consultas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pcpc_sel ON pcp_consultas;
CREATE POLICY pcpc_sel ON pcp_consultas FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpc_ins ON pcp_consultas;
CREATE POLICY pcpc_ins ON pcp_consultas FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpc_upd ON pcp_consultas;
CREATE POLICY pcpc_upd ON pcp_consultas FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpc_del ON pcp_consultas;
CREATE POLICY pcpc_del ON pcp_consultas FOR DELETE USING ((select es_superadmin()));

-- ---------- RLS: pcp_consulta_renglones ----------
ALTER TABLE pcp_consulta_renglones ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pcpcr_sel ON pcp_consulta_renglones;
CREATE POLICY pcpcr_sel ON pcp_consulta_renglones FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpcr_ins ON pcp_consulta_renglones;
CREATE POLICY pcpcr_ins ON pcp_consulta_renglones FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpcr_upd ON pcp_consulta_renglones;
CREATE POLICY pcpcr_upd ON pcp_consulta_renglones FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpcr_del ON pcp_consulta_renglones;
CREATE POLICY pcpcr_del ON pcp_consulta_renglones FOR DELETE USING ((select es_superadmin()));

-- ---------- GRANTs explicitos ----------
-- Supabase no autoexpone tablas nuevas al Data API (precedente: 0007, 0008,
-- 0011). Sin DELETE para authenticated: la API nunca borra fisicamente estas
-- filas, solo RLS + service_role para mantenimiento administrativo.
GRANT SELECT, INSERT, UPDATE, DELETE ON
    reglas_pcp, pcp_legacy_map, pcp_consultas, pcp_consulta_renglones
  TO service_role;
GRANT SELECT, INSERT, UPDATE ON
    reglas_pcp, pcp_legacy_map, pcp_consultas, pcp_consulta_renglones
  TO authenticated;

-- pcp_historial: SELECT+INSERT unicamente, ambos lados (D6).
GRANT SELECT, INSERT, DELETE ON pcp_historial TO service_role;
GRANT SELECT, INSERT ON pcp_historial TO authenticated;

-- Forzar reload de PostgREST para que detecte las tablas y vistas nuevas
NOTIFY pgrst, 'reload schema';

-- =============================================================================
-- M8 — RPC upsert_pcp_legacy (D8)
-- Mirror de upsert_terceros_legacy (0008 M10, corregido por 0009/0010): sin
-- SECURITY DEFINER (la invoca get_service_client(), que ya bypasea RLS),
-- #variable_conflict use_column desde el primer intento -- evita repetir el
-- bug de "column reference is ambiguous" que 0009 tuvo que corregir despues,
-- ya que los parametros OUT (codigo_legacy, pcp_id) colisionan con columnas
-- reales de pcp_legacy_map/pcp_renglones en los targets de ON CONFLICT.
--
-- Forma de cada elemento de p_filas (JSONB): codigo_legacy, presupuesto_id,
-- proceso_comercial_id, fecha_entrega_solicitada, solicitante_id, sector_id,
-- notas, y un array "renglones" con item_proceso_id/producto_id/cantidad/
-- precio_referencia ya resueltos por el llamador. La logica de matching entre
-- el codigo legado de renglon y item_proceso_id vive en
-- services/pcp/imports (Fase 8, tasks.md 8.1) -- confirmada contra el export
-- real, no en esta RPC -- que solo persiste renglones ya resueltos, idempotente
-- via uq_pcpr_pcp_item (pcp_id, item_proceso_id).
-- =============================================================================
CREATE OR REPLACE FUNCTION upsert_pcp_legacy(
    p_drogueria_id   UUID,
    p_sistema_origen TEXT,
    p_filas          JSONB,     -- array de objetos: ver comentario arriba
    p_usuario_id     UUID
) RETURNS TABLE (codigo_legacy TEXT, pcp_id UUID, accion TEXT)
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
  fila JSONB;
  renglon JSONB;
  v_pid UUID;
  v_accion TEXT;
BEGIN
  FOR fila IN SELECT * FROM jsonb_array_elements(p_filas) LOOP
    -- 1) clave de idempotencia
    SELECT m.pcp_id INTO v_pid FROM pcp_legacy_map m
     WHERE m.drogueria_id = p_drogueria_id AND m.sistema_origen = p_sistema_origen
       AND m.codigo_legacy = fila->>'codigo_legacy'
     FOR UPDATE;
    v_accion := 'reusado';

    -- 2) alta o actualizacion del header
    IF v_pid IS NULL THEN
      INSERT INTO pcp (
          drogueria_id, presupuesto_id, proceso_comercial_id, fecha_entrega_solicitada,
          solicitante_id, sector_id, notas, origen, created_by, updated_by
      )
      VALUES (
          p_drogueria_id,
          (fila->>'presupuesto_id')::uuid,
          (fila->>'proceso_comercial_id')::uuid,
          nullif(fila->>'fecha_entrega_solicitada','')::date,
          nullif(fila->>'solicitante_id','')::uuid,
          nullif(fila->>'sector_id','')::uuid,
          fila->>'notas',
          'import_legado',
          p_usuario_id, p_usuario_id
      )
      RETURNING id INTO v_pid;
      v_accion := 'creado';
    ELSE
      UPDATE pcp SET
          fecha_entrega_solicitada = coalesce(nullif(fila->>'fecha_entrega_solicitada','')::date, fecha_entrega_solicitada),
          solicitante_id = coalesce(nullif(fila->>'solicitante_id','')::uuid, solicitante_id),
          sector_id = coalesce(nullif(fila->>'sector_id','')::uuid, sector_id),
          notas = coalesce(fila->>'notas', notas),
          updated_by = p_usuario_id
       WHERE id = v_pid;
    END IF;

    -- 3) mapa (idempotente)
    INSERT INTO pcp_legacy_map (pcp_id, drogueria_id, sistema_origen, codigo_legacy, datos_legacy)
    VALUES (v_pid, p_drogueria_id, p_sistema_origen, fila->>'codigo_legacy', fila)
    ON CONFLICT (drogueria_id, sistema_origen, codigo_legacy) DO NOTHING;

    -- 4) renglones: item_proceso_id ya resuelto por el llamador (Fase 8);
    -- idempotente via uq_pcpr_pcp_item (pcp_id, item_proceso_id).
    FOR renglon IN SELECT * FROM jsonb_array_elements(coalesce(fila->'renglones', '[]'::jsonb)) LOOP
      INSERT INTO pcp_renglones (
          drogueria_id, pcp_id, item_proceso_id, producto_id,
          cantidad, precio_referencia, origen, created_by, updated_by
      )
      VALUES (
          p_drogueria_id, v_pid,
          (renglon->>'item_proceso_id')::uuid,
          nullif(renglon->>'producto_id','')::uuid,
          nullif(renglon->>'cantidad','')::numeric,
          nullif(renglon->>'precio_referencia','')::numeric,
          'import_legado', p_usuario_id, p_usuario_id
      )
      ON CONFLICT (pcp_id, item_proceso_id) DO UPDATE SET
          producto_id        = excluded.producto_id,
          cantidad            = excluded.cantidad,
          precio_referencia   = excluded.precio_referencia,
          updated_by          = p_usuario_id;
    END LOOP;

    codigo_legacy := fila->>'codigo_legacy'; pcp_id := v_pid; accion := v_accion;
    RETURN NEXT;
  END LOOP;
END $$;

REVOKE EXECUTE ON FUNCTION upsert_pcp_legacy(UUID,TEXT,JSONB,UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION upsert_pcp_legacy(UUID,TEXT,JSONB,UUID) FROM anon;
REVOKE EXECUTE ON FUNCTION upsert_pcp_legacy(UUID,TEXT,JSONB,UUID) FROM authenticated;
GRANT  EXECUTE ON FUNCTION upsert_pcp_legacy(UUID,TEXT,JSONB,UUID) TO service_role;

COMMENT ON FUNCTION upsert_pcp_legacy IS
  'Upsert idempotente del import legado de PCP (ver openspec/changes/gestor-pcp/design.md D8). Sin SECURITY DEFINER: la invoca get_service_client(), que ya bypasea RLS.';
