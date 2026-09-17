-- Down migration para 0022_droguerias_agregar_direccion.sql
-- Elimina la columna. Se pierde el dato de direccion cargado (aceptable: es
-- exactamente el dato que esta migracion agrego, no preexistente).

ALTER TABLE droguerias DROP COLUMN IF EXISTS direccion;

NOTIFY pgrst, 'reload schema';
