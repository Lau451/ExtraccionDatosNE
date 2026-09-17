-- Down migration para 0018_productos_rls_performance.sql
-- Vuelve al patron original (mismo_tenant(tabla.columna)), mas lento pero
-- semanticamente identico.

DROP POLICY IF EXISTS prod_sel ON productos;
CREATE POLICY prod_sel ON productos FOR SELECT
  USING ((select mismo_tenant(productos.drogueria_id)));

DROP POLICY IF EXISTS prod_ins ON productos;
CREATE POLICY prod_ins ON productos FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(productos.drogueria_id)));

DROP POLICY IF EXISTS prod_upd ON productos;
CREATE POLICY prod_upd ON productos FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(productos.drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(productos.drogueria_id)));

NOTIFY pgrst, 'reload schema';
