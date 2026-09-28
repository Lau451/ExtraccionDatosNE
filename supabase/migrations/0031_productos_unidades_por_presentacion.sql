-- =============================================================================
-- Migration 0031: productos.unidades_por_presentacion (oc-entregas-planificacion, T1)
--
-- `productos.presentacion` es texto libre (D6: lo carga el import legacy o el
-- alta manual). En la TEST DB, 7037/7144 productos siguen el formato
-- "Presentación x N" (ej. "Presentación x 25"), pero 97 usan otros formatos
-- ("Pres x 1(cajax100)", "x35"...) y 10 están en NULL -- no hay ningún tamaño
-- de pack numérico confiable para verificar divisibilidad en la planificación
-- de entregas (odd/tasks/oc-entregas-planificacion.md § Problem).
--
-- 1. unidades_por_presentacion INTEGER NULL, CHECK (> 0): tamaño de pack
--    numérico, cuando se puede inferir sin ambigüedad de `presentacion`.
--    NULL para cualquier otro formato -- la planificación de entregas
--    simplemente no ofrece advertencia de divisibilidad para esos productos.
-- 2. Backfill: solo cuando `presentacion` coincide EXACTAMENTE con
--    "Presentación x N" (N > 0) se extrae N. Cualquier otra variante queda
--    en NULL a propósito -- interpretar "Pres x 1(cajax100)" o "x35" es
--    ambiguo y está fuera de alcance (mismo criterio que el parser
--    `parsear_unidades_por_presentacion`, services/productos/domain.py).
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE productos ADD COLUMN IF NOT EXISTS unidades_por_presentacion INTEGER NULL;

ALTER TABLE productos ADD CONSTRAINT ck_productos_unidades_por_presentacion
  CHECK (unidades_por_presentacion IS NULL OR unidades_por_presentacion > 0);

COMMENT ON COLUMN productos.unidades_por_presentacion IS
  'Tamaño de pack numérico inferido de presentacion cuando coincide EXACTAMENTE con "Presentación x N" (ej. "Presentación x 25" -> 25). NULL si presentacion usa otro formato o está vacía -- no hay forma confiable de interpretarlo (0031). Usado para advertir divisibilidad no bloqueante en la planificación de entregas de OC.';

UPDATE productos
SET unidades_por_presentacion = substring(presentacion FROM '^Presentación x ([0-9]+)$')::INTEGER
WHERE presentacion ~ '^Presentación x [0-9]+$'
  AND substring(presentacion FROM '^Presentación x ([0-9]+)$')::INTEGER > 0;

NOTIFY pgrst, 'reload schema';
