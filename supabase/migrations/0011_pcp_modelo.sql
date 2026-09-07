-- =============================================================================
-- Migration 0011: modelo core de PCP (gestor de mejora de precios de compra)
--
-- PR1 de la secuencia gestor-pcp (ver openspec/changes/gestor-pcp/design.md,
-- decisiones D1-D4, D11). Cubre las cuatro tablas mas tempranas del modulo:
-- pcp, pcp_renglones, producto_proveedores, pcp_renglon_resultados. Las cinco
-- restantes (pcp_historial, reglas_pcp, pcp_legacy_map, pcp_consultas,
-- pcp_consulta_renglones) y la migracion de precios_proveedor.plazo_pago_dias
-- llegan en 0012_pcp_extras.sql (PR2). El proposal/design original decia
-- "siete tablas nuevas" en su prosa; D2-D9 nombran nueve, tratadas como
-- autoritativas (tasks.md 1.2) — se deja constancia del desajuste aqui.
--
-- Esquema aditivo puro: no toca ninguna tabla existente. Un solo archivo =
-- una sola transaccion (supabase db push envuelve cada migracion en su
-- propia transaccion; no se agregan BEGIN/COMMIT explicitos). Estilo:
-- 0008_terceros_modelo.sql (UNIQUE (id, drogueria_id) en toda tabla nueva
-- para FKs compuestas tenant-safe, GRANTs explicitos, NOTIFY pgrst).
--
-- Verificado en vivo contra el proyecto de test (grnamollopxdlstcpxhc, via
-- introspeccion del esquema OpenAPI de PostgREST) antes de escribir
-- cualquier FK, en lugar de confiar en docs/schema/extractor_final.sql
-- (conocido desactualizado):
--   - presupuestos(id, drogueria_id) UNIQUE       -> uq_pre_id_drog
--   - items_proceso(id, drogueria_id) UNIQUE      -> uq_ip_id_drog
--   - proveedores(id, drogueria_id) UNIQUE        -> uq_prov_id_drog (post-0008)
--   - productos.id / procesos_comerciales.id      -> sin UNIQUE compuesto;
--     FK simple, igual que items_proceso.producto_id /
--     presupuesto_items.producto_id / items_proceso.proceso_comercial_id ya
--     existentes en el esquema en vivo.
--
-- Pasos (M0-M5):
--   M0  Guard de version de Postgres (>=15, consistente con 0008)
--   M1  pcp (header, D2)
--   M2  pcp_renglones (D2)
--   M3  producto_proveedores (D3)
--   M4  pcp_renglon_resultados (D4)
--   M5  Triggers de updated_at, RLS + politicas, GRANTs, NOTIFY pgrst (D11)
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
-- M1 — pcp (header)
-- 1:1 con un presupuesto origen. Confirmado por el usuario: como maximo un
-- PCP abierto por presupuesto -> uq_pcp_presupuesto_abierto, indice unico
-- parcial (permite reabrir con un nuevo PCP una vez que el anterior cerro).
-- =============================================================================
CREATE TABLE IF NOT EXISTS pcp (
    id                          UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id                UUID        NOT NULL,
    presupuesto_id              UUID        NOT NULL,
    proceso_comercial_id        UUID        NOT NULL,   -- denormalizado: filtro de listado sin JOIN
    estado                      TEXT        NOT NULL DEFAULT 'nueva',
    fecha_entrega_solicitada    DATE        NULL,        -- filtro primario del listado, carried desde el presupuesto
    solicitante_id              UUID        NULL,
    sector_id                   UUID        NULL,
    origen                      TEXT        NULL,
    regla_pcp_id                UUID        NULL,        -- referente llega en 0012 (reglas_pcp, PR2); sin FK hasta entonces
    notas                       TEXT        NULL,
    cerrada_at                  TIMESTAMPTZ NULL,
    cerrada_por                 UUID        NULL,
    created_by                  UUID        NULL,
    updated_by                  UUID        NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_pcp_id_drog      UNIQUE (id, drogueria_id),
    CONSTRAINT ck_pcp_estado       CHECK (estado IN ('nueva','en_gestion','esperando_respuesta','cerrada')),
    CONSTRAINT ck_pcp_origen       CHECK (origen IS NULL OR origen IN ('manual','regla','import_legado')),
    CONSTRAINT fk_pcp_drog         FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_pcp_presupuesto  FOREIGN KEY (presupuesto_id, drogueria_id)
                                    REFERENCES presupuestos (id, drogueria_id),
    CONSTRAINT fk_pcp_proceso      FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id),
    CONSTRAINT fk_pcp_solicitante  FOREIGN KEY (solicitante_id) REFERENCES usuarios (id),
    CONSTRAINT fk_pcp_sector       FOREIGN KEY (sector_id, drogueria_id)
                                    REFERENCES sectores_contacto (id, drogueria_id),
    CONSTRAINT fk_pcp_cerrada_por  FOREIGN KEY (cerrada_por) REFERENCES usuarios (id),
    CONSTRAINT fk_pcp_createdby    FOREIGN KEY (created_by) REFERENCES usuarios (id),
    CONSTRAINT fk_pcp_updatedby    FOREIGN KEY (updated_by) REFERENCES usuarios (id)
);
COMMENT ON TABLE pcp IS 'PCP: pedido de mejora de precio elevado a Compras a partir de un presupuesto. Un solo PCP abierto por presupuesto (uq_pcp_presupuesto_abierto). Ver openspec/changes/gestor-pcp/design.md D2.';
COMMENT ON COLUMN pcp.origen IS 'Como se origino el PCP en si (no confundir con pcp_renglones.origen, que es por renglon): manual | regla | import_legado.';
COMMENT ON COLUMN pcp.regla_pcp_id IS 'FK a reglas_pcp, creada recien en 0012_pcp_extras.sql (PR2). Columna nullable sin FK hasta entonces.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_pcp_presupuesto_abierto
    ON pcp (presupuesto_id)
    WHERE estado <> 'cerrada';

CREATE INDEX IF NOT EXISTS idx_pcp_listado
    ON pcp (drogueria_id, estado, fecha_entrega_solicitada)
    WHERE estado <> 'cerrada';

-- =============================================================================
-- M2 — pcp_renglones
-- Ancla en item_proceso_id (nunca presupuesto_items.id, que se borra e
-- inserta de nuevo en cada regeneracion del presupuesto — RN-PRICING-008).
-- cantidad y precio_referencia son snapshots tomados al momento de la
-- seleccion: sin FK a presupuesto_items, inmunes a la regeneracion.
-- =============================================================================
CREATE TABLE IF NOT EXISTS pcp_renglones (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID            NOT NULL,
    pcp_id              UUID            NOT NULL,
    item_proceso_id     UUID            NOT NULL,
    producto_id         UUID            NULL,
    cantidad            NUMERIC(12, 2)  NULL,
    precio_referencia   NUMERIC(15, 2)  NULL,
    origen              TEXT            NOT NULL,
    regla_pcp_id        UUID            NULL,       -- referente llega en 0012 (reglas_pcp, PR2); sin FK hasta entonces
    estado              TEXT            NOT NULL DEFAULT 'pendiente',
    created_by          UUID            NULL,
    updated_by          UUID            NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_pcpr_id_drog     UNIQUE (id, drogueria_id),
    CONSTRAINT uq_pcpr_pcp_item    UNIQUE (pcp_id, item_proceso_id),
    CONSTRAINT ck_pcpr_origen      CHECK (origen IN ('manual','regla','import_legado')),
    CONSTRAINT ck_pcpr_estado      CHECK (estado IN ('pendiente','resuelto','descartado')),
    CONSTRAINT fk_pcpr_drog        FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_pcpr_pcp         FOREIGN KEY (pcp_id, drogueria_id)
                                    REFERENCES pcp (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_pcpr_item        FOREIGN KEY (item_proceso_id, drogueria_id)
                                    REFERENCES items_proceso (id, drogueria_id),
    CONSTRAINT fk_pcpr_producto    FOREIGN KEY (producto_id) REFERENCES productos (id),
    CONSTRAINT fk_pcpr_createdby   FOREIGN KEY (created_by) REFERENCES usuarios (id),
    CONSTRAINT fk_pcpr_updatedby   FOREIGN KEY (updated_by) REFERENCES usuarios (id)
);
COMMENT ON TABLE pcp_renglones IS 'Renglon de un PCP, anclado en item_proceso_id (nunca presupuesto_items.id). cantidad/precio_referencia son snapshots al momento de la seleccion. Ver design.md D2.';
COMMENT ON COLUMN pcp_renglones.origen IS 'manual | regla | import_legado — discriminador que permite que seleccion manual, import legado y reglas automaticas futuras coexistan sin cambio de esquema.';

CREATE INDEX IF NOT EXISTS idx_pcpr_producto ON pcp_renglones (drogueria_id, producto_id);

-- =============================================================================
-- M3 — producto_proveedores (D3)
-- Catalogo real producto<->proveedor. Arranca vacio; alta ad-hoc durante la
-- gestion de un PCP es una escritura normal. Deliberadamente NO derivado de
-- precios_proveedor (eso es un log de cotizaciones, no un catalogo).
-- =============================================================================
CREATE TABLE IF NOT EXISTS producto_proveedores (
    id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID        NOT NULL,
    producto_id         UUID        NOT NULL,
    proveedor_id        UUID        NOT NULL,
    codigo_proveedor    TEXT        NULL,
    preferido           BOOLEAN     NOT NULL DEFAULT FALSE,
    activo              BOOLEAN     NOT NULL DEFAULT TRUE,
    notas               TEXT        NULL,
    created_by          UUID        NULL,
    updated_by          UUID        NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_ppv_id_drog       UNIQUE (id, drogueria_id),
    CONSTRAINT uq_ppv_producto_prov UNIQUE (drogueria_id, producto_id, proveedor_id),
    CONSTRAINT fk_ppv_drog          FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_ppv_producto      FOREIGN KEY (producto_id) REFERENCES productos (id),
    CONSTRAINT fk_ppv_proveedor     FOREIGN KEY (proveedor_id, drogueria_id)
                                     REFERENCES proveedores (id, drogueria_id),
    CONSTRAINT fk_ppv_createdby     FOREIGN KEY (created_by) REFERENCES usuarios (id),
    CONSTRAINT fk_ppv_updatedby     FOREIGN KEY (updated_by) REFERENCES usuarios (id)
);
COMMENT ON TABLE producto_proveedores IS 'Asociacion producto<->proveedor: catalogo real de "proveedores disponibles" para un producto. Arranca vacio (D3); NO se deriva de precios_proveedor.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_ppv_preferido
    ON producto_proveedores (drogueria_id, producto_id)
    WHERE preferido AND activo;

CREATE INDEX IF NOT EXISTS idx_ppv_producto_activo
    ON producto_proveedores (drogueria_id, producto_id)
    WHERE activo;

-- =============================================================================
-- M4 — pcp_renglon_resultados (D4)
-- precios_proveedor sigue siendo el registro de precio; esta tabla guarda el
-- RESULTADO de la negociacion (incluyendo no_cotiza, que nunca fabrica una
-- fila de precio). Invariante: precio_obtenido <=> precio_proveedor_id NOT NULL.
-- =============================================================================
CREATE TABLE IF NOT EXISTS pcp_renglon_resultados (
    id                      UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID        NOT NULL,
    pcp_renglon_id          UUID        NOT NULL,
    proveedor_id            UUID        NOT NULL,
    consulta_id             UUID        NULL,       -- referente llega en 0012 (pcp_consultas, PR2); sin FK hasta entonces
    resultado               TEXT        NOT NULL,
    precio_proveedor_id     UUID        NULL,
    motivo                  TEXT        NULL,
    registrado_por          UUID        NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_ppr_id_drog       UNIQUE (id, drogueria_id),
    CONSTRAINT uq_ppr_renglon_prov  UNIQUE (pcp_renglon_id, proveedor_id),
    CONSTRAINT ck_ppr_resultado_val CHECK (resultado IN ('precio_obtenido','no_cotiza','sin_respuesta')),
    CONSTRAINT ck_ppr_resultado     CHECK ((resultado = 'precio_obtenido') = (precio_proveedor_id IS NOT NULL)),
    CONSTRAINT fk_ppr_drog          FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_ppr_renglon       FOREIGN KEY (pcp_renglon_id, drogueria_id)
                                     REFERENCES pcp_renglones (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_ppr_proveedor     FOREIGN KEY (proveedor_id, drogueria_id)
                                     REFERENCES proveedores (id, drogueria_id),
    CONSTRAINT fk_ppr_precio_prov   FOREIGN KEY (precio_proveedor_id) REFERENCES precios_proveedor (id),
    CONSTRAINT fk_ppr_registrado    FOREIGN KEY (registrado_por) REFERENCES usuarios (id)
);
COMMENT ON TABLE pcp_renglon_resultados IS 'Resultado de negociacion por renglon-proveedor. Solo precio_obtenido escribe una fila en precios_proveedor; no_cotiza/sin_respuesta son outcome puro, nunca fabrican precio. Ver design.md D4.';
COMMENT ON CONSTRAINT ck_ppr_resultado ON pcp_renglon_resultados IS 'Invariante: resultado = precio_obtenido si y solo si precio_proveedor_id NOT NULL.';

-- =============================================================================
-- M5 — Triggers de updated_at, RLS + politicas, GRANTs, NOTIFY pgrst (D11)
-- Confirmado por el usuario: lectura de PCP restringida a compras/gerencia/
-- admin (+ superadmin, convencion estandar de soporte cross-tenant) —
-- comercial/lider_comercial no ven pantallas de PCP. Escritura identica a la
-- politica de precios_proveedor: admin, gerencia, compras.
-- =============================================================================

-- ---------- updated_at ----------
DROP TRIGGER IF EXISTS trg_pcp_updated_at ON pcp;
CREATE TRIGGER trg_pcp_updated_at
  BEFORE UPDATE ON pcp
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_pcp_renglones_updated_at ON pcp_renglones;
CREATE TRIGGER trg_pcp_renglones_updated_at
  BEFORE UPDATE ON pcp_renglones
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_producto_proveedores_updated_at ON producto_proveedores;
CREATE TRIGGER trg_producto_proveedores_updated_at
  BEFORE UPDATE ON producto_proveedores
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_pcp_renglon_resultados_updated_at ON pcp_renglon_resultados;
CREATE TRIGGER trg_pcp_renglon_resultados_updated_at
  BEFORE UPDATE ON pcp_renglon_resultados
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ---------- RLS ----------
ALTER TABLE pcp ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pcp_sel ON pcp;
CREATE POLICY pcp_sel ON pcp FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcp_ins ON pcp;
CREATE POLICY pcp_ins ON pcp FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcp_upd ON pcp;
CREATE POLICY pcp_upd ON pcp FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcp_del ON pcp;
CREATE POLICY pcp_del ON pcp FOR DELETE USING ((select es_superadmin()));

ALTER TABLE pcp_renglones ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pcpr_sel ON pcp_renglones;
CREATE POLICY pcpr_sel ON pcp_renglones FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpr_ins ON pcp_renglones;
CREATE POLICY pcpr_ins ON pcp_renglones FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpr_upd ON pcp_renglones;
CREATE POLICY pcpr_upd ON pcp_renglones FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS pcpr_del ON pcp_renglones;
CREATE POLICY pcpr_del ON pcp_renglones FOR DELETE USING ((select es_superadmin()));

ALTER TABLE producto_proveedores ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ppv_sel ON producto_proveedores;
CREATE POLICY ppv_sel ON producto_proveedores FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS ppv_ins ON producto_proveedores;
CREATE POLICY ppv_ins ON producto_proveedores FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS ppv_upd ON producto_proveedores;
CREATE POLICY ppv_upd ON producto_proveedores FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS ppv_del ON producto_proveedores;
CREATE POLICY ppv_del ON producto_proveedores FOR DELETE USING ((select es_superadmin()));

ALTER TABLE pcp_renglon_resultados ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ppr_sel ON pcp_renglon_resultados;
CREATE POLICY ppr_sel ON pcp_renglon_resultados FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS ppr_ins ON pcp_renglon_resultados;
CREATE POLICY ppr_ins ON pcp_renglon_resultados FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS ppr_upd ON pcp_renglon_resultados;
CREATE POLICY ppr_upd ON pcp_renglon_resultados FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS ppr_del ON pcp_renglon_resultados;
CREATE POLICY ppr_del ON pcp_renglon_resultados FOR DELETE USING ((select es_superadmin()));

-- ---------- GRANTs explicitos ----------
-- Supabase no autoexpone tablas nuevas al Data API (precedente: 0007, 0008).
-- Sin DELETE para authenticated: la API nunca borra fisicamente estas filas,
-- solo RLS + service_role para mantenimiento administrativo.
GRANT SELECT, INSERT, UPDATE, DELETE ON
    pcp, pcp_renglones, producto_proveedores, pcp_renglon_resultados
  TO service_role;
GRANT SELECT, INSERT, UPDATE ON
    pcp, pcp_renglones, producto_proveedores, pcp_renglon_resultados
  TO authenticated;

-- Forzar reload de PostgREST para que detecte las tablas nuevas
NOTIFY pgrst, 'reload schema';
