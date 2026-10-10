-- =============================================================================
-- Migration 0032: exportación de OC a Progress + vista de compromisos de entrega
-- (oc-export-progress, Fase 1; design.md D1, D9)
--
-- 1. ordenes_compra.exportado_at / exportado_por / archivo_exportado: marca de
--    que la OC ya se exportó a Progress (CSV en disco). Son tres columnas y no
--    una tabla de historial porque una OC se exporta una sola vez por versión.
--    `estado` NO cambia al exportar (design C1): las OC extraídas nacen
--    'emitida' y ese estado ya habilita registrar entregas; la marca de
--    exportación es exportado_at IS NOT NULL.
--    - exportado_por: FK a usuarios(id), mismo criterio que fk_er_subidopor
--      (0029) y fk_terceros_createdby (0008).
--    - ck_oc_exportacion: las tres columnas son NULL o las tres NOT NULL; no
--      puede quedar una exportación a medias.
-- 2. idx_oc_exportadas: parcial (la mayoría de las OC no se exporta) para el
--    filtro del calendario de compromisos.
-- 3. v_compromisos_entregas: una fila por ítem de entrega pendiente de una OC
--    exportada, vigente y no cancelada. "Hoy" se calcula en hora argentina:
--    con CURRENT_DATE (UTC en Supabase), entre las 21:00 y las 24:00 una
--    entrega de mañana figuraría como de hoy. El día de hoy cuenta como
--    'futura'. WITH (security_invoker = true) para que aplique la RLS de quien
--    consulta (convención de 0008). Las vistas del proyecto no llevan GRANT
--    propio, esta tampoco.
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS exportado_at TIMESTAMPTZ NULL;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS exportado_por UUID NULL;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS archivo_exportado TEXT NULL;

-- Idempotente: Postgres no soporta "ADD CONSTRAINT IF NOT EXISTS" para FK ni
-- CHECK, así que se guardan con un lookup a pg_constraint (patrón de 0031).
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_oc_exportadopor'
  ) THEN
    ALTER TABLE ordenes_compra ADD CONSTRAINT fk_oc_exportadopor
      FOREIGN KEY (exportado_por) REFERENCES usuarios (id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_oc_exportacion'
  ) THEN
    ALTER TABLE ordenes_compra ADD CONSTRAINT ck_oc_exportacion
      CHECK (
        (exportado_at IS NULL AND exportado_por IS NULL AND archivo_exportado IS NULL)
        OR (exportado_at IS NOT NULL AND exportado_por IS NOT NULL AND archivo_exportado IS NOT NULL)
      );
  END IF;
END $$;

COMMENT ON COLUMN ordenes_compra.exportado_at IS
  'Momento en que la OC se exportó a Progress. NULL = no exportada. Es la marca de exportación: el estado de la OC NO cambia al exportar (oc-export-progress, design C1). Las tres columnas exportado_* van juntas (ck_oc_exportacion). Agregada en 0032.';
COMMENT ON COLUMN ordenes_compra.exportado_por IS
  'Usuario que ejecutó la exportación a Progress. NULL si la OC no se exportó (ck_oc_exportacion). Agregada en 0032.';
COMMENT ON COLUMN ordenes_compra.archivo_exportado IS
  'Nombre del CSV generado en la carpeta de integración con Progress (OC_{cliente}_{numero_oc}_v{version}_{timestamp}.csv). NULL si la OC no se exportó (ck_oc_exportacion). Agregada en 0032.';

CREATE INDEX IF NOT EXISTS idx_oc_exportadas
    ON ordenes_compra (drogueria_id)
    WHERE exportado_at IS NOT NULL;

CREATE OR REPLACE VIEW v_compromisos_entregas WITH (security_invoker = true) AS
SELECT
    oc.drogueria_id,
    oc.id AS orden_compra_id,
    oc.numero_oc,
    oc.version_numero,
    oc.exportado_at,
    t.razon_social AS cliente,
    e.id AS entrega_oc_id,
    e.numero_entrega,
    e.fecha_entrega_planificada,
    oi.numero_renglon,
    p.codigo_interno AS codigo_articulo,
    oi.descripcion,
    ei.cantidad_planificada,
    CASE WHEN e.fecha_entrega_planificada
              < (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
         THEN 'vencida' ELSE 'futura' END AS situacion,
    GREATEST((now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
             - e.fecha_entrega_planificada, 0) AS dias_atraso
FROM entregas_oc e
JOIN ordenes_compra oc    ON oc.id = e.orden_compra_id AND oc.drogueria_id = e.drogueria_id
JOIN entregas_oc_items ei ON ei.entrega_oc_id = e.id AND ei.drogueria_id = e.drogueria_id
JOIN oc_items oi          ON oi.id = ei.oc_item_id AND oi.drogueria_id = ei.drogueria_id
LEFT JOIN productos p     ON p.id = oi.producto_id AND p.drogueria_id = oi.drogueria_id
LEFT JOIN terceros t      ON t.id = oc.cliente_id AND t.drogueria_id = oc.drogueria_id
WHERE oc.exportado_at IS NOT NULL
  AND oc.deleted_at IS NULL
  AND oc.es_vigente
  AND oc.estado <> 'cancelada'
  AND e.estado = 'pendiente';

COMMENT ON VIEW v_compromisos_entregas IS
  'Compromisos de entrega: una fila por ítem de entrega pendiente de una OC exportada a Progress (exportado_at), vigente y no cancelada. situacion = vencida si la fecha planificada es anterior a hoy (hora Argentina), futura en otro caso (hoy cuenta como futura); dias_atraso >= 0. Agregada en 0032.';

NOTIFY pgrst, 'reload schema';
