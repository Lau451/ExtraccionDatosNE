-- =============================================================================
-- 0037: matriz de roles (odd/tasks/roles-permisos-matriz.md S4/S5) -- alinea la
-- RLS de escritura de terceros y catálogos de apoyo con los guards del backend
-- (defensa en profundidad: los routers escriben con service client, así que
-- require_roles sigue siendo el guard efectivo).
--
-- S4: terceros, tercero_direcciones, direccion_usos y terceros_contactos se
-- escriben solo desde admin, gerencia y lider_comercial (comercial y compras
-- pierden la escritura; la lectura *_sel no cambia).
-- S5: sectores_contacto, condiciones_pago y formas_pago suman lider_comercial.
--
-- terceros_legacy_map (tlm_*) no cambia: lo escribe el import legado de
-- clientes/proveedores, cuyo rol-set (admin, gerencia, compras) está fuera de
-- esta matriz. Las políticas *_sel y *_del de 0008 tampoco cambian.
-- =============================================================================

DROP POLICY IF EXISTS terceros_ins ON terceros;
CREATE POLICY terceros_ins ON terceros FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS terceros_upd ON terceros;
CREATE POLICY terceros_upd ON terceros FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS tdir_ins ON tercero_direcciones;
CREATE POLICY tdir_ins ON tercero_direcciones FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tdir_upd ON tercero_direcciones;
CREATE POLICY tdir_upd ON tercero_direcciones FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS du_ins ON direccion_usos;
CREATE POLICY du_ins ON direccion_usos FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS du_upd ON direccion_usos;
CREATE POLICY du_upd ON direccion_usos FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS tc_ins ON terceros_contactos;
CREATE POLICY tc_ins ON terceros_contactos FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS tc_upd ON terceros_contactos;
CREATE POLICY tc_upd ON terceros_contactos FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS sec_ins ON sectores_contacto;
CREATE POLICY sec_ins ON sectores_contacto FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS sec_upd ON sectores_contacto;
CREATE POLICY sec_upd ON sectores_contacto FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS cp_ins ON condiciones_pago;
CREATE POLICY cp_ins ON condiciones_pago FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS cp_upd ON condiciones_pago;
CREATE POLICY cp_upd ON condiciones_pago FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS fp_ins ON formas_pago;
CREATE POLICY fp_ins ON formas_pago FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS fp_upd ON formas_pago;
CREATE POLICY fp_upd ON formas_pago FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial')
              AND (select mismo_tenant(drogueria_id)));
