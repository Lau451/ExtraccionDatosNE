-- Down migration para 0042: se quitan las columnas de código postal y notas de
-- la dirección de entrega. Lo que tuvieran se pierde.

ALTER TABLE ordenes_compra
    DROP COLUMN IF EXISTS codigo_postal_entrega,
    DROP COLUMN IF EXISTS notas_entrega;

COMMENT ON COLUMN ordenes_compra.direccion_entrega IS NULL;

NOTIFY pgrst, 'reload schema';
