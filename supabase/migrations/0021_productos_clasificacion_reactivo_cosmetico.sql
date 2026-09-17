-- =============================================================================
-- Migration 0021: clasificacion -- saca insumo/perfumeria, agrega reactivo/cosmetico
--
-- Segunda vuelta sobre la decision de 0020: se saca 'insumo' (quedaba solo
-- para Reactivos, ahora tiene su propia categoria) y 'perfumeria' (pasa a
-- llamarse 'cosmetico', mismo criterio). Enum final:
--   medicamento, descartable, solucion, nutricion, equipamiento, reactivo,
--   cosmetico, otro
--
-- Orden obligatorio: sacar el constraint viejo antes de actualizar filas
-- (si no, el UPDATE intermedio nunca corre porque el propio constraint
-- viejo ya prohibe escribir 'reactivo'/'cosmetico'), actualizar filas
-- existentes, recien despues poner el constraint nuevo -- si el nuevo
-- constraint se agregara antes de migrar los datos, el ALTER fallaria por
-- las filas que todavia dicen 'insumo'/'perfumeria'.
-- =============================================================================

ALTER TABLE productos DROP CONSTRAINT ck_productos_clasificacion;

UPDATE productos SET clasificacion = 'reactivo' WHERE clasificacion = 'insumo';
UPDATE productos SET clasificacion = 'cosmetico' WHERE clasificacion = 'perfumeria';

ALTER TABLE productos ADD CONSTRAINT ck_productos_clasificacion CHECK (
    clasificacion IS NULL OR clasificacion IN (
        'medicamento', 'descartable', 'solucion', 'nutricion',
        'equipamiento', 'reactivo', 'cosmetico', 'otro'
    )
);

NOTIFY pgrst, 'reload schema';
