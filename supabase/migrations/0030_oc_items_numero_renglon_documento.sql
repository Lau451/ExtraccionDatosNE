-- =============================================================================
-- Migration 0030: oc_items.numero_renglon_documento (oc-numero-renglon-documento, T1)
--
-- oc_items.numero_renglon es un ordinal 1..N asignado por POSICIÓN al
-- confirmar una orden de compra (D13.1, _materializar_orden_compra en
-- services/presupuestacion/extraccion/service.py) -- es la clave posicional
-- que uq_oci protege, y así se queda: un grupo de extracciones puede traer
-- documentos con numeración repetida, y numero_renglon no puede depender de
-- eso.
--
-- La pantalla de matching necesita mostrar igual el número que el CLIENTE
-- imprimió en su documento (7, 38, 41...), porque numero_renglon (1..N) no
-- coincide con el papel. `FilaOrdenCompraIn.numero_renglon_documento` ya
-- viajaba desde el frontend pero se descartaba por completo -- esta columna
-- lo persiste, solo para mostrar.
--
-- 1. numero_renglon_documento TEXT NULL: sin unicidad (a propósito -- ver
--    arriba). NULL cuando la extracción no detectó un número en el
--    documento, o en filas materializadas ANTES de esta migración (fuera de
--    alcance backfillear: odd/tasks/oc-numero-renglon-documento.md § Scope).
--    El frontend cae de vuelta a numero_renglon cuando esta columna es NULL.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE oc_items ADD COLUMN IF NOT EXISTS numero_renglon_documento TEXT NULL;

COMMENT ON COLUMN oc_items.numero_renglon_documento IS
  'Número de línea impreso en el documento del cliente (7, 38, 41...), solo para mostrar. Distinto de numero_renglon (ordinal interno 1..N asignado por posición, D13.1): sin unicidad -- filas de documentos agrupados pueden repetirlo sin conflicto. NULL si la extracción no lo detectó, o en filas materializadas antes de esta migración (0030); la pantalla cae a numero_renglon en ese caso.';

NOTIFY pgrst, 'reload schema';
