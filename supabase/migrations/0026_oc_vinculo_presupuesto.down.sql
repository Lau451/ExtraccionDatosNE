-- Down migration para 0026.
--
-- AVISO (datos antes que esquema): DROP COLUMN presupuesto_item_id borra TODO
-- el trabajo de reconciliacion humana. No es reconstruible: oc_items guarda el
-- producto_id heredado, no de que renglon de presupuesto salio. Exportar antes
-- si la baja puede revertirse:
--   COPY (SELECT id, orden_compra_id, presupuesto_item_id, vinculo_origen,
--                vinculo_confirmado_por, vinculo_confirmado_at
--           FROM oc_items WHERE presupuesto_item_id IS NOT NULL)
--     TO '/tmp/oc_vinculos.csv' CSV HEADER;
--
-- Los oc_items.producto_id ya heredados NO se tocan: son datos de negocio
-- legitimos, identicos a los que un operador podria haber cargado a mano
-- (proposal.md § Rollback Plan). El rollback quita el mecanismo, no su resultado.

DROP INDEX IF EXISTS idx_oci_presupuesto_item;

ALTER TABLE oc_items DROP CONSTRAINT IF EXISTS ck_oci_vinculo_origen_val;
ALTER TABLE oc_items DROP CONSTRAINT IF EXISTS ck_oci_vinculo_origen;
ALTER TABLE oc_items DROP CONSTRAINT IF EXISTS ck_oci_vinculo_excluyente;
ALTER TABLE oc_items DROP CONSTRAINT IF EXISTS fk_oci_presupuesto_item;

ALTER TABLE oc_items DROP COLUMN IF EXISTS vinculo_confirmado_at;
ALTER TABLE oc_items DROP COLUMN IF EXISTS vinculo_confirmado_por;
ALTER TABLE oc_items DROP COLUMN IF EXISTS vinculo_origen;
ALTER TABLE oc_items DROP COLUMN IF EXISTS vinculo_descartado;
ALTER TABLE oc_items DROP COLUMN IF EXISTS presupuesto_item_id;

-- uq_pi_id_drog se deja: es una clave correcta por si misma y otras FK futuras
-- pueden haberla tomado como objetivo. Dropearla solo si se verifico que nadie
-- la referencia:
--   SELECT conname FROM pg_constraint WHERE confrelid = 'presupuesto_items'::regclass;
