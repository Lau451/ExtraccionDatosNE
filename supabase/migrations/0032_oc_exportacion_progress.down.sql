-- Down migration para 0032.
-- AVISO: se pierde el registro de qué OC se exportaron a Progress; los
-- archivos CSV ya escritos en disco quedan.

DROP VIEW IF EXISTS v_compromisos_entregas;
DROP INDEX IF EXISTS idx_oc_exportadas;
ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS ck_oc_exportacion;
ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS fk_oc_exportadopor;
ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS archivo_exportado;
ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS exportado_por;
ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS exportado_at;

NOTIFY pgrst, 'reload schema';
