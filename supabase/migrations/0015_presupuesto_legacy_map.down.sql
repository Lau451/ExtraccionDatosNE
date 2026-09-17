DROP POLICY IF EXISTS prelm_sel ON presupuesto_legacy_map;
DROP POLICY IF EXISTS prelm_ins ON presupuesto_legacy_map;
DROP POLICY IF EXISTS prelm_upd ON presupuesto_legacy_map;
DROP POLICY IF EXISTS prelm_del ON presupuesto_legacy_map;

REVOKE ALL ON presupuesto_legacy_map FROM authenticated;
REVOKE ALL ON presupuesto_legacy_map FROM service_role;

DROP TABLE IF EXISTS presupuesto_legacy_map;

NOTIFY pgrst, 'reload schema';
