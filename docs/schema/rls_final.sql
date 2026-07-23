-- =============================================================================
-- RLS v15 — multi-tenant por drogueria, 6 roles por área
-- Aplicar después de extractor_ia_v15.sql
-- =============================================================================
-- Roles:
--   superadmin      → todas las droguerías, único que hace DELETE
--   admin           → configura y opera su droguería (usuarios, catálogos, todo)
--   gerencia        → supervisa: ve todo (costos, reglas, márgenes), aprueba,
--                     no opera (no gestiona usuarios ni catálogos)
--   lider_comercial → ciclo de venta + APRUEBA presupuestos (validación de
--                     aprobación en el BACKEND, no en la BD), NO ve costos ni reglas
--   comercial       → ciclo de venta, NO ve costos ni reglas, no aprueba
--   compras         → ciclo de compra (proveedores, precios, costos, stock)
--
-- NOTA sobre costos: RLS filtra filas, no columnas. comercial y lider_comercial
-- NO deben consultar costos_productos ni las columnas de costo de
-- presupuesto_items directamente. Usan la vista v_presupuesto_comercial
-- (definida al final, sin costo). La app dirige cada rol a la vista correcta.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- TABLA USUARIOS
-- -----------------------------------------------------------------------------
CREATE TABLE usuarios (
    id              UUID        NOT NULL,
    drogueria_id    UUID        NULL,
    rol             TEXT        NOT NULL,
    nombre          TEXT        NOT NULL,
    apellido        TEXT        NULL,
    es_sistema      BOOLEAN     NOT NULL DEFAULT FALSE,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_usuarios_auth       FOREIGN KEY (id)           REFERENCES auth.users (id) ON DELETE CASCADE,
    CONSTRAINT fk_usuarios_drogueria  FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT ck_usuarios_rol CHECK (rol IN ('superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras', 'sistema')),
    CONSTRAINT ck_usuarios_superadmin CHECK (
        (rol IN ('superadmin', 'sistema') AND drogueria_id IS NULL) OR
        (rol NOT IN ('superadmin', 'sistema') AND drogueria_id IS NOT NULL)
    ),
    CONSTRAINT ck_usuarios_es_sistema CHECK ((rol = 'sistema') = (es_sistema = TRUE))
);

COMMENT ON COLUMN usuarios.es_sistema IS 'TRUE para usuarios técnicos (SYSTEM, IA_AGENT, SCHEDULER) que ejecutan procesos automáticos. Existen en auth.users (login deshabilitado) para mantener un único origen de identidad; el backend los usa con service_role.';

CREATE INDEX idx_usuarios_drogueria ON usuarios (drogueria_id) WHERE drogueria_id IS NOT NULL;
CREATE TRIGGER t_u_usuarios BEFORE UPDATE ON usuarios FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();


-- -----------------------------------------------------------------------------
-- FUNCIONES AUXILIARES
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_drogueria_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT drogueria_id FROM usuarios WHERE id = auth.uid(); $$;

CREATE OR REPLACE FUNCTION get_rol()
RETURNS TEXT LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT rol FROM usuarios WHERE id = auth.uid(); $$;

CREATE OR REPLACE FUNCTION es_superadmin()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT EXISTS (SELECT 1 FROM usuarios WHERE id = auth.uid() AND rol = 'superadmin'); $$;

-- Pertenece a la droguería del recurso (o es superadmin)
CREATE OR REPLACE FUNCTION mismo_tenant(p_drogueria UUID)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT es_superadmin() OR p_drogueria = get_drogueria_id(); $$;

-- Por defecto Postgres da EXECUTE a PUBLIC (incluye anon) sobre toda función
-- nueva, y ADEMÁS Supabase otorga EXECUTE explícito a "anon" y "authenticated"
-- al crear una función en public. Hay que revocar ambos: PUBLIC y anon.
REVOKE EXECUTE ON FUNCTION get_drogueria_id() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION get_rol()          FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION es_superadmin()    FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION mismo_tenant(UUID) FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION get_drogueria_id() FROM anon;
REVOKE EXECUTE ON FUNCTION get_rol()          FROM anon;
REVOKE EXECUTE ON FUNCTION es_superadmin()    FROM anon;
REVOKE EXECUTE ON FUNCTION mismo_tenant(UUID) FROM anon;

GRANT EXECUTE ON FUNCTION get_drogueria_id() TO authenticated;
GRANT EXECUTE ON FUNCTION get_rol()          TO authenticated;
GRANT EXECUTE ON FUNCTION es_superadmin()    TO authenticated;
GRANT EXECUTE ON FUNCTION mismo_tenant(UUID) TO authenticated;


-- =============================================================================
-- POLÍTICAS
-- Convención por defecto:
--   SELECT: mismo tenant (todos los roles ven su droguería salvo restricción)
--   INSERT/UPDATE: según dominio del rol
--   DELETE: solo superadmin
-- =============================================================================

-- ---------- droguerias ----------
ALTER TABLE droguerias ENABLE ROW LEVEL SECURITY;
CREATE POLICY droguerias_sel ON droguerias FOR SELECT USING ((select es_superadmin()) OR id = (select get_drogueria_id()));
CREATE POLICY droguerias_ins ON droguerias FOR INSERT WITH CHECK ((select es_superadmin()));
CREATE POLICY droguerias_upd ON droguerias FOR UPDATE USING ((select es_superadmin()) OR ((select get_rol()) = 'admin' AND id = (select get_drogueria_id()))) WITH CHECK ((select es_superadmin()) OR ((select get_rol()) = 'admin' AND id = (select get_drogueria_id())));
CREATE POLICY droguerias_del ON droguerias FOR DELETE USING ((select es_superadmin()));

-- ---------- planes ----------
-- Catálogo de solo-lectura para cualquier autenticado; escritura solo superadmin.
-- Migración 0007 (supabase/migrations/). Solo estructura: sin enforcement de límites todavía.
ALTER TABLE planes ENABLE ROW LEVEL SECURITY;
CREATE POLICY planes_sel ON planes FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY planes_ins ON planes FOR INSERT WITH CHECK ((select es_superadmin()));
CREATE POLICY planes_upd ON planes FOR UPDATE USING ((select es_superadmin())) WITH CHECK ((select es_superadmin()));
CREATE POLICY planes_del ON planes FOR DELETE USING ((select es_superadmin()));

-- ---------- usuarios ----------
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
CREATE POLICY usuarios_sel ON usuarios FOR SELECT USING ((select es_superadmin()) OR drogueria_id = (select get_drogueria_id()) OR id = (select auth.uid()));
CREATE POLICY usuarios_ins ON usuarios FOR INSERT WITH CHECK (
    (select es_superadmin()) OR ((select get_rol()) = 'admin' AND drogueria_id = (select get_drogueria_id()) AND rol != 'superadmin')
);
CREATE POLICY usuarios_upd ON usuarios FOR UPDATE
USING ((select es_superadmin()) OR ((select get_rol()) = 'admin' AND drogueria_id = (select get_drogueria_id()) AND rol != 'superadmin'))
WITH CHECK ((select es_superadmin()) OR ((select get_rol()) = 'admin' AND drogueria_id = (select get_drogueria_id()) AND rol != 'superadmin'));
CREATE POLICY usuarios_del ON usuarios FOR DELETE USING ((select es_superadmin()));

-- ---------- clientes / CRM / contactos / formatos ----------
-- comercial gestiona; compras solo lee
ALTER TABLE clientes ENABLE ROW LEVEL SECURITY;
CREATE POLICY clientes_sel ON clientes FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY clientes_ins ON clientes FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY clientes_upd ON clientes FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY clientes_del ON clientes FOR DELETE USING ((select es_superadmin()));

ALTER TABLE cliente_contactos ENABLE ROW LEVEL SECURITY;
CREATE POLICY cc_sel ON cliente_contactos FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY cc_ins ON cliente_contactos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cc_upd ON cliente_contactos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cc_del ON cliente_contactos FOR DELETE USING ((select es_superadmin()));

-- CRM: gerencia también agrega notas
ALTER TABLE cliente_observaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY cobs_sel ON cliente_observaciones FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY cobs_ins ON cliente_observaciones FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cobs_upd ON cliente_observaciones FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cobs_del ON cliente_observaciones FOR DELETE USING ((select es_superadmin()));

ALTER TABLE cliente_formato_documentos ENABLE ROW LEVEL SECURITY;
CREATE POLICY cfmt_sel ON cliente_formato_documentos FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY cfmt_ins ON cliente_formato_documentos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cfmt_upd ON cliente_formato_documentos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cfmt_del ON cliente_formato_documentos FOR DELETE USING ((select es_superadmin()));

-- ---------- proveedores / precios_proveedor / compras_proveedor ----------
-- dominio de COMPRAS; comercial solo lee
ALTER TABLE proveedores ENABLE ROW LEVEL SECURITY;
CREATE POLICY prov_sel ON proveedores FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY prov_ins ON proveedores FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY prov_upd ON proveedores FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY prov_del ON proveedores FOR DELETE USING ((select es_superadmin()));

ALTER TABLE precios_proveedor ENABLE ROW LEVEL SECURITY;
CREATE POLICY pp_sel ON precios_proveedor FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY pp_ins ON precios_proveedor FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY pp_upd ON precios_proveedor FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY pp_del ON precios_proveedor FOR DELETE USING ((select es_superadmin()));

ALTER TABLE compras_proveedor ENABLE ROW LEVEL SECURITY;
CREATE POLICY compra_sel ON compras_proveedor FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY compra_ins ON compras_proveedor FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY compra_upd ON compras_proveedor FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY compra_del ON compras_proveedor FOR DELETE USING ((select es_superadmin()));

-- ---------- categorias ----------
ALTER TABLE categorias ENABLE ROW LEVEL SECURITY;
CREATE POLICY cat_sel ON categorias FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY cat_ins ON categorias FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cat_upd ON categorias FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cat_del ON categorias FOR DELETE USING ((select es_superadmin()));

-- ---------- productos ----------
-- catálogo: lo gestiona compras/admin; comercial lo lee (para matching)
ALTER TABLE productos ENABLE ROW LEVEL SECURITY;
CREATE POLICY prod_sel ON productos FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY prod_ins ON productos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY prod_upd ON productos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY prod_del ON productos FOR DELETE USING ((select es_superadmin()));

-- ---------- costos_productos ----------
-- SENSIBLE: comercial y lider_comercial NO ven costos. Solo admin, gerencia, compras.
ALTER TABLE costos_productos ENABLE ROW LEVEL SECURITY;
CREATE POLICY cost_sel ON costos_productos FOR SELECT USING ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cost_ins ON costos_productos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cost_upd ON costos_productos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY cost_del ON costos_productos FOR DELETE USING ((select es_superadmin()));

-- ---------- stock_productos ----------
ALTER TABLE stock_productos ENABLE ROW LEVEL SECURITY;
CREATE POLICY stock_sel ON stock_productos FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY stock_ins ON stock_productos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY stock_upd ON stock_productos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY stock_del ON stock_productos FOR DELETE USING ((select es_superadmin()));

-- ---------- cliente_producto_alias ----------
ALTER TABLE cliente_producto_alias ENABLE ROW LEVEL SECURITY;
CREATE POLICY alias_sel ON cliente_producto_alias FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY alias_ins ON cliente_producto_alias FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY alias_upd ON cliente_producto_alias FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY alias_del ON cliente_producto_alias FOR DELETE USING ((select es_superadmin()));

-- ---------- procesos_comerciales ----------
ALTER TABLE procesos_comerciales ENABLE ROW LEVEL SECURITY;
CREATE POLICY proc_sel ON procesos_comerciales FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY proc_ins ON procesos_comerciales FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY proc_upd ON procesos_comerciales FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY proc_del ON procesos_comerciales FOR DELETE USING ((select es_superadmin()));

-- ---------- processing_sessions / extraction_results / chunk_results ----------
ALTER TABLE processing_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY ps_sel ON processing_sessions FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY ps_ins ON processing_sessions FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ps_upd ON processing_sessions FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ps_del ON processing_sessions FOR DELETE USING ((select es_superadmin()));

ALTER TABLE extraction_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY er_sel ON extraction_results FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY er_ins ON extraction_results FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY er_upd ON extraction_results FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY er_del ON extraction_results FOR DELETE USING ((select es_superadmin()));

ALTER TABLE chunk_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY chunk_sel ON chunk_results FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY chunk_ins ON chunk_results FOR INSERT WITH CHECK ((select mismo_tenant(drogueria_id)));
CREATE POLICY chunk_upd ON chunk_results FOR UPDATE USING ((select mismo_tenant(drogueria_id))) WITH CHECK ((select mismo_tenant(drogueria_id)));
CREATE POLICY chunk_del ON chunk_results FOR DELETE USING ((select es_superadmin()));

-- ---------- items_proceso (drogueria_id denormalizado, FK compuesta al padre) ----------
ALTER TABLE items_proceso ENABLE ROW LEVEL SECURITY;
CREATE POLICY ip_sel ON items_proceso FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY ip_ins ON items_proceso FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ip_upd ON items_proceso FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ip_del ON items_proceso FOR DELETE USING ((select es_superadmin()));

-- ---------- matching_candidatos (drogueria_id denormalizado) ----------
ALTER TABLE matching_candidatos ENABLE ROW LEVEL SECURITY;
CREATE POLICY mc_sel ON matching_candidatos FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY mc_ins ON matching_candidatos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY mc_upd ON matching_candidatos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY mc_del ON matching_candidatos FOR DELETE USING ((select es_superadmin()));

-- ---------- reglas_pricing ----------
-- SENSIBLE: solo admin y gerencia. comercial/lider/compras NO ven las reglas.
ALTER TABLE reglas_pricing ENABLE ROW LEVEL SECURITY;
CREATE POLICY rp_sel ON reglas_pricing FOR SELECT USING ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY rp_ins ON reglas_pricing FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY rp_upd ON reglas_pricing FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY rp_del ON reglas_pricing FOR DELETE USING ((select es_superadmin()));

-- ---------- presupuestos ----------
-- comercial y lider crean/editan. La transición a 'aprobado' (solo lider/gerencia/
-- admin) la valida el BACKEND antes del UPDATE; RLS solo garantiza tenant y rol de escritura.
ALTER TABLE presupuestos ENABLE ROW LEVEL SECURITY;
CREATE POLICY pre_sel ON presupuestos FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY pre_ins ON presupuestos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY pre_upd ON presupuestos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY pre_del ON presupuestos FOR DELETE USING ((select es_superadmin()));

-- ---------- presupuesto_items ----------
-- SENSIBLE (tiene costo_usado, margen). comercial/lider NO consultan esta tabla directo:
-- usan v_presupuesto_comercial (sin costo). Por eso el SELECT se limita a roles con costo.
-- comercial/lider igual pueden INSERT/UPDATE (precio, cantidad) porque arman el presupuesto,
-- pero la lectura de columnas de costo se resuelve por vista.
ALTER TABLE presupuesto_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY pi_sel ON presupuesto_items FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY pi_ins ON presupuesto_items FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY pi_upd ON presupuesto_items FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY pi_del ON presupuesto_items FOR DELETE USING ((select es_superadmin()));

-- ---------- comparativas / ofertas_items ----------
ALTER TABLE comparativas ENABLE ROW LEVEL SECURITY;
CREATE POLICY comp_sel ON comparativas FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY comp_ins ON comparativas FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY comp_upd ON comparativas FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY comp_del ON comparativas FOR DELETE USING ((select es_superadmin()));

ALTER TABLE ofertas_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY oi_sel ON ofertas_items FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY oi_ins ON ofertas_items FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY oi_upd ON ofertas_items FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY oi_del ON ofertas_items FOR DELETE USING ((select es_superadmin()));

-- ---------- ordenes_compra / oc_items / entregas (drogueria_id denormalizado) ----------
ALTER TABLE ordenes_compra ENABLE ROW LEVEL SECURITY;
CREATE POLICY oc_sel ON ordenes_compra FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY oc_ins ON ordenes_compra FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY oc_upd ON ordenes_compra FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY oc_del ON ordenes_compra FOR DELETE USING ((select es_superadmin()));

ALTER TABLE oc_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY oci_sel ON oc_items FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY oci_ins ON oc_items FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY oci_upd ON oc_items FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY oci_del ON oc_items FOR DELETE USING ((select es_superadmin()));

ALTER TABLE entregas_oc ENABLE ROW LEVEL SECURITY;
CREATE POLICY eoc_sel ON entregas_oc FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY eoc_ins ON entregas_oc FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY eoc_upd ON entregas_oc FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY eoc_del ON entregas_oc FOR DELETE USING ((select es_superadmin()));

ALTER TABLE entregas_oc_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY eoci_sel ON entregas_oc_items FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY eoci_ins ON entregas_oc_items FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY eoci_upd ON entregas_oc_items FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY eoci_del ON entregas_oc_items FOR DELETE USING ((select es_superadmin()));


-- =============================================================================
-- LÓGICA DE NEGOCIO: VIVE EN EL BACKEND, NO EN LA BD
-- Esta BD solo garantiza integridad (CHECKs, FKs, únicos) y aislamiento
-- (RLS multi-tenant + roles). El backend implementa: alta de usuarios,
-- aprobación de presupuestos, matching, motor de pricing, stock comprometido,
-- validación de extracciones e imports. Ver prompt_backend.md.
-- =============================================================================


-- =============================================================================
-- VISTA PARA COMERCIAL: presupuesto SIN costos (solo margen %)
-- comercial y lider_comercial consultan ESTA vista, no presupuesto_items directo.
-- =============================================================================
CREATE OR REPLACE VIEW v_presupuesto_comercial AS
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
    pi.margen_resultante_pct,          -- ve el margen %
    pi.precio_mercado_usado,           -- ve la referencia de mercado
    pi.metodo_precio,
    pi.stock_verificado,
    pi.stock_al_generar,
    pi.excluido,
    pi.motivo_exclusion
    -- NO expone: costo_usado, origen_costo, precio_proveedor_id, detalle_calculo
FROM presupuestos p
JOIN procesos_comerciales proc ON proc.id = p.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
JOIN presupuesto_items pi      ON pi.presupuesto_id = p.id
JOIN items_proceso ip          ON ip.id = pi.item_proceso_id
LEFT JOIN productos prod       ON prod.id = pi.producto_id;

COMMENT ON VIEW v_presupuesto_comercial IS 'Presupuesto para roles comerciales: muestra precio, margen % y referencia de mercado, pero NUNCA el costo crudo. comercial y lider_comercial usan esta vista; admin/gerencia usan v_presupuesto_revision (con costo).';

-- security_invoker: sin esto, la vista corre con privilegios del creador
-- y podría ignorar el RLS de comparativas/presupuestos del usuario real.
ALTER VIEW v_presupuesto_comercial SET (security_invoker = on);


-- =============================================================================
-- FKs hacia "usuarios" — van acá porque usuarios recién existe en este archivo.
-- Cubre: created_by/updated_by/deleted_by de las entidades de negocio, los
-- *_por unificados a UUID, y las FKs de las 9 tablas nuevas de eventos/
-- automatizaciones/notificaciones que apuntan a usuarios.
-- =============================================================================

-- auditoría en entidades de negocio existentes
ALTER TABLE clientes             ADD CONSTRAINT fk_cli_createdby  FOREIGN KEY (created_by) REFERENCES usuarios (id);
ALTER TABLE clientes             ADD CONSTRAINT fk_cli_updatedby  FOREIGN KEY (updated_by) REFERENCES usuarios (id);
ALTER TABLE clientes             ADD CONSTRAINT fk_cli_deletedby  FOREIGN KEY (deleted_by) REFERENCES usuarios (id);
ALTER TABLE productos            ADD CONSTRAINT fk_prod_createdby FOREIGN KEY (created_by) REFERENCES usuarios (id);
ALTER TABLE productos            ADD CONSTRAINT fk_prod_updatedby FOREIGN KEY (updated_by) REFERENCES usuarios (id);
ALTER TABLE productos            ADD CONSTRAINT fk_prod_deletedby FOREIGN KEY (deleted_by) REFERENCES usuarios (id);
ALTER TABLE proveedores          ADD CONSTRAINT fk_prov_createdby FOREIGN KEY (created_by) REFERENCES usuarios (id);
ALTER TABLE proveedores          ADD CONSTRAINT fk_prov_updatedby FOREIGN KEY (updated_by) REFERENCES usuarios (id);
ALTER TABLE proveedores          ADD CONSTRAINT fk_prov_deletedby FOREIGN KEY (deleted_by) REFERENCES usuarios (id);
ALTER TABLE procesos_comerciales ADD CONSTRAINT fk_proc_createdby FOREIGN KEY (created_by) REFERENCES usuarios (id);
ALTER TABLE procesos_comerciales ADD CONSTRAINT fk_proc_updatedby FOREIGN KEY (updated_by) REFERENCES usuarios (id);
ALTER TABLE procesos_comerciales ADD CONSTRAINT fk_proc_deletedby FOREIGN KEY (deleted_by) REFERENCES usuarios (id);
ALTER TABLE presupuestos         ADD CONSTRAINT fk_pre_createdby  FOREIGN KEY (created_by) REFERENCES usuarios (id);
ALTER TABLE presupuestos         ADD CONSTRAINT fk_pre_updatedby  FOREIGN KEY (updated_by) REFERENCES usuarios (id);
ALTER TABLE presupuestos         ADD CONSTRAINT fk_pre_deletedby  FOREIGN KEY (deleted_by) REFERENCES usuarios (id);
ALTER TABLE comparativas         ADD CONSTRAINT fk_comp_createdby FOREIGN KEY (created_by) REFERENCES usuarios (id);
ALTER TABLE comparativas         ADD CONSTRAINT fk_comp_updatedby FOREIGN KEY (updated_by) REFERENCES usuarios (id);
ALTER TABLE comparativas         ADD CONSTRAINT fk_comp_deletedby FOREIGN KEY (deleted_by) REFERENCES usuarios (id);
ALTER TABLE ordenes_compra       ADD CONSTRAINT fk_oc_createdby   FOREIGN KEY (created_by) REFERENCES usuarios (id);
ALTER TABLE ordenes_compra       ADD CONSTRAINT fk_oc_updatedby   FOREIGN KEY (updated_by) REFERENCES usuarios (id);
ALTER TABLE ordenes_compra       ADD CONSTRAINT fk_oc_deletedby   FOREIGN KEY (deleted_by) REFERENCES usuarios (id);

-- los *_por unificados a UUID (antes TEXT)
ALTER TABLE cliente_observaciones      ADD CONSTRAINT fk_cobs_creadopor  FOREIGN KEY (creado_por)          REFERENCES usuarios (id);
ALTER TABLE cliente_formato_documentos ADD CONSTRAINT fk_cfmt_actualiz   FOREIGN KEY (actualizado_por)     REFERENCES usuarios (id);
ALTER TABLE cliente_producto_alias     ADD CONSTRAINT fk_alias_creadopor FOREIGN KEY (creado_por)          REFERENCES usuarios (id);
ALTER TABLE precios_proveedor          ADD CONSTRAINT fk_pp_creadopor    FOREIGN KEY (creado_por)          REFERENCES usuarios (id);
ALTER TABLE extraction_results         ADD CONSTRAINT fk_er_validadopor  FOREIGN KEY (validado_por)        REFERENCES usuarios (id);
ALTER TABLE presupuestos               ADD CONSTRAINT fk_pre_aprobadopor FOREIGN KEY (aprobado_por)        REFERENCES usuarios (id);
ALTER TABLE presupuestos               ADD CONSTRAINT fk_pre_presentapor FOREIGN KEY (presentado_por)      REFERENCES usuarios (id);
ALTER TABLE presupuesto_items          ADD CONSTRAINT fk_pi_ajustadopor  FOREIGN KEY (precio_ajustado_por) REFERENCES usuarios (id);
ALTER TABLE compras_proveedor          ADD CONSTRAINT fk_cp_creadopor    FOREIGN KEY (creado_por)          REFERENCES usuarios (id);

-- eventos / eventos_recurrentes
ALTER TABLE eventos             ADD CONSTRAINT fk_ev_resp       FOREIGN KEY (responsable_id) REFERENCES usuarios (id);
ALTER TABLE eventos             ADD CONSTRAINT fk_ev_createdby  FOREIGN KEY (created_by)     REFERENCES usuarios (id);
ALTER TABLE eventos             ADD CONSTRAINT fk_ev_updatedby  FOREIGN KEY (updated_by)     REFERENCES usuarios (id);
ALTER TABLE eventos             ADD CONSTRAINT fk_ev_deletedby  FOREIGN KEY (deleted_by)     REFERENCES usuarios (id);
ALTER TABLE eventos_recurrentes ADD CONSTRAINT fk_evr_createdby FOREIGN KEY (created_by)     REFERENCES usuarios (id);
ALTER TABLE eventos_recurrentes ADD CONSTRAINT fk_evr_updatedby FOREIGN KEY (updated_by)     REFERENCES usuarios (id);
ALTER TABLE eventos_recurrentes ADD CONSTRAINT fk_evr_deletedby FOREIGN KEY (deleted_by)     REFERENCES usuarios (id);

-- historial_cambios / reglas_automatizacion / acciones_ejecutadas / proveedor_producto_alias
ALTER TABLE historial_cambios     ADD CONSTRAINT fk_hc_user      FOREIGN KEY (usuario_id)  REFERENCES usuarios (id);
ALTER TABLE reglas_automatizacion ADD CONSTRAINT fk_ra_createdby FOREIGN KEY (created_by)  REFERENCES usuarios (id);
ALTER TABLE reglas_automatizacion ADD CONSTRAINT fk_ra_updatedby FOREIGN KEY (updated_by)  REFERENCES usuarios (id);
ALTER TABLE proveedor_producto_alias ADD CONSTRAINT fk_ppa_creadopor FOREIGN KEY (creado_por) REFERENCES usuarios (id);

-- notificaciones
ALTER TABLE notificaciones            ADD CONSTRAINT fk_no_dest FOREIGN KEY (destinatario_id) REFERENCES usuarios (id);
ALTER TABLE notificacion_preferencias ADD CONSTRAINT fk_np_user FOREIGN KEY (usuario_id)      REFERENCES usuarios (id) ON DELETE CASCADE;


-- =============================================================================
-- VISTAS que dependen de "usuarios"
-- =============================================================================

CREATE VIEW v_calendario AS
SELECT
    e.id                AS evento_id,
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
    u.nombre            AS responsable,
    e.proceso_comercial_id,
    e.cliente_id,
    cl.nombre           AS cliente,
    CASE
        WHEN e.estado IN ('completado', 'cancelado') THEN FALSE
        WHEN e.fecha_limite IS NOT NULL AND e.fecha_limite < NOW() THEN TRUE
        ELSE FALSE
    END                 AS vencido
FROM eventos e
LEFT JOIN usuarios u ON u.id = e.responsable_id
LEFT JOIN clientes cl ON cl.id = e.cliente_id
WHERE e.deleted_at IS NULL;

COMMENT ON VIEW v_calendario IS 'El calendario del sistema como vista sobre eventos. vencido se deriva de fecha_limite vs ahora.';

ALTER VIEW v_calendario SET (security_invoker = on);

-- Enriquecer v_presupuesto_revision (definida en extractor_final.sql) con el
-- nombre de quien ajustó el precio, ahora que precio_ajustado_por es FK real.
CREATE OR REPLACE VIEW v_presupuesto_revision AS
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


-- =============================================================================
-- RLS de las tablas nuevas (eventos, automatizaciones, notificaciones)
-- =============================================================================

ALTER TABLE eventos ENABLE ROW LEVEL SECURITY;
CREATE POLICY ev_sel ON eventos FOR SELECT USING ((select mismo_tenant(drogueria_id)) AND deleted_at IS NULL);
CREATE POLICY ev_ins ON eventos FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ev_upd ON eventos FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ev_del ON eventos FOR DELETE USING ((select es_superadmin()));

ALTER TABLE eventos_recurrentes ENABLE ROW LEVEL SECURITY;
CREATE POLICY evr_sel ON eventos_recurrentes FOR SELECT USING ((select mismo_tenant(drogueria_id)) AND deleted_at IS NULL);
CREATE POLICY evr_ins ON eventos_recurrentes FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY evr_upd ON eventos_recurrentes FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY evr_del ON eventos_recurrentes FOR DELETE USING ((select es_superadmin()));

ALTER TABLE historial_cambios ENABLE ROW LEVEL SECURITY;
CREATE POLICY hc_sel ON historial_cambios FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY hc_ins ON historial_cambios FOR INSERT WITH CHECK ((select mismo_tenant(drogueria_id)));
CREATE POLICY hc_del ON historial_cambios FOR DELETE USING ((select es_superadmin()));
-- sin política de UPDATE: historial_cambios es INSERT-only por diseño

ALTER TABLE reglas_automatizacion ENABLE ROW LEVEL SECURITY;
CREATE POLICY ra_sel ON reglas_automatizacion FOR SELECT USING ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ra_ins ON reglas_automatizacion FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ra_upd ON reglas_automatizacion FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ra_del ON reglas_automatizacion FOR DELETE USING ((select es_superadmin()));

ALTER TABLE acciones_ejecutadas ENABLE ROW LEVEL SECURITY;
CREATE POLICY ae_sel ON acciones_ejecutadas FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY ae_ins ON acciones_ejecutadas FOR INSERT WITH CHECK ((select mismo_tenant(drogueria_id)));
CREATE POLICY ae_upd ON acciones_ejecutadas FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ae_del ON acciones_ejecutadas FOR DELETE USING ((select es_superadmin()));

ALTER TABLE proveedor_producto_alias ENABLE ROW LEVEL SECURITY;
CREATE POLICY ppa_sel ON proveedor_producto_alias FOR SELECT USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY ppa_ins ON proveedor_producto_alias FOR INSERT WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ppa_upd ON proveedor_producto_alias FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ppa_del ON proveedor_producto_alias FOR DELETE USING ((select es_superadmin()));

-- notificaciones: cada uno ve LAS SUYAS. admin/gerencia ven las de su droguería.
ALTER TABLE notificaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY no_sel ON notificaciones FOR SELECT USING (
    destinatario_id = (select auth.uid())
    OR ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
    OR (select es_superadmin())
);
CREATE POLICY no_ins ON notificaciones FOR INSERT WITH CHECK ((select mismo_tenant(drogueria_id)));
CREATE POLICY no_upd ON notificaciones FOR UPDATE
USING (destinatario_id = (select auth.uid()) OR (select es_superadmin()))
WITH CHECK (destinatario_id = (select auth.uid()) OR (select es_superadmin()));
CREATE POLICY no_del ON notificaciones FOR DELETE USING ((select es_superadmin()));

ALTER TABLE notificacion_entregas ENABLE ROW LEVEL SECURITY;
CREATE POLICY ne_sel ON notificacion_entregas FOR SELECT USING (
    EXISTS (SELECT 1 FROM notificaciones n WHERE n.id = notificacion_id AND n.destinatario_id = (select auth.uid()))
    OR ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
    OR (select es_superadmin())
);
CREATE POLICY ne_ins ON notificacion_entregas FOR INSERT WITH CHECK ((select mismo_tenant(drogueria_id)));
CREATE POLICY ne_upd ON notificacion_entregas FOR UPDATE USING ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id))) WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
CREATE POLICY ne_del ON notificacion_entregas FOR DELETE USING ((select es_superadmin()));
-- Nota: acá el EXISTS SÍ se mantiene a propósito — filtra por DESTINATARIO de
-- la notificación, no por tenant. No se puede denormalizar sin duplicar el
-- destinatario_id en cada fila de entrega.

ALTER TABLE notificacion_preferencias ENABLE ROW LEVEL SECURITY;
CREATE POLICY np_sel ON notificacion_preferencias FOR SELECT USING (
    usuario_id = (select auth.uid())
    OR ((select get_rol()) = 'admin' AND (select mismo_tenant(drogueria_id)))
    OR (select es_superadmin())
);
CREATE POLICY np_ins ON notificacion_preferencias FOR INSERT WITH CHECK (
    usuario_id = (select auth.uid()) AND (select mismo_tenant(drogueria_id))
);
CREATE POLICY np_upd ON notificacion_preferencias FOR UPDATE
USING (usuario_id = (select auth.uid()) OR (select es_superadmin()))
WITH CHECK (usuario_id = (select auth.uid()) OR (select es_superadmin()));
CREATE POLICY np_del ON notificacion_preferencias FOR DELETE USING (
    usuario_id = (select auth.uid()) OR (select es_superadmin())
);


-- =============================================================================
-- PRIMER SUPERADMIN (una vez, tras crear el usuario en Supabase Auth)
-- INSERT INTO usuarios (id, drogueria_id, rol, nombre)
-- VALUES ('uuid-del-auth-user', NULL, 'superadmin', 'Tu Nombre');
--
-- USUARIOS TÉCNICOS (SYSTEM / IA_AGENT / SCHEDULER) — crear también en
-- Supabase Auth (Admin API, login deshabilitado) y luego:
-- INSERT INTO usuarios (id, drogueria_id, rol, nombre, es_sistema) VALUES
--   ('<uuid-auth-system>',    NULL, 'sistema', 'SYSTEM',    TRUE),
--   ('<uuid-auth-ia-agent>',  NULL, 'sistema', 'IA_AGENT',  TRUE),
--   ('<uuid-auth-scheduler>', NULL, 'sistema', 'SCHEDULER', TRUE);
-- =============================================================================
