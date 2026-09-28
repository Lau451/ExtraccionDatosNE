-- Down migration para 0031.

ALTER TABLE productos DROP CONSTRAINT IF EXISTS ck_productos_unidades_por_presentacion;
ALTER TABLE productos DROP COLUMN IF EXISTS unidades_por_presentacion;

NOTIFY pgrst, 'reload schema';
