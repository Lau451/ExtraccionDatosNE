-- Down migration para 0021_productos_clasificacion_reactivo_cosmetico.sql

ALTER TABLE productos DROP CONSTRAINT ck_productos_clasificacion;

UPDATE productos SET clasificacion = 'insumo' WHERE clasificacion = 'reactivo';
UPDATE productos SET clasificacion = 'perfumeria' WHERE clasificacion = 'cosmetico';

ALTER TABLE productos ADD CONSTRAINT ck_productos_clasificacion CHECK (
    clasificacion IS NULL OR clasificacion IN (
        'medicamento', 'descartable', 'solucion', 'nutricion',
        'insumo', 'equipamiento', 'perfumeria', 'otro'
    )
);

NOTIFY pgrst, 'reload schema';
