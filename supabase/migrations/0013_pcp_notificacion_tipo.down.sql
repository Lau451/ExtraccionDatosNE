-- Rollback de 0013_pcp_notificacion_tipo.sql -- vuelve el CHECK a su forma
-- original. Solo es seguro correr este down mientras ninguna fila de
-- `notificaciones` tenga tipo = 'pcp_cerrada' todavía (si las hay, hay que
-- migrarlas/borrarlas antes -- el ALTER TABLE ADD CONSTRAINT fallaría si
-- alguna fila viola el CHECK angosto).

ALTER TABLE notificaciones DROP CONSTRAINT ck_notif_tipo;
ALTER TABLE notificaciones ADD CONSTRAINT ck_notif_tipo CHECK (tipo IN (
    'oc_creada', 'evento_vencido', 'evento_asignado', 'ia_completada',
    'error_automatizacion', 'comparativa_disponible', 'presupuesto_aprobado',
    'presupuesto_pendiente', 'proceso_por_vencer', 'entrega_atrasada',
    'precio_por_vencer', 'sistema', 'otro'
));

NOTIFY pgrst, 'reload schema';
