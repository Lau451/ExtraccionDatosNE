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
--
-- Hardening (revisión RDD de T1+T2, oc-entregas-planificacion) -- el ADD
-- CONSTRAINT de más abajo no era idempotente (reventaba "constraint ya
-- existe" en un reintento) y el backfill no tenía tope de dígitos (un N con
-- más de 10 dígitos revienta el ::INTEGER con "integer out of range" antes de
-- llegar siquiera al CHECK). Este archivo ya está APLICADO en la TEST DB
-- (grnamollopxdlstcpxhc, 7037 filas backfillleadas) -- el cambio de acá es
-- puramente defensivo para un entorno NUEVO que corra esta migración desde
-- cero: sobre una base ya migrada es un no-op (el DO block detecta que el
-- constraint ya existe; el patrón `[0-9]{1,9}` sigue matcheando exactamente
-- los mismos N reales de esta DB, ninguno tiene 10+ dígitos), así que es
-- comportamiento equivalente para la TEST DB, no un cambio de datos.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE productos ADD COLUMN IF NOT EXISTS unidades_por_presentacion INTEGER NULL;

-- Idempotente: Postgres no soporta "ADD CONSTRAINT IF NOT EXISTS" para CHECK
-- constraints, así que se guarda con un lookup a pg_constraint antes de
-- agregarla -- un reintento de esta migración (entorno nuevo con retry, o
-- corrida manual dos veces) ya no revienta con "constraint ... already exists".
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_productos_unidades_por_presentacion'
  ) THEN
    ALTER TABLE productos ADD CONSTRAINT ck_productos_unidades_por_presentacion
      CHECK (unidades_por_presentacion IS NULL OR unidades_por_presentacion > 0);
  END IF;
END $$;

COMMENT ON COLUMN productos.unidades_por_presentacion IS
  'Tamaño de pack numérico inferido de presentacion cuando coincide EXACTAMENTE con "Presentación x N" (ej. "Presentación x 25" -> 25). NULL si presentacion usa otro formato o está vacía -- no hay forma confiable de interpretarlo (0031). Usado para advertir divisibilidad no bloqueante en la planificación de entregas de OC.';

-- Acotado a 1-9 dígitos (hasta 999.999.999): un N de 10+ dígitos podría
-- superar el tope de int4 (2147483647) y hacer que el ::INTEGER reviente con
-- "integer out of range" en vez de simplemente no ofrecer un tamaño de pack
-- (mismo criterio que parsear_unidades_por_presentacion, services/productos/
-- domain.py). 9 dígitos es un techo generoso para un tamaño de pack real y
-- nunca puede desbordar int4 (999.999.999 < 2.147.483.647).
UPDATE productos
SET unidades_por_presentacion = substring(presentacion FROM '^Presentación x ([0-9]{1,9})$')::INTEGER
WHERE presentacion ~ '^Presentación x [0-9]{1,9}$'
  AND substring(presentacion FROM '^Presentación x ([0-9]{1,9})$')::INTEGER > 0;

NOTIFY pgrst, 'reload schema';
