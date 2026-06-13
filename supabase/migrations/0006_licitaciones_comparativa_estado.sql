ALTER TABLE licitaciones
  ADD COLUMN IF NOT EXISTS comparativa_estado TEXT DEFAULT NULL;

ALTER TABLE licitaciones DROP CONSTRAINT IF EXISTS licitaciones_comparativa_estado_check;
ALTER TABLE licitaciones ADD CONSTRAINT licitaciones_comparativa_estado_check
  CHECK (comparativa_estado IS NULL OR comparativa_estado = 'pedida');

NOTIFY pgrst, 'reload schema';

COMMENT ON COLUMN licitaciones.comparativa_estado IS
  'Estado manual de la comparativa. NULL = sin comparativa; ''pedida'' = solicitada al proveedor. '
  'El estado ''cargada'' NO se persiste: se deriva de la existencia de un extraction_result '
  'con document_type=''comparativa'' vinculado a esta licitación.';
