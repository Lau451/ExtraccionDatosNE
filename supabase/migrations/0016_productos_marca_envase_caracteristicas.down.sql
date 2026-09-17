-- =============================================================================
-- Reversion manual de 0016_productos_marca_envase_caracteristicas.sql
--
-- NO la ejecuta `supabase db push` (no es un archivo de migracion numerado
-- estandar); es un script para correr a mano si hace falta revertir.
--
-- Orden: politicas/GRANTs primero, despues el ALTER de productos (dropea las
-- columnas y FKs agregadas), despues las tablas nuevas hijo antes que padre
-- (producto_caracteristicas depende de caracteristicas y de productos;
-- marcas/envases/caracteristicas no dependen entre si).
-- =============================================================================

-- ---------- Reversion de M6: politicas, GRANTs ----------
DROP POLICY IF EXISTS marc_sel ON marcas;
DROP POLICY IF EXISTS marc_ins ON marcas;
DROP POLICY IF EXISTS marc_upd ON marcas;
DROP POLICY IF EXISTS marc_del ON marcas;

DROP POLICY IF EXISTS env_sel ON envases;
DROP POLICY IF EXISTS env_ins ON envases;
DROP POLICY IF EXISTS env_upd ON envases;
DROP POLICY IF EXISTS env_del ON envases;

DROP POLICY IF EXISTS car_sel ON caracteristicas;
DROP POLICY IF EXISTS car_ins ON caracteristicas;
DROP POLICY IF EXISTS car_upd ON caracteristicas;
DROP POLICY IF EXISTS car_del ON caracteristicas;

DROP POLICY IF EXISTS prodcar_sel ON producto_caracteristicas;
DROP POLICY IF EXISTS prodcar_ins ON producto_caracteristicas;
DROP POLICY IF EXISTS prodcar_del ON producto_caracteristicas;

REVOKE ALL ON marcas, envases, caracteristicas, producto_caracteristicas
  FROM service_role, authenticated;

-- ---------- Reversion de M5: ALTER productos ----------
ALTER TABLE productos
  DROP CONSTRAINT IF EXISTS fk_prod_marca,
  DROP CONSTRAINT IF EXISTS fk_prod_envase,
  DROP CONSTRAINT IF EXISTS ck_prod_alicuota_iva;

ALTER TABLE productos
  DROP COLUMN IF EXISTS marca_id,
  DROP COLUMN IF EXISTS envase_id,
  DROP COLUMN IF EXISTS alicuota_iva;

-- ---------- Reversion de M4, M3, M2, M1: tablas (hijos primero) ----------
DROP TABLE IF EXISTS producto_caracteristicas;
DROP TABLE IF EXISTS caracteristicas;
DROP TABLE IF EXISTS envases;
DROP TABLE IF EXISTS marcas;

NOTIFY pgrst, 'reload schema';
