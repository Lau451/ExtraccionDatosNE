-- =============================================================================
-- Migration 0005: Ampliar tipos de licitación y agregar columna cliente
--
-- Cambios:
--   1. Reemplaza el CHECK constraint de tipo para incluir 'panales' y 'formulas'
--   2. ADD COLUMN cliente TEXT (nullable, texto libre)
-- =============================================================================

-- Ampliar CHECK constraint de tipo
ALTER TABLE licitaciones DROP CONSTRAINT IF EXISTS licitaciones_tipo_check;
ALTER TABLE licitaciones ADD CONSTRAINT licitaciones_tipo_check
  CHECK (tipo IN ('descartables', 'medicamentos', 'soluciones', 'panales', 'formulas'));

-- Nueva columna cliente
ALTER TABLE licitaciones ADD COLUMN IF NOT EXISTS cliente TEXT;

NOTIFY pgrst, 'reload schema';

COMMENT ON COLUMN licitaciones.cliente IS
  'Nombre del cliente o institución a la que pertenece la licitación. Opcional.';
