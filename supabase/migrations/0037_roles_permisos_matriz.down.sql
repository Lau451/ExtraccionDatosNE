-- Down migration para 0037: restaura las políticas INSERT/UPDATE de
-- 0008_terceros_modelo.sql para terceros, tercero_direcciones, direccion_usos,
-- terceros_contactos y los catálogos sectores_contacto, condiciones_pago y
-- formas_pago.

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

DROP POLICY IF EXISTS sec_ins ON sectores_contacto;
CREATE POLICY sec_ins ON sectores_contacto FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS sec_upd ON sectores_contacto;
CREATE POLICY sec_upd ON sectores_contacto FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS cp_ins ON condiciones_pago;
CREATE POLICY cp_ins ON condiciones_pago FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS cp_upd ON condiciones_pago;
CREATE POLICY cp_upd ON condiciones_pago FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS fp_ins ON formas_pago;
CREATE POLICY fp_ins ON formas_pago FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS fp_upd ON formas_pago;
CREATE POLICY fp_upd ON formas_pago FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)));
