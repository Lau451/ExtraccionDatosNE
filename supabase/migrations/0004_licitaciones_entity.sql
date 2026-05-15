-- =============================================================================
-- Migration 0004: Entidad Licitaciones (gestión de negocio)
--
-- Introduce `licitaciones` como entidad de primer orden que agrupa N archivos
-- de extracción (comparativas, órdenes de compra, documentos de licitación)
-- bajo una misma licitación gestionada por el usuario.
--
-- Cambios:
--   1. CREATE TABLE licitaciones
--   2. ALTER TABLE extraction_results ADD COLUMN licitacion_id (FK nullable)
--   3. Índices para consultas frecuentes
--   4. RLS habilitada con policy permisiva (backend usa service_role)
--   5. GRANTs explícitos (tablas nuevas no se auto-exponen al Data API)
-- =============================================================================

-- ======================
-- Trigger updated_at (reutilizable)
-- ======================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ======================
-- Tabla: licitaciones
-- ======================
CREATE TABLE IF NOT EXISTS licitaciones (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Identificación
  nombre          TEXT        NOT NULL,

  -- Clasificación
  tipo            TEXT        NOT NULL
                              CHECK (tipo IN ('descartables', 'medicamentos', 'soluciones')),

  -- Fechas operativas
  apertura        DATE,                     -- fecha de apertura de sobres
  vencimiento     DATE,                     -- fecha límite de presentación/oferta

  -- Modalidad y gestión
  tipo_gestion    TEXT,                     -- texto libre: "directa", "concurso", etc.
  modalidad       TEXT        NOT NULL DEFAULT 'mail'
                              CHECK (modalidad IN ('mail', 'pliego')),

  -- Estado del ciclo de vida
  estado          TEXT        NOT NULL DEFAULT 'abierta'
                              CHECK (estado IN ('abierta', 'en_evaluacion', 'adjudicada', 'cerrada')),

  -- Económico
  monto_estimado  NUMERIC(14, 2),           -- ARS estimado; nullable hasta conocerse

  -- Notas libres
  notas           TEXT,

  -- Auditoría
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trigger updated_at para licitaciones
DROP TRIGGER IF EXISTS trg_licitaciones_updated_at ON licitaciones;
CREATE TRIGGER trg_licitaciones_updated_at
  BEFORE UPDATE ON licitaciones
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ======================
-- Vínculo con extraction_results (1 licitación → N archivos)
-- ======================
ALTER TABLE extraction_results
  ADD COLUMN IF NOT EXISTS licitacion_id UUID
  REFERENCES licitaciones(id) ON DELETE SET NULL;
-- ON DELETE SET NULL: borrar una licitación deja los archivos huérfanos (licitacion_id=NULL)
-- preservando el histórico de extracciones. La API previene el borrado con 409.

-- ======================
-- Índices
-- ======================

-- FK lookup desde extraction_results (filtro por licitación en historial)
CREATE INDEX IF NOT EXISTS idx_extraction_results_licitacion_id
  ON extraction_results(licitacion_id)
  WHERE licitacion_id IS NOT NULL;

-- Listado de licitaciones activas (caso de uso principal del selector de upload)
CREATE INDEX IF NOT EXISTS idx_licitaciones_estado_activas
  ON licitaciones(estado, nombre)
  WHERE estado IN ('abierta', 'en_evaluacion');

-- Búsqueda por tipo (filtros del panel)
CREATE INDEX IF NOT EXISTS idx_licitaciones_tipo
  ON licitaciones(tipo);

-- Vencimientos próximos (alertas futuras)
CREATE INDEX IF NOT EXISTS idx_licitaciones_vencimiento
  ON licitaciones(vencimiento)
  WHERE vencimiento IS NOT NULL AND estado <> 'cerrada';

-- Ordenamiento por fecha de creación (listado principal)
CREATE INDEX IF NOT EXISTS idx_licitaciones_created_at
  ON licitaciones(created_at DESC);

-- ======================
-- RLS
-- (backend usa service_role que bypassea RLS;
--  policy permisiva evita bloqueo accidental si se expone anon key)
-- ======================
ALTER TABLE licitaciones ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS licitaciones_all_access ON licitaciones;
CREATE POLICY licitaciones_all_access ON licitaciones
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- ======================
-- GRANTs explícitos
-- (Supabase no auto-expone tablas nuevas al Data API)
-- ======================
GRANT SELECT, INSERT, UPDATE, DELETE ON licitaciones TO service_role;
GRANT SELECT ON licitaciones TO anon, authenticated;

-- Forzar reload de PostgREST para que detecte la nueva tabla
NOTIFY pgrst, 'reload schema';

COMMENT ON TABLE licitaciones IS
  'Entidad de gestión: agrupa N extracciones (comparativas, OCs, docs) bajo una licitación de negocio.';
COMMENT ON COLUMN extraction_results.licitacion_id IS
  'FK opcional a licitaciones. NULL = archivo legacy o no clasificado. Válido de forma permanente.';
