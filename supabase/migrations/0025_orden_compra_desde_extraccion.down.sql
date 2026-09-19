-- Down migration para 0025.
--
-- AVISO 1 (datos antes que esquema): restaurar NOT NULL en proceso_comercial_id
-- exige borrar o rellenar previamente toda OC originada en extraccion
-- (proceso_comercial_id IS NULL). El ALTER falla si queda alguna.
--
-- AVISO 2: restaurar uq_oc (alcance GLOBAL) es estrictamente mas restrictivo que
-- los indices parciales. Si dos clientes registraron el mismo
-- (numero_oc, version_numero), el ALTER falla. Verificar y resolver antes:
--   SELECT numero_oc, version_numero, count(*)
--     FROM ordenes_compra GROUP BY 1, 2 HAVING count(*) > 1;
--
-- AVISO 3 (perdida de conocimiento): DROP TABLE oc_cliente_alias borra todo lo
-- que el sistema aprendio de cada confirmacion humana (D3.1). No es
-- reconstruible desde las OC ya materializadas: ordenes_compra guarda el
-- cliente_id resuelto, no el texto de encabezado que lo origino. Exportar antes
-- si la baja puede revertirse:
--   COPY (SELECT * FROM oc_cliente_alias) TO '/tmp/oc_cliente_alias.csv' CSV HEADER;
--
-- AVISO 4 (grupos): DROP COLUMN grupo_id disuelve toda agrupacion pendiente. Las
-- extracciones agrupadas y NO validadas quedan como N documentos sueltos, y
-- validarlas por separado produce N ordenes_compra con el mismo numero_oc y el
-- mismo cliente -- que uq_oc_por_cliente rechaza. Verificar que no quede ninguna:
--   SELECT grupo_id, count(*) FROM extraction_results
--    WHERE grupo_id IS NOT NULL AND validado = false GROUP BY 1;

DROP INDEX IF EXISTS idx_er_grupo;
ALTER TABLE extraction_results DROP COLUMN IF EXISTS grupo_id;

DROP INDEX IF EXISTS idx_oca_cliente;
DROP TABLE IF EXISTS oc_cliente_alias;

ALTER TABLE entregas_oc_items DROP CONSTRAINT IF EXISTS ck_eoci_planificada;
ALTER TABLE entregas_oc_items DROP COLUMN IF EXISTS cantidad_planificada;

DROP INDEX IF EXISTS uq_oc_por_cliente;
DROP INDEX IF EXISTS uq_oc_por_proceso;
ALTER TABLE ordenes_compra ADD CONSTRAINT uq_oc UNIQUE (numero_oc, version_numero);

ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS ck_oc_anclaje;
ALTER TABLE ordenes_compra ALTER COLUMN proceso_comercial_id SET NOT NULL;
