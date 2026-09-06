-- =============================================================================
-- Reversion manual de 0011_pcp_modelo.sql
--
-- NO la ejecuta `supabase db push` (no es un archivo de migracion numerado
-- estandar); es un script para correr a mano si hace falta revertir. Segura
-- en cualquier momento: las cuatro tablas son aditivas puras y nada fuera de
-- services/pcp/ las lee todavia (design.md, "Rollback Plan").
--
-- Orden: hijos antes que padres (pcp_renglon_resultados y
-- producto_proveedores no dependen entre si; pcp_renglones depende de pcp;
-- pcp no depende de ninguna de las otras tres).
-- =============================================================================

-- ---------- Reversion de M5: politicas, RLS, triggers, GRANTs ----------
DROP POLICY IF EXISTS pcp_sel ON pcp;
DROP POLICY IF EXISTS pcp_ins ON pcp;
DROP POLICY IF EXISTS pcp_upd ON pcp;
DROP POLICY IF EXISTS pcp_del ON pcp;

DROP POLICY IF EXISTS pcpr_sel ON pcp_renglones;
DROP POLICY IF EXISTS pcpr_ins ON pcp_renglones;
DROP POLICY IF EXISTS pcpr_upd ON pcp_renglones;
DROP POLICY IF EXISTS pcpr_del ON pcp_renglones;

DROP POLICY IF EXISTS ppv_sel ON producto_proveedores;
DROP POLICY IF EXISTS ppv_ins ON producto_proveedores;
DROP POLICY IF EXISTS ppv_upd ON producto_proveedores;
DROP POLICY IF EXISTS ppv_del ON producto_proveedores;

DROP POLICY IF EXISTS ppr_sel ON pcp_renglon_resultados;
DROP POLICY IF EXISTS ppr_ins ON pcp_renglon_resultados;
DROP POLICY IF EXISTS ppr_upd ON pcp_renglon_resultados;
DROP POLICY IF EXISTS ppr_del ON pcp_renglon_resultados;

REVOKE ALL ON pcp, pcp_renglones, producto_proveedores, pcp_renglon_resultados
  FROM service_role, authenticated;

DROP TRIGGER IF EXISTS trg_pcp_updated_at                   ON pcp;
DROP TRIGGER IF EXISTS trg_pcp_renglones_updated_at         ON pcp_renglones;
DROP TRIGGER IF EXISTS trg_producto_proveedores_updated_at  ON producto_proveedores;
DROP TRIGGER IF EXISTS trg_pcp_renglon_resultados_updated_at ON pcp_renglon_resultados;

-- ---------- Reversion de M4, M3, M2, M1: tablas (hijos primero) ----------
DROP TABLE IF EXISTS pcp_renglon_resultados;
DROP TABLE IF EXISTS producto_proveedores;
DROP TABLE IF EXISTS pcp_renglones;
DROP TABLE IF EXISTS pcp;

NOTIFY pgrst, 'reload schema';
