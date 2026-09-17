-- =============================================================================
-- Migration 0020: agrega 'solucion' y 'nutricion' a productos.clasificacion
--
-- Decision de negocio (revision del informe de observaciones del maestro de
-- productos): Sueros y Sol. de gran volumen no son "medicamento" -- son
-- soluciones parenterales, categoria propia. Nutricion tampoco es "insumo"
-- -- tiene identidad de negocio propia (formulas, suplementos). Ambos se
-- habian mapeado por descarte en la carga inicial (0018/0019 no tocan esto,
-- es dato, no RLS). Queda:
--   medicamento, descartable, solucion, nutricion, equipamiento, perfumeria,
--   otro
-- insumo se mantiene para reactivos y similares (unico caso restante) y
-- para lo que no encaje en el resto.
-- =============================================================================

ALTER TABLE productos DROP CONSTRAINT ck_productos_clasificacion;
ALTER TABLE productos ADD CONSTRAINT ck_productos_clasificacion CHECK (
    clasificacion IS NULL OR clasificacion IN (
        'medicamento', 'descartable', 'solucion', 'nutricion',
        'insumo', 'equipamiento', 'perfumeria', 'otro'
    )
);

NOTIFY pgrst, 'reload schema';
