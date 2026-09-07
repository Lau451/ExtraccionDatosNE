-- =============================================================================
-- gestor-pcp PR11 (tasks.md 11.9, design.md D10) — agrega 'pcp_cerrada' al
-- CHECK de notificaciones.tipo.
--
-- **Deviación explícita respecto a tasks.md 11.9**: la tarea describe el
-- cambio como "Add pcp_cerrada to TipoNotificacion in
-- services/presupuestacion/notificaciones/models.py (additive)" -- solo el
-- Literal de Python. Pero `notificaciones` tiene su propio
-- `ck_notif_tipo CHECK (tipo IN (...))` en base (docs/schema/extractor_final.sql:1410-1415)
-- que NO incluye 'pcp_cerrada': editar únicamente el Literal de Pydantic
-- deja el valor pasando la validación de FastAPI pero rechazado por Postgres
-- con un `23514` en cuanto `crear_notificacion` intente escribirlo -- el
-- feedback loop de Fase B (PCP_REPRICING_AUTOMATICO) fallaría en runtime
-- pese a estar "implementado". Esta migración cierra ese gap con el único
-- cambio de esquema que la tarea necesita de verdad: ensanchar el CHECK
-- (aditivo, ningún valor existente se toca).
--
-- No requiere Supabase MCP para el DROP+ADD CONSTRAINT en sí (una sola
-- transacción, sin RLS/GRANTs nuevos) -- el mismo patrón de aplicación que
-- 0011/0012 (MCP `apply_migration` por el orquestador, ya que el MCP de
-- Supabase no estuvo disponible en este contexto de sdd-apply).
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'gestor-pcp requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE notificaciones DROP CONSTRAINT ck_notif_tipo;
ALTER TABLE notificaciones ADD CONSTRAINT ck_notif_tipo CHECK (tipo IN (
    'oc_creada', 'evento_vencido', 'evento_asignado', 'ia_completada',
    'error_automatizacion', 'comparativa_disponible', 'presupuesto_aprobado',
    'presupuesto_pendiente', 'proceso_por_vencer', 'entrega_atrasada',
    'precio_por_vencer', 'sistema', 'otro', 'pcp_cerrada'
));

NOTIFY pgrst, 'reload schema';
