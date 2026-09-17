-- Down migration para 0020_productos_clasificacion_solucion_nutricion.sql
-- No revierte datos: si alguna fila quedo con 'solucion'/'nutricion', el
-- ALTER CONSTRAINT de abajo va a fallar (a proposito) hasta reclasificar
-- esas filas a mano -- evita perder informacion de clasificacion en un
-- rollback silencioso.

ALTER TABLE productos DROP CONSTRAINT ck_productos_clasificacion;
ALTER TABLE productos ADD CONSTRAINT ck_productos_clasificacion CHECK (
    clasificacion IS NULL OR clasificacion IN (
        'medicamento', 'descartable', 'insumo', 'equipamiento', 'perfumeria', 'otro'
    )
);

NOTIFY pgrst, 'reload schema';
