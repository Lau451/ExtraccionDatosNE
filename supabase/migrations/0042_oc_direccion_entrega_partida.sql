-- =============================================================================
-- 0042: la dirección de entrega de la OC se guarda en tres partes
-- (odd/tasks/oc-export-direccion-presupuesto.md S2, T1).
--
-- Sistemas (Progress) pide el CSV de exportación con la dirección partida:
-- direccion_entrega = solo calle y número, codigo_postal_entrega aparte y
-- notas_entrega con el resto (lugar, horario). La extracción ya las devuelve
-- separadas; acá solo se agregan las dos columnas nuevas.
--
-- Aditiva: columnas NULL, sin backfill. Las OC existentes conservan la
-- dirección completa en direccion_entrega.
-- =============================================================================

ALTER TABLE ordenes_compra
    ADD COLUMN IF NOT EXISTS codigo_postal_entrega TEXT NULL,
    ADD COLUMN IF NOT EXISTS notas_entrega         TEXT NULL;

COMMENT ON COLUMN ordenes_compra.direccion_entrega IS
  'Domicilio de entrega: solo calle y número (ej. FRENCH 5090) desde 0042. Las OC anteriores a 0042 tienen la dirección completa.';
COMMENT ON COLUMN ordenes_compra.codigo_postal_entrega IS
  'Código postal de la dirección de entrega. NULL si el documento no lo trae. Agregada en 0042.';
COMMENT ON COLUMN ordenes_compra.notas_entrega IS
  'Resto de la dirección de entrega que no es calle, número ni código postal (lugar, sector, localidad, horario). Agregada en 0042.';

NOTIFY pgrst, 'reload schema';
