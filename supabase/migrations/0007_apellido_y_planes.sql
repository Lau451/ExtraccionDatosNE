-- =============================================================================
-- Migration 0007: apellido en usuarios + tabla planes
--
-- Soporte de schema para el módulo de autenticación/gestión de usuarios
-- completo: invitación por email, "Mi cuenta" (nombre + apellido separados),
-- y estructura de planes por droguería (sin lógica de facturación todavía).
--
-- Cambios:
--   1. ALTER TABLE usuarios ADD COLUMN apellido
--   2. CREATE TABLE planes
--   3. ALTER TABLE droguerias ADD COLUMN plan_id (FK nullable a planes)
--   4. RLS de planes: lectura para cualquier autenticado, escritura solo superadmin
--   5. GRANTs explícitos (tablas nuevas no se auto-exponen al Data API)
-- =============================================================================

-- ======================
-- usuarios.apellido
-- ======================
ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS apellido TEXT;

COMMENT ON COLUMN usuarios.apellido IS
  'Apellido del usuario. Nullable: usuarios creados antes de esta migración no tienen valor de backfill posible.';

-- ======================
-- Tabla: planes
-- ======================
CREATE TABLE IF NOT EXISTS planes (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

  nombre                TEXT        NOT NULL,

  -- Límites (nullable = sin límite). Sin enforcement todavía; solo estructura
  -- para soportar facturación/límites en una iteración futura.
  max_usuarios          INT,
  max_documentos_mes    INT,
  almacenamiento_mb     INT,

  -- Funcionalidades habilitadas por plan, sin esquema fijo todavía.
  funcionalidades       JSONB       NOT NULL DEFAULT '{}'::jsonb,

  activo                BOOLEAN     NOT NULL DEFAULT TRUE,

  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_planes_updated_at ON planes;
CREATE TRIGGER trg_planes_updated_at
  BEFORE UPDATE ON planes
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ======================
-- droguerias.plan_id
-- ======================
ALTER TABLE droguerias
  ADD COLUMN IF NOT EXISTS plan_id UUID REFERENCES planes(id);

COMMENT ON COLUMN droguerias.plan_id IS
  'Plan asignado a la droguería. Nullable: sin plan asignado no restringe nada todavía (sin enforcement).';

CREATE INDEX IF NOT EXISTS idx_droguerias_plan_id
  ON droguerias(plan_id)
  WHERE plan_id IS NOT NULL;

-- ======================
-- RLS: planes
-- Catálogo de solo-lectura para cualquier autenticado (necesitan verlo al
-- elegir/mostrar el plan de su droguería); escritura acotada a superadmin.
-- Reusa es_superadmin(), ya definida en el proyecto.
-- ======================
ALTER TABLE planes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS planes_sel ON planes;
CREATE POLICY planes_sel ON planes
  FOR SELECT
  USING (auth.role() = 'authenticated');

DROP POLICY IF EXISTS planes_ins ON planes;
CREATE POLICY planes_ins ON planes
  FOR INSERT
  WITH CHECK ((select es_superadmin()));

DROP POLICY IF EXISTS planes_upd ON planes;
CREATE POLICY planes_upd ON planes
  FOR UPDATE
  USING ((select es_superadmin()))
  WITH CHECK ((select es_superadmin()));

DROP POLICY IF EXISTS planes_del ON planes;
CREATE POLICY planes_del ON planes
  FOR DELETE
  USING ((select es_superadmin()));

-- ======================
-- GRANTs explícitos
-- (Supabase no auto-expone tablas nuevas al Data API)
-- ======================
GRANT SELECT, INSERT, UPDATE, DELETE ON planes TO service_role;
GRANT SELECT ON planes TO authenticated;

-- Forzar reload de PostgREST para que detecte la tabla nueva y la columna nueva
NOTIFY pgrst, 'reload schema';

COMMENT ON TABLE planes IS
  'Catálogo de planes por droguería. Solo estructura: sin lógica de facturación ni enforcement de límites todavía.';
