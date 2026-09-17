-- =============================================================================
-- Migration 0015: idempotencia del import legado de presupuestos
--
-- Mirror deliberado de pcp_legacy_map (0012 M3, design.md D8): mismo esqueleto
-- de columnas y constraints, solo cambia a que apunta -- presupuesto_id en vez
-- de pcp_id. Guarda solo presupuesto_id (nunca proceso_comercial_id): esa
-- tabla ya lo trae en su propia fila, mismo criterio de no-duplicar dato que
-- pcp_legacy_map ya aplica.
--
-- Motivo por el que hace falta una tabla propia (y no reusar pcp_legacy_map):
-- el import de PCP siempre crea su placeholder de presupuesto junto con el
-- PCP (mismo run), así que nunca necesitó buscar un presupuesto por su cuenta.
-- El import de presupuestos legados corre SOLO y PRIMERO -- el import de PCP
-- lo referencia después por numero_presupuesto y debe poder encontrarlo sin
-- que exista ningún PCP todavía.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'import de presupuestos legados requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS presupuesto_legacy_map (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    presupuesto_id  UUID        NOT NULL,
    drogueria_id    UUID        NOT NULL,
    sistema_origen  TEXT        NOT NULL DEFAULT 'legacy',
    codigo_legacy   TEXT        NOT NULL,
    datos_legacy    JSONB       NULL,
    importado_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_prelm_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT uq_prelm_codigo  UNIQUE (drogueria_id, sistema_origen, codigo_legacy),
    CONSTRAINT fk_prelm_presupuesto FOREIGN KEY (presupuesto_id, drogueria_id)
                                    REFERENCES presupuestos (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_prelm_drog        FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON TABLE presupuesto_legacy_map IS 'Clave de idempotencia del import legado de presupuestos. uq_prelm_codigo (drogueria_id, sistema_origen, codigo_legacy=numero_presupuesto) es la que un reimport usa via ON CONFLICT / lookup para no duplicar el proceso_comercial+presupuesto ya creado.';

-- ---------- RLS: presupuesto_legacy_map (mismo patron que pcp_legacy_map) ----------
ALTER TABLE presupuesto_legacy_map ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS prelm_sel ON presupuesto_legacy_map;
CREATE POLICY prelm_sel ON presupuesto_legacy_map FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS prelm_ins ON presupuesto_legacy_map;
CREATE POLICY prelm_ins ON presupuesto_legacy_map FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS prelm_upd ON presupuesto_legacy_map;
CREATE POLICY prelm_upd ON presupuesto_legacy_map FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS prelm_del ON presupuesto_legacy_map;
CREATE POLICY prelm_del ON presupuesto_legacy_map FOR DELETE USING ((select es_superadmin()));

-- ---------- GRANTs explicitos ----------
-- Supabase no autoexpone tablas nuevas al Data API (precedente: 0007, 0008,
-- 0011, 0012). Sin DELETE para authenticated: la API nunca borra fisicamente
-- estas filas, solo RLS + service_role para mantenimiento administrativo.
GRANT SELECT, INSERT, UPDATE, DELETE ON presupuesto_legacy_map TO service_role;
GRANT SELECT, INSERT, UPDATE ON presupuesto_legacy_map TO authenticated;

-- Forzar reload de PostgREST para que detecte la tabla nueva
NOTIFY pgrst, 'reload schema';
